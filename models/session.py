from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field


class SessionCreate(BaseModel):
    type: str
    name: str | None = None
    start_time: datetime
    end_time: datetime | None = None
    source: str | None = None
    metadata: dict | None = None
    notes: str | None = None


class SessionOut(BaseModel):
    id: str
    type: str
    name: str | None
    start_time: datetime
    end_time: datetime | None = None
    source: str | None = None
    metadata: dict | None = None
    notes: str | None


class WorkoutSetCreate(BaseModel):
    reps: int = Field(ge=0)
    weight: float = Field(ge=0, allow_inf_nan=False)
    comment: str = ""


class WorkoutExerciseCreate(BaseModel):
    name: str = Field(min_length=1)
    muscle_groups: list[str] = Field(default_factory=list)
    sets: list[WorkoutSetCreate] = Field(default_factory=list)


class WorkoutCreate(BaseModel):
    client_request_id: UUID
    start_time: datetime
    name: str = "Workout"
    notes: str = ""
    duration_minutes: int = Field(default=0, ge=0)
    exercises: list[WorkoutExerciseCreate] = Field(default_factory=list)
    source: str = "desktop"


class WorkoutSetUpdate(WorkoutSetCreate):
    unit: str = "lbs"
    extra_data: dict = Field(default_factory=dict)
    comment_key: str = Field(default="comment", pattern="^(comment|notes)$")
    weight_key: str = Field(default="weight", pattern="^(weight|weight_kg)$")
    record_time: datetime | None = None


class WorkoutExerciseUpdate(WorkoutExerciseCreate):
    metadata: dict = Field(default_factory=dict)
    sets: list[WorkoutSetUpdate] = Field(min_length=1)


class WorkoutUpdate(BaseModel):
    expected_revision: int = Field(ge=1)
    start_time: datetime
    local_date: date
    name: str = "Workout"
    notes: str = ""
    duration_minutes: int = Field(default=0, ge=0)
    exercises: list[WorkoutExerciseUpdate] = Field(min_length=1)
