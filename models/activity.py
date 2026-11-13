from pydantic import BaseModel


class ActivityCreate(BaseModel):
    session_id: str
    type: str
    name: str | None = None
    metadata: dict | None = None


class ActivityOut(BaseModel):
    id: str
    session_id: str
    type: str
    name: str | None
    metadata: dict | None
