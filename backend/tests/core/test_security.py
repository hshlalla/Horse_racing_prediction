import pytest
from app.core.security import (
    hash_password, verify_password,
    create_access_token, decode_access_token,
    generate_refresh_token,
)


def test_password_round_trip():
    hashed = hash_password("mypassword123")
    assert verify_password("mypassword123", hashed)
    assert not verify_password("wrong", hashed)


def test_access_token_round_trip():
    token = create_access_token(user_id=42)
    user_id = decode_access_token(token)
    assert user_id == 42


def test_expired_token_raises():
    from jose import jwt as jose_jwt
    import datetime
    from app.core.config import settings
    past = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=1)
    token = jose_jwt.encode(
        {"sub": "1", "exp": past, "iat": past},
        settings.JWT_SECRET,
        algorithm="HS256",
    )
    with pytest.raises(ValueError):
        decode_access_token(token)


def test_refresh_token_is_unique():
    raw1, hash1 = generate_refresh_token()
    raw2, hash2 = generate_refresh_token()
    assert raw1 != raw2
    assert hash1 != hash2
    assert len(raw1) == 43  # base64url of 32 bytes


def test_invalid_token_raises():
    with pytest.raises(ValueError):
        decode_access_token("not.a.valid.jwt")
