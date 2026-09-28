from __future__ import annotations

import time
from collections import defaultdict
from threading import Lock


class RateLimiter:
    def __init__(self, limit: int = 60, window_seconds: int = 60, redis_client=None):
        self.limit, self.window_seconds, self.redis = limit, window_seconds, redis_client
        self._lock = Lock()
        self._memory = defaultdict(list)

    def allow(self, key: str) -> bool:
        now = time.time()
        if self.redis is not None:
            redis_key = f"ratelimit:{key}:{int(now // self.window_seconds)}"
            count = self.redis.incr(redis_key)
            if count == 1:
                self.redis.expire(redis_key, self.window_seconds)
            return count <= self.limit
        with self._lock:
            recent = [stamp for stamp in self._memory[key] if stamp > now - self.window_seconds]
            if len(recent) >= self.limit:
                self._memory[key] = recent
                return False
            recent.append(now)
            self._memory[key] = recent
            return True
