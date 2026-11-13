from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, field_validator


def _require_offset(value: datetime | None) -> datetime | None:
    if value is not None and (value.tzinfo is None or value.utcoffset() is None):
        raise ValueError("due_at must include a UTC offset")
    return value


class TaskCreate(BaseModel):
    title: str
    description: str | None = None
    category: str | None = None
    priority: int | None = None
    due_at: datetime | None = None
    due_date: date | None = None
    session_id: str | None = None
    client_request_id: UUID | None = None
    completed: bool = False

    @field_validator("due_at")
    @classmethod
    def validate_due_at(cls, value: datetime | None) -> datetime | None:
        return _require_offset(value)


class TaskUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    category: str | None = None
    priority: int | None = None
    due_at: datetime | None = None
    due_date: date | None = None
    expected_revision: int | None = None

    @field_validator("due_at")
    @classmethod
    def validate_due_at(cls, value: datetime | None) -> datetime | None:
        return _require_offset(value)


class TaskOut(BaseModel):
    id: str
    title: str
    description: str | None
    category: str | None
    status: str
    priority: int | None
    due_at: datetime | None
    due_date: date | None = None
    completed_at: datetime | None
    created_at: datetime
    session_id: str | None = None
    updated_at: datetime | None = None
    deleted_at: datetime | None = None
    revision: int
    client_request_id: UUID | None = None
