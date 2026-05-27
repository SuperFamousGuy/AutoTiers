import uuid
from datetime import timedelta
from app.auth.jwt import encode_jwt, decode_jwt, JWTInvalid


def test_encode_decode_roundtrip():
    user_id = uuid.uuid4()
    token = encode_jwt(user_id)
    decoded = decode_jwt(token)
    assert decoded == user_id


def test_decode_invalid_token_raises():
    import pytest
    with pytest.raises(JWTInvalid):
        decode_jwt("not.a.token")


def test_decode_expired_token_raises():
    import pytest
    user_id = uuid.uuid4()
    token = encode_jwt(user_id, ttl=timedelta(seconds=-1))
    with pytest.raises(JWTInvalid):
        decode_jwt(token)
