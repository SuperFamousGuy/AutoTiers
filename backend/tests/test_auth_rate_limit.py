import time
from app.auth.rate_limit import SlidingWindowRateLimiter


def test_allows_under_limit():
    rl = SlidingWindowRateLimiter(max_attempts=3, window_seconds=60)
    assert rl.check_and_record("alice@x.com") is True
    assert rl.check_and_record("alice@x.com") is True
    assert rl.check_and_record("alice@x.com") is True


def test_blocks_after_limit():
    rl = SlidingWindowRateLimiter(max_attempts=3, window_seconds=60)
    rl.check_and_record("alice@x.com")
    rl.check_and_record("alice@x.com")
    rl.check_and_record("alice@x.com")
    assert rl.check_and_record("alice@x.com") is False


def test_window_expires(monkeypatch):
    rl = SlidingWindowRateLimiter(max_attempts=2, window_seconds=10)
    rl.check_and_record("alice@x.com")
    rl.check_and_record("alice@x.com")
    assert rl.check_and_record("alice@x.com") is False
    # Advance time past the window. Capture the real time.time before
    # patching so the lambda doesn't recurse into itself.
    real_time = time.time
    monkeypatch.setattr(time, "time", lambda: real_time() + 20)
    assert rl.check_and_record("alice@x.com") is True


def test_keys_are_independent():
    rl = SlidingWindowRateLimiter(max_attempts=2, window_seconds=60)
    rl.check_and_record("alice@x.com")
    rl.check_and_record("alice@x.com")
    assert rl.check_and_record("alice@x.com") is False
    assert rl.check_and_record("bob@x.com") is True
