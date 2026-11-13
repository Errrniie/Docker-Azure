import logging
import traceback
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from psycopg.types.json import Json

from db import get_conn
from dependencies import verify_api_key
from models.record import RecordCreate, RecordOut, RecordUpdate

logger = logging.getLogger("life-api")

router = APIRouter()


def _lock_activity_parent(cur, activity_id: str):
    """Serialize child writes with a full workout replacement."""
    cur.execute("SELECT session_id FROM activities WHERE id = %s;", (activity_id,))
    row = cur.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Activity not found")
    cur.execute("""
        SELECT id FROM sessions WHERE id = %s AND deleted_at IS NULL FOR UPDATE;
    """, (row[0],))
    if cur.fetchone() is None:
        raise HTTPException(status_code=404, detail="Session not found")
    cur.execute("SELECT 1 FROM activities WHERE id = %s AND deleted_at IS NULL;", (activity_id,))
    if cur.fetchone() is None:
        raise HTTPException(status_code=409, detail="Activity changed; reload before saving")


def _lock_record_parent(cur, record_id: str):
    cur.execute("SELECT activity_id FROM records WHERE id = %s;", (record_id,))
    row = cur.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Record not found")
    _lock_activity_parent(cur, row[0])
    cur.execute("SELECT 1 FROM records WHERE id = %s AND deleted_at IS NULL;", (record_id,))
    if cur.fetchone() is None:
        raise HTTPException(status_code=409, detail="Record changed; reload before saving")


@router.post("/records", dependencies=[Depends(verify_api_key)])
def create_record(record: RecordCreate):
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                _lock_activity_parent(cur, record.activity_id)
                cur.execute("""
                    INSERT INTO records (activity_id, data)
                    VALUES (%s, %s)
                    RETURNING id;
                """, (
                    record.activity_id,
                    Json(record.data),
                ))
                record_id = cur.fetchone()[0]
                cur.execute("""
                    UPDATE sessions SET revision = revision + 1
                    WHERE id = (SELECT session_id FROM activities WHERE id = %s)
                      AND type = 'workout';
                """, (record.activity_id,))
            conn.commit()

        return {"record_id": record_id}

    except HTTPException:
        raise
    except Exception:
        logger.error("FAILED TO CREATE RECORD")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail="Record creation failed")


@router.get(
    "/activities/{activity_id}/records",
    response_model=List[RecordOut],
    dependencies=[Depends(verify_api_key)],
)
def get_records_for_activity(
    activity_id: str,
    include_deleted: bool = Query(False),
):
    query = """
        SELECT id, activity_id, record_time, data
        FROM records
        WHERE activity_id = %s
    """
    params = [activity_id]

    if not include_deleted:
        query += " AND deleted_at IS NULL"

    query += " ORDER BY record_time"

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            rows = cur.fetchall()

    return [
        {
            "id": str(r[0]),
            "activity_id": str(r[1]),
            "record_time": r[2],
            "data": r[3],
        }
        for r in rows
    ]


@router.patch("/records/{record_id}", dependencies=[Depends(verify_api_key)])
def update_record(record_id: str, update: RecordUpdate):
    """Replace a live record's data without changing its stable ID or timestamp."""
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                _lock_record_parent(cur, record_id)
                cur.execute("""
                    UPDATE records
                    SET data = %s
                    WHERE id = %s AND deleted_at IS NULL
                    RETURNING activity_id;
                """, (Json(update.data), record_id))
                row = cur.fetchone()
                if row:
                    cur.execute("""
                        UPDATE sessions SET revision = revision + 1
                        WHERE id = (SELECT session_id FROM activities WHERE id = %s)
                          AND type = 'workout';
                    """, (row[0],))
            conn.commit()
    except HTTPException:
        raise
    except Exception:
        logger.error("FAILED TO UPDATE RECORD")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail="Record update failed")

    if row is None:
        raise HTTPException(status_code=404, detail="Record not found")
    return {"record_id": record_id}


@router.delete("/records/{record_id}", dependencies=[Depends(verify_api_key)])
def delete_record(record_id: str):
    try:
        with get_conn() as conn:
            with conn.transaction():
                with conn.cursor() as cur:
                    _lock_record_parent(cur, record_id)
                    cur.execute("""
                        UPDATE records
                        SET
                            deleted_at = now(),
                            deleted_reason = 'manual'
                        WHERE id = %s
                          AND deleted_at IS NULL
                        RETURNING activity_id;
                    """, (record_id,))
                    row = cur.fetchone()
                    if row:
                        cur.execute("""
                            UPDATE sessions SET revision = revision + 1
                            WHERE id = (SELECT session_id FROM activities WHERE id = %s)
                              AND type = 'workout';
                        """, (row[0],))

        if not row:
            raise HTTPException(status_code=404, detail="Record not found")

        return Response(status_code=204)

    except HTTPException:
        raise
    except Exception:
        logger.error("FAILED TO DELETE RECORD")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail="Record deletion failed")
