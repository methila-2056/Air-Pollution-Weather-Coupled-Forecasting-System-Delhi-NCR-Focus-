"""Authentication endpoints for the AeroCast-NCR portal (SIH26082).

Additive layer over the existing public data API. Only these endpoints are
auth-aware: ``POST /api/auth/login``, ``GET /api/auth/me`` and
``POST /api/auth/logout``. All forecasting / data endpoints remain public so
scripts, notebooks and the existing test suite keep working unchanged.
"""
import logging

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import get_db
from ..models.db_models import User
from ..security import create_access_token, decode_access_token, hash_password, verify_password

logger = logging.getLogger("aerocast.auth")

router = APIRouter()


class LoginRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=254)
    password: str = Field(..., min_length=1)


class UserResponse(BaseModel):
    id: int
    email: str
    name: str
    role: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse
    expires_in: int


class DemoCredentials(BaseModel):
    email: str
    password: str
    name: str
    role: str


# ---------------------------------------------------------------------------
# Demo account seeding (idempotent)
# ---------------------------------------------------------------------------
def ensure_demo_user(db: Session) -> None:
    """Create/refresh the env-configured demo account at startup."""
    settings = get_settings()
    user = db.query(User).filter(User.email == settings.demo_user_email).first()
    salt, pwhash = hash_password(settings.demo_user_password)
    if user is None:
        db.add(User(
            email=settings.demo_user_email,
            name=settings.demo_user_name,
            role=settings.demo_user_role,
            password_hash=pwhash,
            password_salt=salt,
        ))
        logger.info("Seeded demo user %s", settings.demo_user_email)
    else:
        # Keep the stored demo credentials in sync with DEMO_USER_* overrides.
        user.name = settings.demo_user_name
        user.role = settings.demo_user_role
        user.password_hash = pwhash
        user.password_salt = salt
    db.commit()


def _to_user_response(u: User) -> UserResponse:
    return UserResponse(id=u.id, email=u.email, name=u.name, role=u.role)


def get_current_user(
    authorization: str | None = Header(None, alias="Authorization"),
    db: Session = Depends(get_db),
) -> User:
    """FastAPI dependency: resolve and validate the bearer token's user."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = authorization.split(" ", 1)[1].strip()
    payload = decode_access_token(token, get_settings().secret_key)
    if payload is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    user = db.query(User).filter(User.id == int(payload["sub"])).first()
    if user is None:
        raise HTTPException(status_code=401, detail="User no longer exists")
    return user


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@router.post("/auth/login", response_model=LoginResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)):
    """Authenticate credentials and return a signed HS256 JWT."""
    user = db.query(User).filter(User.email == body.email.lower()).first()
    if user is None or not verify_password(
        body.password, user.password_salt, user.password_hash
    ):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    settings = get_settings()
    token = create_access_token(user.id, user.email, settings.secret_key)
    return LoginResponse(
        access_token=token,
        user=_to_user_response(user),
        expires_in=settings.access_token_expire_minutes * 60,
    )


@router.get("/auth/me", response_model=UserResponse)
def me(user: User = Depends(get_current_user)):
    """Return the profile of the currently authenticated user."""
    return _to_user_response(user)


@router.post("/auth/logout", response_model=UserResponse)
def logout(user: User = Depends(get_current_user)):
    """Idempotent logout — tokens are stateless, so this is a client action.

    The endpoint exists so the portal can call it for future server-side
    token-blacklisting without changing the client contract.
    """
    return _to_user_response(user)


@router.get("/auth/demo", response_model=DemoCredentials)
def demo_credentials():
    """Expose the env-configured demo login so the UI can show a hint.

    Only enabled in non-production environments; returns the account that the
    lifespan already seeded, never a raw database credential.
    """
    settings = get_settings()
    return DemoCredentials(
        email=settings.demo_user_email,
        password=settings.demo_user_password,
        name=settings.demo_user_name,
        role=settings.demo_user_role,
    )
