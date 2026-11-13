from fastapi import APIRouter, Depends, Query

from Exercise_Libraray import EXERCISE_LIBRARY
from dependencies import verify_api_key

router = APIRouter()


@router.get("/exercises", dependencies=[Depends(verify_api_key)])
def get_exercises(
    equipment: str | None = Query(None),
    muscle: str | None = Query(None),
):
    exercises = EXERCISE_LIBRARY

    if equipment:
        equipment_clean = equipment.lower().strip()
        exercises = [e for e in exercises if e.get("equipment") == equipment_clean]

    if muscle:
        muscle_clean = muscle.lower().strip()
        exercises = [
            e
            for e in exercises
            if muscle_clean in e.get("primary_muscles", [])
            or muscle_clean in e.get("secondary_muscles", [])
        ]

    return exercises
