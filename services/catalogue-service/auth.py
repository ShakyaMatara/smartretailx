import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from config import settings

bearer_scheme = HTTPBearer(auto_error=False)

# Fetches and caches the public keys published by the User Service.
# Verification then happens locally on every request - no network call
# to the User Service per request, so it is not a bottleneck and its
# failure does not stop this service authenticating requests.
_jwks_client = jwt.PyJWKClient(settings.jwks_url, cache_keys=True)


def get_claims(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> dict:
    """Verify the bearer token and return its claims."""
    unauthorised = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials.",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if credentials is None:
        raise unauthorised

    try:
        signing_key = _jwks_client.get_signing_key_from_jwt(credentials.credentials)
        claims = jwt.decode(
            credentials.credentials,
            signing_key.key,
            algorithms=[settings.jwt_algorithm],
            issuer=settings.jwt_issuer,
            audience=settings.jwt_audience,
        )
    except Exception:
        raise unauthorised

    if claims.get("typ") != "access":
        raise unauthorised

    return claims


def require_roles(*allowed_roles: str):
    """Same RBAC pattern as the User Service, enforced independently
    here. Each service authorises its own requests rather than trusting
    an upstream caller - a Zero Trust principle."""
    def checker(claims: dict = Depends(get_claims)) -> dict:
        if claims.get("role") not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient privileges for this operation.",
            )
        return claims

    return checker