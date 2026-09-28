#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
from urllib.parse import urlparse

REQUIRED = {
    "SECRET_KEY": lambda value: len(value) >= 32 and "replace" not in value.lower(),
    "ASSEMBLYAI_API_KEY": lambda value: bool(value),
    "DATABASE_URL": lambda value: value.startswith(("postgresql://", "postgresql+asyncpg://")),
    "REDIS_URL": lambda value: urlparse(value).scheme == "redis",
    "QDRANT_URL": lambda value: urlparse(value).scheme in {"http", "https"},
    "S3_ENDPOINT_URL": lambda value: urlparse(value).scheme in {"http", "https"},
}


def main() -> int:
    errors: list[str] = []
    if os.getenv("APP_ENV", "production").lower() == "production" and os.getenv("AUTH_REQUIRED", "true").lower() != "true":
        errors.append("AUTH_REQUIRED must be true in production")
    for name, check in REQUIRED.items():
        value = os.getenv(name, "").strip()
        if not value or not check(value):
            errors.append(f"{name} is missing or invalid")
    if os.getenv("VECTOR_BACKEND", "qdrant").lower() == "qdrant" and not os.getenv("QDRANT_COLLECTION", "").strip():
        errors.append("QDRANT_COLLECTION is required for Qdrant")
    if errors:
        print("Environment validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print("Environment validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
