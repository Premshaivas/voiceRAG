#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse


def http_json(url: str, headers: dict[str, str] | None = None, method: str = "GET", payload: dict | None = None) -> dict:
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(url, data=data, method=method, headers={"Content-Type": "application/json", **(headers or {})})
    with urllib.request.urlopen(request, timeout=15) as response:
        body = response.read().decode()
        return json.loads(body) if body else {}


def check_tcp(url: str, label: str) -> None:
    parsed = urlparse(url)
    host = parsed.hostname or "localhost"
    port = parsed.port or (5432 if parsed.scheme.startswith("postgresql") else 6379 if parsed.scheme == "redis" else 80)
    with socket.create_connection((host, port), timeout=5):
        print(f"PASS {label}: TCP {host}:{port}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe live VoiceRAG integrations")
    parser.add_argument("--api-url", default=os.getenv("API_URL", "http://localhost:8000"))
    parser.add_argument("--check-llm", action="store_true", help="Make one minimal LLM Gateway request")
    args = parser.parse_args()
    failures = 0

    def run(label: str, callback) -> None:
        nonlocal failures
        try:
            callback()
        except Exception as exc:
            failures += 1
            print(f"FAIL {label}: {exc}")

    run("API health", lambda: (http_json(f"{args.api_url.rstrip('/')}/health"), print("PASS API health")))
    run("API readiness", lambda: (http_json(f"{args.api_url.rstrip('/')}/health/ready"), print("PASS API readiness")))
    run("PostgreSQL", lambda: check_tcp(os.environ["DATABASE_URL"], "PostgreSQL"))
    run("Redis", lambda: check_tcp(os.environ["REDIS_URL"], "Redis"))

    def qdrant() -> None:
        result = http_json(f"{os.environ['QDRANT_URL'].rstrip('/')}/collections", headers={"api-key": os.getenv("QDRANT_API_KEY", "")})
        assert "result" in result, result
        print("PASS Qdrant")
    run("Qdrant", qdrant)

    def minio() -> None:
        import boto3
        client = boto3.client("s3", endpoint_url=os.environ["S3_ENDPOINT_URL"], region_name=os.getenv("S3_REGION", "us-east-1"), aws_access_key_id=os.environ["S3_ACCESS_KEY"], aws_secret_access_key=os.environ["S3_SECRET_KEY"])
        client.head_bucket(Bucket=os.environ["S3_BUCKET"])
        print("PASS MinIO/S3")
    run("MinIO/S3", minio)

    def assemblyai() -> None:
        request = urllib.request.Request("https://api.assemblyai.com/v2/transcript?limit=1", headers={"authorization": os.environ["ASSEMBLYAI_API_KEY"]})
        with urllib.request.urlopen(request, timeout=15) as response:
            result = json.loads(response.read().decode())
            assert response.status == 200 and "transcripts" in result
        print("PASS AssemblyAI credentials")
    run("AssemblyAI", assemblyai)

    if args.check_llm:
        def llm() -> None:
            provider = os.getenv("LLM_PROVIDER", "assemblyai").strip().lower()
            if provider == "assemblyai":
                endpoint = os.getenv("LLM_GATEWAY_URL", "https://llm-gateway.assemblyai.com/v1/chat/completions")
                model = os.getenv("LLM_GATEWAY_MODEL", "claude-sonnet-4-6")
                authorization = os.environ["ASSEMBLYAI_API_KEY"]
            elif provider == "openai_compatible":
                endpoint = os.getenv("LLM_API_BASE_URL", "https://api.openai.com/v1").rstrip("/")
                if not endpoint.endswith("/chat/completions"):
                    endpoint += "/chat/completions"
                model = os.getenv("LLM_API_MODEL", "gpt-4o-mini")
                authorization = f"Bearer {os.environ['LLM_API_KEY']}"
            else:
                raise ValueError("LLM_PROVIDER must be assemblyai or openai_compatible")
            result = http_json(endpoint, headers={"Authorization": authorization}, method="POST", payload={"model": model, "temperature": 0, "max_tokens": 1, "messages": [{"role": "user", "content": "Reply with OK."}]})
            assert result.get("choices"), result
            print(f"PASS LLM provider ({provider})")
        run("LLM provider", llm)
    else:
        print("SKIP LLM Gateway: rerun with --check-llm")

    if failures:
        print(f"{failures} integration check(s) failed")
        return 1
    print("All requested integration checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
