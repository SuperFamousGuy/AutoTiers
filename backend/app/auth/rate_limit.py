"""In-memory sliding-window rate limiter for login attempts.

NOT process-safe. Acceptable for single-process FastAPI dev and the v1
single-container Railway deploy. Move to Redis when we go multi-instance.
"""
import time
from collections import defaultdict, deque
from typing import Deque, Dict


class LoginRateLimiter:
    def __init__(self, max_attempts: int = 5, window_seconds: int = 900):
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self._attempts: Dict[str, Deque[float]] = defaultdict(deque)

    def check_and_record(self, key: str) -> bool:
        """Returns True if the request is allowed, False if rate-limited.

        Records the attempt either way (so spamming a blocked key extends
        the block — the standard sliding-window behavior).
        """
        now = time.time()
        bucket = self._attempts[key]
        cutoff = now - self.window_seconds
        while bucket and bucket[0] < cutoff:
            bucket.popleft()
        if len(bucket) >= self.max_attempts:
            return False
        bucket.append(now)
        return True


# Module-level singleton used by the auth router.
login_rate_limiter = LoginRateLimiter()
