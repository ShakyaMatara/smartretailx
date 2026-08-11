from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
import jwt

from database import get_db
from models import User
from tokens import decode_token

# tokenUrl tells Swagger where the login endpoint is, which is what
# powers the Authorize button in the docs UI.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    """
    Resolve the caller from their bearer token.
    Returns 401 for any token problem.
    """
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials.",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        claims = decode_token(token)
    except jwt.PyJWTError:
        raise credentials_error

    # A refresh token must not be usable as an access token.
    if claims.get("typ") != "access":
        raise credentials_error

    user = db.query(User).filter(User.id == claims.get("sub")).first()
    if user is None or not user.is_active:
        raise credentials_error

    return user


def require_roles(*allowed_roles: str):
    """
    Role-Based Access Control.

    Usage: Depends(require_roles("admin"))

    Returns 403 Forbidden, not 401. The distinction matters and is a
    likely viva question: 401 means "we do not know who you are",
    403 means "we know exactly who you are and you are not allowed".
    """
    def checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient privileges for this operation.",
            )
        return current_user

    return checker