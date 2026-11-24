from datetime import date

from sqlalchemy import Date, Enum, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base
from .schemas import ApplicationStatus


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(primary_key=True)
    name: Mapped[str]
    email: Mapped[str] = mapped_column(unique=True)
    password_hash: Mapped[str]
    legacy_access: Mapped[bool] = mapped_column(default=False)


class AuthSession(Base):
    __tablename__ = "auth_sessions"

    token_hash: Mapped[str] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    expires_at: Mapped[int] = mapped_column(index=True)


class AuthRateLimit(Base):
    __tablename__ = "auth_rate_limits"

    key: Mapped[str] = mapped_column(primary_key=True)
    expires_at: Mapped[int] = mapped_column(index=True)
    attempts: Mapped[int]


class Application(Base):
    __tablename__ = "applications"
    __table_args__ = (UniqueConstraint("user_id", "id"),)

    row_id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    id: Mapped[str] = mapped_column(String(128))
    company: Mapped[str]
    position: Mapped[str]
    location: Mapped[str]
    date_applied: Mapped[date] = mapped_column(Date)
    status: Mapped[ApplicationStatus] = mapped_column(
        Enum(
            ApplicationStatus,
            values_callable=lambda statuses: [status.value for status in statuses],
            create_constraint=True,
            native_enum=False,
        )
    )


class ImportedApplication(Base):
    __tablename__ = "imported_applications"
    __table_args__ = (UniqueConstraint("user_id", "id"),)

    row_id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    id: Mapped[str] = mapped_column(String(128))
