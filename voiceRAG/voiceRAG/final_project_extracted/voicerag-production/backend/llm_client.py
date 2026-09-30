from __future__ import annotations

import json
import logging
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .config import Settings, settings

logger = logging.getLogger(__name__)


def _chat_completions_url(base_url: str) -> str:
    base = base_url.rstrip("/")
    if base.endswith("/chat/completions"):
        return base
    return f"{base}/chat/completions"


def complete_chat(
    messages: list[dict[str, str]],
    *,
    temperature: float,
    max_tokens: int,
    config: Settings = settings,
    provider: str | None = None,
    api_key_override: str | None = None,
    endpoint_override: str | None = None,
    model_override: str | None = None,
    opener: Callable[..., Any] = urlopen,
    purpose: str = "chat completion",
) -> str | None:
    """Call the configured chat provider, returning None when it is unavailable.

    AssemblyAI uses its key directly in Authorization. OpenAI-compatible providers
    use the conventional Bearer scheme and a configurable API base URL.
    """
    selected_provider = (provider or config.llm_provider).strip().lower()
    if selected_provider == "assemblyai":
        api_key = api_key_override if api_key_override is not None else config.assemblyai_api_key
        endpoint = endpoint_override or config.llm_gateway_url
        model = model_override or config.llm_gateway_model
        authorization = api_key
    elif selected_provider == "openai_compatible":
        api_key = api_key_override if api_key_override is not None else config.llm_api_key
        endpoint = _chat_completions_url(endpoint_override or config.llm_api_base_url)
        model = model_override or config.llm_api_model
        authorization = f"Bearer {api_key}" if api_key else None
    else:
        logger.error("Unsupported LLM provider %r for %s", selected_provider, purpose)
        return None

    if not api_key:
        logger.debug("No API key is configured for LLM provider %s", selected_provider)
        return None

    payload = {
        "model": model,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "messages": messages,
    }
    request = Request(
        endpoint,
        data=json.dumps(payload).encode(),
        method="POST",
        headers={"Authorization": authorization or "", "Content-Type": "application/json"},
    )
    try:
        with opener(request, timeout=90) as response:
            result = json.loads(response.read().decode())
        content = result["choices"][0]["message"]["content"]
        if isinstance(content, str) and content.strip():
            return content.strip()
        logger.warning("LLM provider %s returned empty content for %s", selected_provider, purpose)
    except HTTPError as exc:
        logger.warning("LLM provider %s returned HTTP %s for %s", selected_provider, exc.code, purpose)
    except (URLError, TimeoutError, OSError) as exc:
        logger.warning("LLM provider %s could not be reached for %s: %s", selected_provider, purpose, exc)
    except (KeyError, IndexError, TypeError, ValueError, AttributeError) as exc:
        logger.warning("LLM provider %s returned an invalid response for %s: %s", selected_provider, purpose, exc)
    return None
