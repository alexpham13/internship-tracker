import re
from datetime import date
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator


class ApplicationStatus(StrEnum):
    APPLIED = "Applied"
    RESPONDED = "Responded"
    INTERVIEW = "Interview"
    OFFER = "Offer"
    REJECTED = "Rejected"


NonBlank = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
ApplicationId = Annotated[str, StringConstraints(pattern=r"^[a-zA-Z0-9_-]{1,128}$")]


class ApplicationFields(BaseModel):
    model_config = ConfigDict(extra="forbid")

    company: NonBlank
    position: NonBlank
    location: NonBlank
    date_applied: date = Field(alias="dateApplied")
    status: ApplicationStatus

    @field_validator("date_applied", mode="before")
    @classmethod
    def validate_date_format(cls, value: object) -> object:
        if isinstance(value, date) or (
            isinstance(value, str) and re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value)
        ):
            return value
        raise ValueError("Use YYYY-MM-DD for the application date.")


class ApplicationRecord(ApplicationFields):
    model_config = ConfigDict(from_attributes=True, validate_by_name=True)

    id: ApplicationId


class ApplicationImport(BaseModel):
    applications: list[ApplicationRecord] = Field(min_length=1)


class ImportResult(BaseModel):
    imported: int
    skipped: int


class Statistics(BaseModel):
    total: int
    responses: int
    interviews: int
    offers: int


class Health(BaseModel):
    status: Literal["ok"]
