from datetime import datetime

from pydantic import BaseModel


class RecordCreate(BaseModel):
    activity_id: str
    data: dict


class RecordUpdate(BaseModel):
    data: dict


class RecordOut(BaseModel):
    id: str
    activity_id: str
    record_time: datetime
    data: dict
