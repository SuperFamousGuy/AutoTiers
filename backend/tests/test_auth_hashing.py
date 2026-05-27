from app.auth.hashing import hash_password, verify_password


def test_hash_password_returns_argon2_string():
    h = hash_password("hunter2hunter2")
    assert h.startswith("$argon2")


def test_verify_password_accepts_correct_password():
    h = hash_password("hunter2hunter2")
    assert verify_password(h, "hunter2hunter2") is True


def test_verify_password_rejects_wrong_password():
    h = hash_password("hunter2hunter2")
    assert verify_password(h, "wrong-password") is False
