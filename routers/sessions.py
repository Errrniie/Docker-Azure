import logging
import traceback
import hashlib
import json
from datetime import datetime
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from psycopg.types.json import Json
import psycopg

from Exercise_Libraray import normalize_exercise_name
from db import get_conn
from dependencies import verify_api_key
from models.session import SessionCreate, SessionOut, WorkoutCreate, WorkoutUpdate

logger = logging.getLogger("life-api")

router = APIRouter()


@router.post("/workouts", dependencies=[Depends(verify_api_key)])
def create_workout(workout: WorkoutCreate):
    """Create a complete workout in one transaction with a retry-safe request ID."""
    if workout.start_time.tzinfo is None or workout.start_time.utcoffset() is None:
        raise HTTPException(status_code=422, detail="start_time must include a UTC offset")

    request_hash = hashlib.sha256(json.dumps(
        workout.model_dump(mode="json", exclude={"client_request_id"}),
        sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")).hexdigest()
    metadata = {
        "duration_minutes": workout.duration_minutes,
        "local_date": workout.start_time.date().isoformat(),
        "utc_offset_minutes": int(workout.start_time.utcoffset().total_seconds() / 60),
    }

    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO sessions
                        (type, name, start_time, source, metadata, notes,
                         client_request_id, request_hash)
                    VALUES ('workout', %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id;
                """, (
                    workout.name, workout.start_time, workout.source,
                    Json(metadata), workout.notes, workout.client_request_id,
                    request_hash,
                ))
                session_id = cur.fetchone()[0]
                for exercise_order, exercise in enumerate(workout.exercises):
                    cur.execute("""
                        INSERT INTO activities
                            (session_id, type, name, metadata, activity_order)
                        VALUES (%s, 'exercise', %s, %s, %s)
                        RETURNING id;
                    """, (
                        session_id, normalize_exercise_name(exercise.name),
                        Json({"muscle_groups": exercise.muscle_groups}), exercise_order,
                    ))
                    activity_id = cur.fetchone()[0]
                    for set_order, set_item in enumerate(exercise.sets):
                        cur.execute("""
                            INSERT INTO records
                                (activity_id, record_time, data, set_order)
                            VALUES (%s, %s, %s, %s);
                        """, (
                            activity_id, workout.start_time,
                            Json(set_item.model_dump()), set_order,
                        ))
        return {"session_id": session_id, "reused": False}
    except psycopg.errors.UniqueViolation:
        # The first request committed but its response may have been lost.
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT id, request_hash, deleted_at
                    FROM sessions WHERE client_request_id = %s;
                """, (workout.client_request_id,))
                existing = cur.fetchone()
        if existing and existing[1] == request_hash and existing[2] is None:
            return {"session_id": existing[0], "reused": True}
        raise HTTPException(status_code=409, detail="Workout request ID was already used")
    except Exception:
        logger.error("FAILED TO CREATE WORKOUT")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail="Workout creation failed")


@router.post("/sessions", dependencies=[Depends(verify_api_key)])
def create_session(session: SessionCreate):
    session.type = session.type.lower().strip()
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO sessions (
                        type,
                        name,
                        start_time,
                        end_time,
                        source,
                        metadata,
                        notes
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    RETURNING id;
                """, (
                    session.type,
                    session.name,
                    session.start_time,
                    session.end_time,
                    session.source,
                    Json(session.metadata) if session.metadata is not None else None,
                    session.notes,
                ))
                session_id = cur.fetchone()[0]
            conn.commit()

        return {"session_id": session_id}

    except Exception:
        logger.error("FAILED TO CREATE SESSION")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail="Session creation failed")


@router.patch("/workouts/{session_id}", dependencies=[Depends(verify_api_key)])
def update_workout(session_id: UUID, workout: WorkoutUpdate):
    """Replace one workout atomically, refusing an out-of-date editor copy."""
    if workout.start_time.tzinfo is None or workout.start_time.utcoffset() is None:
        raise HTTPException(status_code=422, detail="start_time must include a UTC offset")
    metadata = {
        "duration_minutes": workout.duration_minutes,
        "local_date": workout.local_date.isoformat(),
        "utc_offset_minutes": int(workout.start_time.utcoffset().total_seconds() / 60),
    }
    try:
        with get_conn() as conn:
            with conn.transaction():
                with conn.cursor() as cur:
                    cur.execute("""
                        UPDATE sessions
                        SET name = %s, notes = %s, start_time = %s,
                            end_time = CASE WHEN end_time IS NULL THEN NULL
                                ELSE %s + (end_time - start_time) END,
                            metadata = COALESCE(metadata, '{}'::jsonb) || %s::jsonb,
                            revision = revision + 1
                        WHERE id = %s AND type = 'workout' AND deleted_at IS NULL
                          AND revision = %s
                        RETURNING revision;
                    """, (
                        workout.name, workout.notes, workout.start_time,
                        workout.start_time, Json(metadata), session_id,
                        workout.expected_revision,
                    ))
                    row = cur.fetchone()
                    if row is None:
                        cur.execute("""
                            SELECT 1 FROM sessions
                            WHERE id = %s AND type = 'workout' AND deleted_at IS NULL;
                        """, (session_id,))
                        if cur.fetchone():
                            raise HTTPException(status_code=409, detail="Workout changed; reload before saving")
                        raise HTTPException(status_code=404, detail="Workout not found")

                    cur.execute("""
                        UPDATE records SET deleted_at = now(), deleted_reason = 'replaced'
                        WHERE activity_id IN
                            (SELECT id FROM activities WHERE session_id = %s AND deleted_at IS NULL)
                          AND deleted_at IS NULL;
                    """, (session_id,))
                    cur.execute("""
                        UPDATE activities SET deleted_at = now(), deleted_reason = 'replaced'
                        WHERE session_id = %s AND deleted_at IS NULL;
                    """, (session_id,))
                    for exercise_order, exercise in enumerate(workout.exercises):
                        cur.execute("""
                            INSERT INTO activities
                                (session_id, type, name, metadata, activity_order)
                            VALUES (%s, 'exercise', %s, %s, %s)
                            RETURNING id;
                        """, (
                            session_id, normalize_exercise_name(exercise.name),
                            Json({**exercise.metadata, "muscle_groups": exercise.muscle_groups}),
                            exercise_order,
                        ))
                        activity_id = cur.fetchone()[0]
                        for set_order, set_item in enumerate(exercise.sets):
                            data = dict(set_item.extra_data)
                            data["reps"] = set_item.reps
                            data[set_item.weight_key] = set_item.weight
                            data[set_item.comment_key] = set_item.comment
                            data["unit"] = set_item.unit
                            if "set" in data:
                                data["set"] = set_order + 1
                            cur.execute("""
                                INSERT INTO records
                                    (activity_id, record_time, data, set_order)
                                VALUES (%s, %s, %s, %s);
                            """, (
                                activity_id, set_item.record_time or workout.start_time,
                                Json(data), set_order,
                            ))
        return {"session_id": str(session_id), "revision": row[0]}
    except HTTPException:
        raise
    except Exception:
        logger.error("FAILED TO UPDATE WORKOUT")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail="Workout update failed")


@router.get("/sessions", response_model=List[SessionOut], dependencies=[Depends(verify_api_key)])
def get_sessions(
    type: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    start: datetime | None = None,
    end: datetime | None = None,
    include_deleted: bool = Query(False),
):
    query = """
        SELECT id, type, name, start_time, end_time, source, metadata, notes
        FROM sessions
    """
    params = []
    conditions = []

    if not include_deleted:
        conditions.append("deleted_at IS NULL")

    if start and end:
        conditions.append("start_time BETWEEN %s AND %s")
        params.extend([start, end])
    elif start:
        conditions.append("start_time >= %s")
        params.append(start)
    elif end:
        conditions.append("start_time <= %s")
        params.append(end)

    if type:
        conditions.append("type = %s")
        params.append(type.lower().strip())

    if conditions:
        query += " WHERE " + " AND ".join(conditions)

    query += " ORDER BY start_time DESC LIMIT %s"
    params.append(limit)

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            rows = cur.fetchall()

    return [
        {
            "id": str(r[0]),
            "type": r[1],
            "name": r[2],
            "start_time": r[3],
            "end_time": r[4],
            "source": r[5],
            "metadata": r[6],
            "notes": r[7],
        }
        for r in rows
    ]


@router.get("/workouts/full", dependencies=[Depends(verify_api_key)])
def get_full_workouts():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    s.id,
                    s.type,
                    s.name,
                    s.start_time,
                    s.end_time,
                    s.source,
                    s.metadata,
                    s.notes,
                    a.id,
                    a.type,
                    a.name,
                    a.metadata,
                    r.id,
                    r.record_time,
                    r.data,
                    s.revision
                FROM sessions s
                LEFT JOIN activities a
                  ON a.session_id = s.id AND a.deleted_at IS NULL
                LEFT JOIN records r
                  ON r.activity_id = a.id AND r.deleted_at IS NULL
                WHERE s.type = 'workout'
                  AND s.deleted_at IS NULL
                ORDER BY s.start_time DESC, s.id,
                         a.activity_order, a.id,
                         r.set_order, r.record_time, r.id
            """)
            rows = cur.fetchall()

    sessions: dict[str, dict] = {}
    session_order: list[str] = []

    for row in rows:
        session_id = str(row[0])
        activity_id = row[8]
        record_id = row[12]

        if session_id not in sessions:
            sessions[session_id] = {
                "session_id": session_id,
                "type": row[1],
                "name": row[2],
                "start_time": row[3],
                "end_time": row[4],
                "source": row[5],
                "metadata": row[6],
                "notes": row[7],
                "revision": row[15],
                "activities": [],
                "_activity_map": {},
            }
            session_order.append(session_id)

        session_obj = sessions[session_id]

        if activity_id is not None:
            activity_id_str = str(activity_id)
            if activity_id_str not in session_obj["_activity_map"]:
                activity_obj = {
                    "activity_id": activity_id_str,
                    "type": row[9],
                    "name": row[10],
                    "metadata": row[11],
                    "records": [],
                }
                session_obj["_activity_map"][activity_id_str] = activity_obj
                session_obj["activities"].append(activity_obj)

            if record_id is not None:
                session_obj["_activity_map"][activity_id_str]["records"].append(
                    {
                        "record_id": str(record_id),
                        "record_time": row[13],
                        "data": row[14],
                    }
                )

    result = []
    for session_id in session_order:
        session_obj = sessions[session_id]
        del session_obj["_activity_map"]
        result.append(session_obj)

    return result


@router.get("/sessions/{session_id}", response_model=SessionOut, dependencies=[Depends(verify_api_key)])
def get_session(session_id: str):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, type, name, start_time, end_time, source, metadata, notes
                FROM sessions
                WHERE id = %s
                  AND deleted_at IS NULL
            """, (session_id,))
            row = cur.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Session not found")

    return {
        "id": str(row[0]),
        "type": row[1],
        "name": row[2],
        "start_time": row[3],
        "end_time": row[4],
        "source": row[5],
        "metadata": row[6],
        "notes": row[7],
    }


@router.delete("/sessions/{session_id}", dependencies=[Depends(verify_api_key)])
def delete_session(session_id: str):
    try:
        with get_conn() as conn:
            with conn.transaction():
                with conn.cursor() as cur:
                    cur.execute("""
                        UPDATE sessions
                        SET
                            deleted_at = now(),
                            deleted_reason = 'manual',
                            revision = revision + 1
                        WHERE id = %s
                          AND deleted_at IS NULL
                        RETURNING id;
                    """, (session_id,))
                    session_row = cur.fetchone()

                    if session_row:
                        cur.execute("""
                            UPDATE activities
                            SET
                                deleted_at = now(),
                                deleted_reason = 'cascade'
                            WHERE session_id = %s
                              AND deleted_at IS NULL;
                        """, (session_id,))
                        cur.execute("""
                            UPDATE records
                            SET
                                deleted_at = now(),
                                deleted_reason = 'cascade'
                            WHERE activity_id IN (
                                SELECT id
                                FROM activities
                                WHERE session_id = %s
                            )
                              AND deleted_at IS NULL;
                        """, (session_id,))

        if not session_row:
            raise HTTPException(status_code=404, detail="Session not found")

        return Response(status_code=204)

    except HTTPException:
        raise
    except Exception:
        logger.error("FAILED TO DELETE SESSION")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail="Session deletion failed")


@router.post("/sessions/{session_id}/restore", dependencies=[Depends(verify_api_key)])
def restore_session(session_id: str):
    try:
        with get_conn() as conn:
            with conn.transaction():
                with conn.cursor() as cur:
                    cur.execute("""
                        UPDATE sessions
                        SET
                            deleted_at = NULL,
                            deleted_reason = NULL,
                            revision = revision + 1
                        WHERE id = %s
                        RETURNING id;
                    """, (session_id,))
                    session_row = cur.fetchone()

                    if session_row:
                        cur.execute("""
                            UPDATE activities
                            SET
                                deleted_at = NULL,
                                deleted_reason = NULL
                            WHERE session_id = %s
                              AND deleted_reason = 'cascade';
                        """, (session_id,))
                        cur.execute("""
                            UPDATE records
                            SET
                                deleted_at = NULL,
                                deleted_reason = NULL
                            WHERE activity_id IN (
                                SELECT id
                                FROM activities
                                WHERE session_id = %s
                            )
                              AND deleted_reason = 'cascade';
                        """, (session_id,))

        if not session_row:
            raise HTTPException(status_code=404, detail="Session not found")

        return {"session_id": session_id, "status": "restored"}

    except HTTPException:
        raise
    except Exception:
        logger.error("FAILED TO RESTORE SESSION")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail="Session restore failed")
