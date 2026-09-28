from __future__ import annotations

import logging
import time
from collections import Counter
from threading import Lock

from fastapi import Request
from starlette.responses import Response

logger = logging.getLogger("voicerag")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
try:
    from opentelemetry import trace
    tracer = trace.get_tracer("voicerag.http")
except ImportError:  # pragma: no cover - optional deployment dependency
    tracer = None


class Metrics:
    def __init__(self):
        self._lock = Lock()
        self.requests = Counter()
        self.errors = Counter()
        self.latency_ms = Counter()

    def observe(self, method: str, path: str, status: int, elapsed_ms: float) -> None:
        key = (method, path, str(status))
        with self._lock:
            self.requests[key] += 1
            self.latency_ms[(method, path)] += int(elapsed_ms)
            if status >= 500:
                self.errors[(method, path)] += 1

    def prometheus(self) -> str:
        lines = ["# HELP voicerag_http_requests_total HTTP requests", "# TYPE voicerag_http_requests_total counter"]
        with self._lock:
            for (method, path, status), value in sorted(self.requests.items()):
                lines.append(f'voicerag_http_requests_total{{method="{method}",path="{path}",status="{status}"}} {value}')
            lines.append("# HELP voicerag_http_errors_total HTTP 5xx responses")
            lines.append("# TYPE voicerag_http_errors_total counter")
            for (method, path), value in sorted(self.errors.items()):
                lines.append(f'voicerag_http_errors_total{{method="{method}",path="{path}"}} {value}')
            lines.append("# HELP voicerag_http_latency_ms_sum HTTP latency sum")
            lines.append("# TYPE voicerag_http_latency_ms_sum counter")
            for (method, path), value in sorted(self.latency_ms.items()):
                lines.append(f'voicerag_http_latency_ms_sum{{method="{method}",path="{path}"}} {value}')
        return "\n".join(lines) + "\n"


async def observe_request(request: Request, call_next, metrics: Metrics) -> Response:
    started = time.perf_counter()
    if tracer:
        with tracer.start_as_current_span(f"HTTP {request.method} {request.url.path}") as span:
            span.set_attribute("http.method", request.method)
            span.set_attribute("http.route", request.url.path)
            response = await call_next(request)
            span.set_attribute("http.status_code", response.status_code)
    else:
        response = await call_next(request)
    elapsed = (time.perf_counter() - started) * 1000
    metrics.observe(request.method, request.url.path, response.status_code, elapsed)
    logger.info("request method=%s path=%s status=%s latency_ms=%.1f", request.method, request.url.path, response.status_code, elapsed)
    return response
