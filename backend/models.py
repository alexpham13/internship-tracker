from datetime import date

from sqlalchemy import Date, Enum, String
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base
from .schemas import ApplicationStatus


class Application(Base):
    __tablename__ = "applications"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
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

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
