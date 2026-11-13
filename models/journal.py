from datetime import date, datetime

from pydantic import BaseModel


class JournalPageTypeCreate(BaseModel):
    type_key: str
    display_name: str
    page_order: int = 0


class JournalPageTypeOut(BaseModel):
    type_key: str
    display_name: str
    page_order: int
    created_at: datetime
    updated_at: datetime


class JournalEntryCreate(BaseModel):
    entry_date: date
    mood: str | None = None
    metadata: dict | None = None


class JournalEntryUpdate(BaseModel):
    mood: str | None = None
    metadata: dict | None = None


class JournalPageCreate(BaseModel):
    journal_entry_id: str
    page_type: str
    title: str | None = None
    content: str = ""
    metadata: dict | None = None
    page_order: int = 0


class JournalPageUpdate(BaseModel):
    title: str | None = None
    content: str | None = None
    metadata: dict | None = None
    page_order: int | None = None
    expected_revision: int | None = None


class JournalPageOut(BaseModel):
    id: str
    journal_entry_id: str
    page_type: str
    title: str | None
    content: str
    metadata: dict | None
    page_order: int
    created_at: datetime
    updated_at: datetime
    revision: int


class JournalEntryOut(BaseModel):
    id: str
    entry_date: date
    mood: str | None
    metadata: dict | None
    created_at: datetime
    updated_at: datetime


class JournalEntryWithPagesOut(JournalEntryOut):
    pages: list[JournalPageOut]
