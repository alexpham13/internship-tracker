import hashlib
import os
import re
import secrets
import time
from typing import Annotated
from urllib.parse import urlsplit
from uuid import uuid4

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError
from argon2.low_level import Type
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, EmailStr, StringConstraints, field_validator
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .database import conflict_insert, get_session
from .models import AuthRateLimit, AuthSession, User

DatabaseSession = Annotated[Session, Depends(get_session)]
LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1"}
DEFAULT_ORIGINS = [
    f"http://{host}:{port}"
    for host in ("localhost", "127.0.0.1")
    for port in (5173, 5174, 4173)
]
SESSION_SECONDS = 12 * 60 * 60
RATE_WINDOW_SECONDS = 15 * 60
CSRF_HEADER = "X-InternTrack-Request"
COOKIE_NAME = "interntrack_session"
TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_-]{43}")
passwords = PasswordHasher(type=Type.ID)
DUMMY_PASSWORD_HASH = passwords.hash(secrets.token_urlsafe(32))


def is_loopback_http(scheme: str, hostname: str | None) -> bool:
    return scheme == "http" and hostname in LOOPBACK_HOSTS


class Credentials(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    email: EmailStr
    password: Annotated[str, StringConstraints(min_length=1, max_length=128)]

    @field_validator("email")
    @classmethod
    def normalize_email(cls, email: str) -> str:
        return email.casefold()


class Registration(Credentials):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100, pattern=r"^[^\x00]+$")]
    password: Annotated[str, StringConstraints(min_length=15, max_length=128)]


class Account(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    legacy_access: bool


def configure_auth(app: FastAPI) -> None:
    # Set an explicit allowlist when deploying. Never derive a trusted origin from request headers.
    configured = os.getenv("AUTH_ALLOWED_ORIGINS")
    origins = DEFAULT_ORIGINS if configured is None else [
        origin.strip() for origin in configured.split(",") if origin.strip()
    ]
    for origin in origins:
        parts = urlsplit(origin)
        if (
            parts.scheme not in {"http", "https"} or not parts.hostname
            or parts.username is not None or "*" in parts.netloc
            or origin != f"{parts.scheme}://{parts.netloc}"
        ):
            raise ValueError("AUTH_ALLOWED_ORIGINS must contain exact HTTP(S) origins without trailing slashes.")
    app.state.auth_origins = origins
    secure = os.getenv("AUTH_COOKIE_SECURE", "true").strip().lower()
    if secure not in ("true", "false"):
        raise ValueError("AUTH_COOKIE_SECURE must be true or false.")
    app.state.secure_cookie = secure == "true"
    if not app.state.secure_cookie and any(
        not is_loopback_http(parts.scheme, parts.hostname)
        for parts in map(urlsplit, origins)
    ):
        raise ValueError("AUTH_COOKIE_SECURE=false requires loopback HTTP origins.")
    app.state.session_cookie = f"__Host-{COOKIE_NAME}" if app.state.secure_cookie else COOKIE_NAME


def require_csrf(request: Request) -> None:
    # A cross-origin form cannot send this header. Browser preflights are restricted to trusted origins.
    if request.method not in {"GET", "HEAD", "OPTIONS"} and (
        request.headers.get("origin") not in request.app.state.auth_origins
        or request.headers.get(CSRF_HEADER) != "1"
    ):
        raise HTTPException(403, "Request could not be verified. Reload the page and try again.")
    if not session_cookie_allowed(request):
        raise HTTPException(403, "Local HTTP sessions require a loopback API URL.")


def session_cookie_allowed(request: Request) -> bool:
    return request.app.state.secure_cookie or is_loopback_http(request.url.scheme, request.url.hostname)


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def session_key(request: Request) -> str | None:
    if not session_cookie_allowed(request):
        return None
    token = request.cookies.get(request.app.state.session_cookie)
    return digest(token) if token and TOKEN_PATTERN.fullmatch(token) else None


def current_user(request: Request, response: Response) -> User:
    key = session_key(request)
    user = None
    if key:
        # Release the connection before slow operations such as PDF extraction or Gemini calls.
        with Session(request.app.state.engine) as db:
            user = db.scalar(
                select(User).join(AuthSession, AuthSession.user_id == User.id).where(
                    AuthSession.token_hash == key, AuthSession.expires_at > int(time.time()),
                )
            )
    if user is None:
        raise HTTPException(401, "Sign in to continue.", headers={"Cache-Control": "no-store"})
    require_csrf(request)
    response.headers["Cache-Control"] = "no-store"
    return user


CurrentUser = Annotated[User, Depends(current_user)]


def take_attempt(db: Session, key: str, limit: int) -> None:
    now = int(time.time())
    expires_at = now - now % RATE_WINDOW_SECONDS + RATE_WINDOW_SECONDS
    # The database upsert enforces the limit across processes and concurrent requests.
    db.execute(delete(AuthRateLimit).where(AuthRateLimit.expires_at <= now))
    attempt = conflict_insert(db, AuthRateLimit).values(key=key, expires_at=expires_at, attempts=1)
    count = db.scalar(
        attempt.on_conflict_do_update(
            index_elements=[AuthRateLimit.key],
            set_={"attempts": AuthRateLimit.attempts + 1},
            where=AuthRateLimit.attempts < limit,
        ).returning(AuthRateLimit.attempts)
    )
    db.commit()
    if count is None:
        raise HTTPException(
            429, "Too many attempts. Try again later.",
            headers={"Retry-After": str(expires_at - now), "Cache-Control": "no-store"},
        )


def limit_auth_ip(request: Request, db: DatabaseSession) -> None:
    require_csrf(request)
    operation = request.scope["route"].name
    address = request.client.host if request.client else "unknown"
    limit = 8 if operation == "register" else 30
    take_attempt(db, digest(f"{operation}:ip:{address}"), limit)


def start_session(request: Request, response: Response, db: Session, user: User) -> None:
    now = int(time.time())
    key = session_key(request)
    db.execute(delete(AuthSession).where(AuthSession.expires_at <= now))
    if key:
        db.execute(delete(AuthSession).where(AuthSession.token_hash == key))
    token = secrets.token_urlsafe(32)
    db.add(AuthSession(token_hash=digest(token), user_id=user.id, expires_at=now + SESSION_SECONDS))
    db.commit()
    response.set_cookie(
        request.app.state.session_cookie, token, max_age=SESSION_SECONDS,
        path="/", secure=request.app.state.secure_cookie, httponly=True, samesite="lax",
    )
    response.headers["Cache-Control"] = "no-store"


router = APIRouter(prefix="/auth")


@router.post("/register", status_code=201, dependencies=[Depends(limit_auth_ip)])
def register(fields: Registration, request: Request, response: Response, db: DatabaseSession) -> Account:
    user = User(
        id=str(uuid4()), name=fields.name, email=fields.email,
        password_hash=passwords.hash(fields.password),
    )
    db.add(user)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Could not create an account with that email. Try signing in.") from None
    start_session(request, response, db, user)
    return Account.model_validate(user)


@router.post("/login", dependencies=[Depends(limit_auth_ip)])
def login(fields: Credentials, request: Request, response: Response, db: DatabaseSession) -> Account:
    take_attempt(db, digest(f"login:account:{fields.email}"), 20)
    user = db.scalar(select(User).where(User.email == fields.email))
    password_hash = user.password_hash if user else DUMMY_PASSWORD_HASH
    try:
        passwords.verify(password_hash, fields.password)
    except VerificationError:
        raise HTTPException(401, "Email or password is incorrect.", headers={"Cache-Control": "no-store"}) from None
    if user is None:
        raise HTTPException(401, "Email or password is incorrect.", headers={"Cache-Control": "no-store"})
    if passwords.check_needs_rehash(password_hash):
        user.password_hash = passwords.hash(fields.password)
    start_session(request, response, db, user)
    return Account.model_validate(user)


@router.get("/me")
def me(user: CurrentUser) -> Account:
    return Account.model_validate(user)


@router.post("/logout", status_code=204, dependencies=[Depends(require_csrf)])
def logout(request: Request, response: Response, db: DatabaseSession) -> None:
    key = session_key(request)
    if key:
        db.execute(delete(AuthSession).where(AuthSession.token_hash == key))
        db.commit()
    response.delete_cookie(
        request.app.state.session_cookie, path="/", secure=request.app.state.secure_cookie,
        httponly=True, samesite="lax",
    )
    response.headers["Cache-Control"] = "no-store"
