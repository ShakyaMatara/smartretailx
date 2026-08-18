import hashlib
import json
import uuid
from datetime import datetime, timedelta, timezone
from functools import lru_cache

import jwt
from jwt.algorithms import RSAAlgorithm
from cryptography.hazmat.primitives.serialization import load_pem_public_key
from config import settings


@lru_cache
def _private_key() -> str:
    with open(settings.jwt_private_key_path, "r") as f:
        return f.read()


@lru_cache
def _public_key() -> str:
    with open(settings.jwt_public_key_path, "r") as f:
        return f.read()


@lru_cache
def key_id() -> str:
    """
    A stable identifier for this key pair, derived from the public key.

    The kid is placed in the token header so a verifier holding several
    public keys knows which one to use. This is what makes key rotation
    possible without invalidating tokens signed by the previous key.
    """
    digest = hashlib.sha256(_public_key().encode()).hexdigest()
    return digest[:16]


def _create_token(subject: str, email: str, role: str,
                  token_type: str, expires_delta: timedelta) -> str:
    now = datetime.now(timezone.utc)

    payload = {
        "sub": subject,              # subject: the user id
        "email": email,
        "role": role,                # drives RBAC in every service
        "typ": token_type,           # "access" or "refresh"
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "iat": now,                  # issued at
        "exp": now + expires_delta,  # expiry
        "jti": str(uuid.uuid4()),    # unique id, allows revocation lists
    }

    return jwt.encode(
        payload,
        _private_key(),
        algorithm=settings.jwt_algorithm,
        headers={"kid": key_id()},
    )


def create_access_token(subject: str, email: str, role: str) -> str:
    return _create_token(
        subject, email, role, "access",
        timedelta(minutes=settings.access_token_expire_minutes),
    )


def create_refresh_token(subject: str, email: str, role: str) -> str:
    return _create_token(
        subject, email, role, "refresh",
        timedelta(days=settings.refresh_token_expire_days),
    )


def decode_token(token: str) -> dict:
    """
    Verify and decode a token.

    Raises jwt.PyJWTError on any failure: bad signature, expiry,
    wrong issuer, wrong audience. Note that algorithms is an explicit
    allow-list - accepting whatever the token header claims would
    permit the well-known "alg: none" and algorithm-confusion attacks.
    """
    return jwt.decode(
        token,
        _public_key(),
        algorithms=[settings.jwt_algorithm],
        issuer=settings.jwt_issuer,
        audience=settings.jwt_audience,
    )


def public_jwks() -> dict:
    """
    Publish the public key in JWKS format so other services can fetch
    it over HTTP and verify tokens without any shared secret.
    """
    key = load_pem_public_key(_public_key().encode())
    jwk = json.loads(RSAAlgorithm.to_jwk(key))
    jwk.update({"kid": key_id(), "use": "sig", "alg": settings.jwt_algorithm})
    return {"keys": [jwk]}