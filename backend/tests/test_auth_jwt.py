import uuid
from datetime import timedelta
from app.auth.jwt import encode_jwt, decode_jwt, JWTInvalid, JWTClaims


def test_encode_decode_roundtrip():
    user_id = uuid.uuid4()
    token = encode_jwt(user_id, token_version=0)
    claims = decode_jwt(token)
    assert isinstance(claims, JWTClaims)
    assert claims.user_id == user_id
    assert claims.token_version == 0


def test_encode_decode_roundtrip_with_version():
    user_id = uuid.uuid4()
    token = encode_jwt(user_id, token_version=3)
    claims = decode_jwt(token)
    assert claims.user_id == user_id
    assert claims.token_version == 3


def test_decode_missing_v_claim_defaults_to_zero():
    """Tokens without a 'v' claim (pre-#241) are treated as version 0."""
    import jwt as pyjwt
    from app.config import settings
    from datetime import datetime, timezone
    user_id = uuid.uuid4()
    now = datetime.now(timezone.utc)
    # Build a legacy payload without the "v" claim.
    payload = {"sub": str(user_id), "iat": now, "exp": now + timedelta(days=30)}
    token = pyjwt.encode(payload, settings.jwt_secret, algorithm="HS256")
    claims = decode_jwt(token)
    assert claims.user_id == user_id
    assert claims.token_version == 0


def test_decode_invalid_token_raises():
    import pytest
    with pytest.raises(JWTInvalid):
        decode_jwt("not.a.token")


def test_decode_expired_token_raises():
    import pytest
    user_id = uuid.uuid4()
    token = encode_jwt(user_id, token_version=0, ttl=timedelta(seconds=-1))
    with pytest.raises(JWTInvalid):
        decode_jwt(token)
