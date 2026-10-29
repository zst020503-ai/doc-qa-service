import re

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import AppError, Conflict
from app.core.security import create_access_token, hash_password, verify_password
from app.models import User
from app.repositories import users
from app.schemas import LoginRequest, RegisterRequest, TokenResponse

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _build_token(user: User) -> TokenResponse:
    return TokenResponse(
        access_token=create_access_token(user.id, user.role),
        expires_in=settings.jwt_ttl_minutes * 60,
    )


def register(db: Session, payload: RegisterRequest) -> tuple[User, TokenResponse]:
    email = payload.email.strip().lower()
    if not _EMAIL_RE.match(email):
        raise AppError("INVALID_EMAIL", "邮箱格式不正确", 422)
    if users.get_by_email(db, email) is not None:
        raise Conflict("该邮箱已注册")
    user = users.create(db, email, hash_password(payload.password))
    return user, _build_token(user)


def login(db: Session, payload: LoginRequest) -> TokenResponse:
    email = payload.email.strip().lower()
    user = users.get_by_email(db, email)
    if user is None or not verify_password(payload.password, user.hashed_password):
        raise AppError("INVALID_CREDENTIALS", "邮箱或密码错误", 401)
    return _build_token(user)
