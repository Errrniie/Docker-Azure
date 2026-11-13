from .Barbell import BARBELL_EXERCISES
from .Bodyweight import BODYWEIGHT_EXERCISES
from .Cable import CABLE_EXERCISES
from .Cardio import CARDIO_EXERCISES
from .Dumbbell import DUMBBELL_EXERCISES
from .Machine import MACHINE_EXERCISES
from .Smith_Machine import SMITH_MACHINE_EXERCISES


EXERCISE_LIBRARY = (
    BARBELL_EXERCISES
    + DUMBBELL_EXERCISES
    + SMITH_MACHINE_EXERCISES
    + CABLE_EXERCISES
    + MACHINE_EXERCISES
    + BODYWEIGHT_EXERCISES
    + CARDIO_EXERCISES
)


ALIAS_MAP: dict[str, str] = {}

for exercise in EXERCISE_LIBRARY:
    canonical_name = exercise["name"]
    ALIAS_MAP[canonical_name.lower()] = canonical_name

    for alias in exercise.get("aliases", []):
        ALIAS_MAP[alias.lower()] = canonical_name


def normalize_exercise_name(name: str | None) -> str | None:
    if not name:
        return None

    cleaned = " ".join(name.strip().lower().split())

    return ALIAS_MAP.get(cleaned, cleaned.title())

