import logging
import traceback
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from psycopg.types.json import Json

from Exercise_Libraray import normalize_exercise_name
from db import get_conn
from dependencies import verify_api_key
from models.activity import ActivityCreate, ActivityOut

logger = logging.getLogger("life-api")

router = APIRouter()


@router.post("/activities", dependencies=[Depends(verify_api_key)])
def create_activity(activity: ActivityCreate):
    if activity.type.lower() == "task":
        raise HTTPException(400, "Tasks should not be created as activities")
    activity.type = activity.type.lower().strip()
    activity.name = normalize_exercise_name(activity.name)

    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT id FROM sessions
                    WHERE id = %s AND deleted_at IS NULL FOR UPDATE;
                """, (activity.session_id,))
                if cur.fetchone() is None:
                    raise HTTPException(status_code=404, detail="Session not found")
                cur.execute("""
                    INSERT INTO activities (session_id, type, name, metadata)
                    VALUES (%s, %s, %s, %s)
                    RETURNING id;
                """, (
                    activity.session_id,
                    activity.type,
                    activity.name,
                    Json(activity.metadata) if activity.metadata is not None else None,
                ))
                activity_id = cur.fetchone()[0]
                cur.execute("""
                    UPDATE sessions SET revision = revision + 1
                    WHERE id = %s AND type = 'workout';
                """, (activity.session_id,))
            conn.commit()

        return {"activity_id": activity_id}

    except HTTPException:
        raise
    except Exception:
        logger.error("FAILED TO CREATE ACTIVITY")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail="Activity creation failed")


@router.get(
    "/sessions/{session_id}/activities",
    response_model=List[ActivityOut],
    dependencies=[Depends(verify_api_key)],
)
def get_activities_for_session(
    session_id: str,
    include_deleted: bool = Query(False),
):
    query = """
        SELECT id, session_id, type, name, metadata
        FROM activities
        WHERE session_id = %s
    """
    params = [session_id]

    if not include_deleted:
        query += " AND deleted_at IS NULL"

    query += " ORDER BY id"

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            rows = cur.fetchall()

    return [
        {
            "id": str(r[0]),
            "session_id": str(r[1]),
            "type": r[2],
            "name": r[3],
            "metadata": r[4],
        }
        for r in rows
    ]


@router.delete("/activities/{activity_id}", dependencies=[Depends(verify_api_key)])
def delete_activity(activity_id: str):
    try:
        with get_conn() as conn:
            with conn.transaction():
                with conn.cursor() as cur:
                    cur.execute("SELECT session_id FROM activities WHERE id = %s;", (activity_id,))
                    parent = cur.fetchone()
                    if parent is None:
                        raise HTTPException(status_code=404, detail="Activity not found")
                    cur.execute("""
                        SELECT id FROM sessions
                        WHERE id = %s AND deleted_at IS NULL FOR UPDATE;
                    """, (parent[0],))
                    if cur.fetchone() is None:
                        raise HTTPException(status_code=404, detail="Session not found")
                    cur.execute("""
                        UPDATE activities
                        SET
                            deleted_at = now(),
                            deleted_reason = 'manual'
                        WHERE id = %s
                          AND deleted_at IS NULL
                        RETURNING session_id;
                    """, (activity_id,))
                    row = cur.fetchone()
                    if row:
                        cur.execute("""
                            UPDATE sessions SET revision = revision + 1
                            WHERE id = %s AND type = 'workout';
                        """, (row[0],))

        if not row:
            raise HTTPException(status_code=404, detail="Activity not found")

        return Response(status_code=204)

    except HTTPException:
        raise
    except Exception:
        logger.error("FAILED TO DELETE ACTIVITY")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail="Activity deletion failed")
