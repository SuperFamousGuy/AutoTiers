"""In-memory sliding-window rate limiter.

NOT process-safe. Acceptable for single-process FastAPI dev and the v1
single-container Railway deploy. Move to Redis when we go multi-instance.

Only ``feedback_rate_limiter`` survives the accounts/auth teardown — the
login/password-reset/email-verification limiters were removed with
``api/auth.py``.
"""
import time
from collections import defaultdict, deque
from typing import Deque, Dict


class SlidingWindowRateLimiter:
    def __init__(self, max_attempts: int = 5, window_seconds: int = 900):
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self._attempts: Dict[str, Deque[float]] = defaultdict(deque)

    def check_and_record(self, key: str) -> bool:
        """Returns True if the request is allowed, False if rate-limited.

        Only records the attempt when it is allowed; a request that is
        already over the limit returns False without extending the window,
        so the block clears window_seconds after the last *allowed* attempt.
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


# Rate limiter for in-app feedback submissions — keyed by client IP (there is
# no account to key on; submissions are always anonymous). 5 submissions per
# 10 minutes prevents abuse while leaving room for a user who hits a couple of
# bugs in one session.
feedback_rate_limiter = SlidingWindowRateLimiter(max_attempts=5, window_seconds=600)
