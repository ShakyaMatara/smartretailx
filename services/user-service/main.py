import uuid
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from config import settings
from database import get_db, init_db
from dependencies import get_current_user, require_roles
from models import User
from schemas import TokenResponse, UserRegisterRequest, UserResponse
from security import hash_password, verify_password
from tokens import create_access_token, create_refresh_token, public_jwks


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Runs once on startup, before the service accepts traffic.
    init_db()
    yield


app = FastAPI(
    title="SmartRetailX User Service",
    description="Handles user registration, authentication and role management.",
    version="1.2.0",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------
# Health probes
# ---------------------------------------------------------------------

@app.get("/health/live", tags=["Health"])
def liveness():
    """Liveness probe: is this process alive?"""
    return {"status": "alive", "service": "user-service"}


@app.get("/health/ready", tags=["Health"])
def readiness(db: Session = Depends(get_db)):
    """
    Readiness probe: can this service actually serve traffic?
    Checks the database connection too, so a service that is running
    but cannot reach its database reports as NOT ready and is removed
    from the load balancer rather than failing requests.
    """
    from sqlalchemy import text

    try:
        db.execute(text("SELECT 1"))
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="database unavailable",
        )
    return {"status": "ready", "service": "user-service"}


# ---------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------

@app.post("/api/v1/auth/login", response_model=TokenResponse, tags=["Authentication"])
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    """
    Authenticate and receive an access and refresh token pair.

    Uses the OAuth 2.0 Resource Owner Password Credentials grant.
    The username field carries the email address.
    """
    user = db.query(User).filter(User.email == form_data.username).first()

    # Deliberately identical response whether the email is unknown or the
    # password is wrong. Distinguishing them would let an attacker
    # enumerate which email addresses hold accounts.
    auth_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Incorrect email or password.",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if user is None:
        # Hash a dummy value anyway so the response time for an unknown
        # email matches that of a known one, closing a timing side-channel.
        hash_password("dummy_password_for_constant_time")
        raise auth_error

    if not verify_password(form_data.password, user.password_hash):
        raise auth_error

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account has been deactivated.",
        )

    return TokenResponse(
        access_token=create_access_token(user.id, user.email, user.role),
        refresh_token=create_refresh_token(user.id, user.email, user.role),
        expires_in=settings.access_token_expire_minutes * 60,
    )


@app.get("/.well-known/jwks.json", tags=["Authentication"])
def jwks():
    """
    Public key set. Other services fetch this to verify tokens
    independently, with no shared secret and no call back to this
    service on every request.
    """
    return public_jwks()


# ---------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------

@app.post(
    "/api/v1/users/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Users"],
)
def register_user(payload: UserRegisterRequest, db: Session = Depends(get_db)):
    """
    Register a new user account.

    Returns 201 Created on success and 409 Conflict if the email
    is already registered.
    """
    existing = db.query(User).filter(User.email == payload.email).first()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email address already exists.",
        )

    user = User(
        email=payload.email,
        full_name=payload.full_name,
        password_hash=hash_password(payload.password),
        role="customer",  # role is never taken from user input
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    return user


@app.get("/api/v1/users/me", response_model=UserResponse, tags=["Users"])
def read_own_profile(current_user: User = Depends(get_current_user)):
    """Return the authenticated user's own profile."""
    return current_user


@app.get("/api/v1/users", response_model=list[UserResponse], tags=["Users"])
def list_users(
    current_user: User = Depends(require_roles("admin")),
    db: Session = Depends(get_db),
    limit: int = 50,
    offset: int = 0,
):
    """
    List all users. Administrators only.

    Paginated by default so the endpoint cannot be used to pull the
    entire user table in a single request.
    """
    return db.query(User).offset(offset).limit(limit).all()


@app.delete("/api/v1/users/me", status_code=status.HTTP_204_NO_CONTENT, tags=["Users"])
def erase_own_account(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Right to erasure (GDPR Article 17).

    Personal data is irreversibly anonymised rather than the row being
    deleted, so that referential integrity with historical order records
    is preserved while no personal data remains.
    """
    current_user.email = f"erased-{current_user.id}@invalid.local"
    current_user.full_name = "[erased]"
    current_user.password_hash = hash_password(str(uuid.uuid4()))
    current_user.is_active = False
    db.commit()
    return None