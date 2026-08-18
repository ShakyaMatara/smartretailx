"""Unit tests for JWT issuance and verification."""
import time

import jwt
import pytest

pytestmark = pytest.mark.unit


def test_access_token_carries_expected_claims():
    from tokens import create_access_token, decode_token
    token = create_access_token("user-123", "a@example.com", "customer")
    claims = decode_token(token)

    assert claims["sub"] == "user-123"
    assert claims["email"] == "a@example.com"
    assert claims["role"] == "customer"
    assert claims["typ"] == "access"
    assert claims["iss"] == "smartretailx-user-service"
    assert claims["aud"] == "smartretailx-api"
    assert "jti" in claims


def test_token_header_declares_rs256_and_key_id():
    from tokens import create_access_token, key_id
    header = jwt.get_unverified_header(create_access_token("u", "e@x.com", "customer"))
    assert header["alg"] == "RS256"
    assert header["kid"] == key_id()


def test_refresh_token_is_typed_separately():
    """A refresh token must not be usable where an access token is expected."""
    from tokens import create_refresh_token, decode_token
    assert decode_token(create_refresh_token("u", "e@x.com", "customer"))["typ"] == "refresh"


def test_tampered_payload_is_rejected():
    """Altering any character invalidates the signature."""
    from tokens import create_access_token, decode_token
    token = create_access_token("user-123", "a@example.com", "customer")
    head, payload, signature = token.split(".")
    tampered = f"{head}.{payload[:-4]}AAAA.{signature}"

    with pytest.raises(jwt.PyJWTError):
        decode_token(tampered)


def test_token_signed_by_a_different_key_is_rejected():
    from tokens import decode_token
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives import serialization

    rogue = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = rogue.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    forged = jwt.encode(
        {"sub": "attacker", "role": "admin", "typ": "access",
         "iss": "smartretailx-user-service", "aud": "smartretailx-api",
         "exp": int(time.time()) + 900},
        pem, algorithm="RS256",
    )

    with pytest.raises(jwt.PyJWTError):
        decode_token(forged)


def test_expired_token_is_rejected():
    from config import settings
    from tokens import _create_token, decode_token
    from datetime import timedelta

    expired = _create_token("u", "e@x.com", "customer", "access", timedelta(seconds=-60))
    with pytest.raises(jwt.ExpiredSignatureError):
        decode_token(expired)


def test_jwks_publishes_a_matching_key_id():
    """Consumers select the verification key by kid, which makes
    rotation possible without invalidating live tokens."""
    from tokens import key_id, public_jwks
    jwks = public_jwks()
    assert len(jwks["keys"]) == 1
    assert jwks["keys"][0]["kid"] == key_id()
    assert jwks["keys"][0]["alg"] == "RS256"
    assert "d" not in jwks["keys"][0], "private exponent must never be published"
