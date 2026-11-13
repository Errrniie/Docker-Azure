import logging
import traceback
import hashlib
import json
from datetime import datetime, timezone
from typing import List

import psycopg
from fastapi import APIRouter, Depends, HTTPException, Query, Response

from db import get_conn
from dependencies import verify_api_key
from models.task import TaskCreate, TaskOut, TaskUpdate

logger = logging.getLogger("life-api")

router = APIRouter()


@router.post("/tasks", dependencies=[Depends(verify_api_key)])
def create_task(task: TaskCreate):
    if not task.title.strip():
        raise HTTPException(status_code=422, detail="Task title cannot be empty")
    request_hash = None
    if task.client_request_id is not None:
        request_hash = hashlib.sha256(json.dumps(
            task.model_dump(mode="json", exclude={"client_request_id"}),
            sort_keys=True, separators=(",", ":"),
        ).encode("utf-8")).hexdigest()
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO tasks (
                        title,
                        description,
                        category,
                        priority,
                        due_at,
                        due_date,
                        session_id,
                        status,
                        completed_at,
                        client_request_id,
                        request_hash
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id;
                """, (
                    task.title,
                    task.description,
                    task.category,
                    task.priority,
                    task.due_at,
                    task.due_date,
                    task.session_id,
                    "completed" if task.completed else "pending",
                    datetime.now(timezone.utc) if task.completed else None,
                    task.client_request_id,
                    request_hash,
                ))
                task_id = cur.fetchone()[0]
            conn.commit()

        return {"task_id": task_id, "reused": False}

    except psycopg.errors.UniqueViolation:
        if task.client_request_id is not None:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT id, request_hash, deleted_at
                        FROM tasks WHERE client_request_id = %s;
                    """, (task.client_request_id,))
                    existing = cur.fetchone()
            if existing and existing[1] == request_hash and existing[2] is None:
                return {"task_id": existing[0], "reused": True}
        raise HTTPException(status_code=409, detail="Task request ID was already used")
    except HTTPException:
        raise
    except Exception:
        logger.error("FAILED TO CREATE TASK")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail="Task creation failed")


@router.get("/tasks", response_model=List[TaskOut], dependencies=[Depends(verify_api_key)])
def get_tasks(
    status: str | None = Query(None),
    category: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    include_deleted: bool = Query(False),
):
    query = """
        SELECT
            id,
            title,
            description,
            category,
            status,
            priority,
            due_at,
            completed_at,
            created_at,
            session_id,
            updated_at,
            deleted_at,
            revision,
            client_request_id,
            due_date
        FROM tasks
    """
    params = []

    conditions = []

    if not include_deleted:
        conditions.append("deleted_at IS NULL")

    if status:
        conditions.append("status = %s")
        params.append(status)

    if category:
        conditions.append("category = %s")
        params.append(category)

    if conditions:
        query += " WHERE " + " AND ".join(conditions)


    query += " ORDER BY created_at DESC, id DESC LIMIT %s OFFSET %s"
    params.extend([limit, offset])

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            rows = cur.fetchall()

    return [
        {
            "id": str(r[0]),
            "title": r[1],
            "description": r[2],
            "category": r[3],
            "status": r[4],
            "priority": r[5],
            "due_at": r[6],
            "completed_at": r[7],
            "created_at": r[8],
            "session_id": str(r[9]) if r[9] is not None else None,
            "updated_at": r[10],
            "deleted_at": r[11],
            "revision": r[12],
            "client_request_id": r[13],
            "due_date": r[14],
        }
        for r in rows
    ]


@router.patch("/tasks/{task_id}", response_model=TaskOut, dependencies=[Depends(verify_api_key)])
def update_task(task_id: str, update: TaskUpdate):
    """Update task details while leaving completion and deletion to their own routes."""
    values = update.model_dump(exclude_unset=True)
    expected_revision = values.pop("expected_revision", None)
    if not values:
        raise HTTPException(status_code=400, detail="No fields provided for update")
    if "title" in values and (values["title"] is None or not values["title"].strip()):
        raise HTTPException(status_code=422, detail="Task title cannot be empty")

    columns = ("title", "description", "category", "priority", "due_at", "due_date")
    clauses = [f"{column} = %s" for column in columns if column in values]
    params = [values[column] for column in columns if column in values]
    params.append(task_id)
    revision_condition = ""
    if expected_revision is not None:
        revision_condition = " AND revision = %s"
        params.append(expected_revision)

    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(f"""
                    UPDATE tasks
                    SET {", ".join(clauses)}, updated_at = now(), revision = revision + 1
                    WHERE id = %s AND deleted_at IS NULL {revision_condition}
                    RETURNING id, title, description, category, status, priority,
                              due_at, completed_at, created_at, session_id,
                              updated_at, deleted_at, revision, client_request_id,
                              due_date;
                """, params)
                row = cur.fetchone()
                if row is None:
                    cur.execute("SELECT 1 FROM tasks WHERE id = %s AND deleted_at IS NULL", (task_id,))
                    exists = cur.fetchone() is not None
            conn.commit()
    except Exception:
        logger.error("FAILED TO UPDATE TASK")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail="Task update failed")

    if not row:
        if exists and expected_revision is not None:
            raise HTTPException(status_code=409, detail="Task changed on another device")
        raise HTTPException(status_code=404, detail="Task not found")
    return {
        "id": str(row[0]), "title": row[1], "description": row[2],
        "category": row[3], "status": row[4], "priority": row[5],
        "due_at": row[6], "completed_at": row[7], "created_at": row[8],
        "session_id": str(row[9]) if row[9] is not None else None,
        "updated_at": row[10], "deleted_at": row[11], "revision": row[12],
        "client_request_id": row[13],
        "due_date": row[14],
    }

@router.post("/tasks/{task_id}/complete", dependencies=[Depends(verify_api_key)])
def complete_task(task_id: str, expected_revision: int | None = Query(None, ge=1)):
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE tasks
                    SET
                        status = 'completed',
                        completed_at = now(),
                        updated_at = now(),
                        revision = revision + 1
                    WHERE id = %s
                      AND deleted_at IS NULL
                      AND (%s IS NULL OR revision = %s)
                    RETURNING id;
                """, (task_id, expected_revision, expected_revision))
                row = cur.fetchone()
                if row is None:
                    cur.execute("SELECT 1 FROM tasks WHERE id = %s AND deleted_at IS NULL", (task_id,))
                    exists = cur.fetchone() is not None
            conn.commit()

        if not row:
            if exists and expected_revision is not None:
                raise HTTPException(status_code=409, detail="Task changed on another device")
            raise HTTPException(status_code=404, detail="Task not found")

        return {"task_id": task_id, "status": "completed"}

    except HTTPException:
        raise
    except Exception:
        logger.error("FAILED TO COMPLETE TASK")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail="Task completion failed")

@router.post("/tasks/{task_id}/reopen", dependencies=[Depends(verify_api_key)])
def reopen_task(task_id: str, expected_revision: int | None = Query(None, ge=1)):
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE tasks
                    SET
                        status = 'pending',
                        completed_at = NULL,
                        updated_at = now(),
                        revision = revision + 1
                    WHERE id = %s
                      AND deleted_at IS NULL
                      AND (%s IS NULL OR revision = %s)
                    RETURNING id;
                """, (task_id, expected_revision, expected_revision))
                row = cur.fetchone()
                if row is None:
                    cur.execute("SELECT 1 FROM tasks WHERE id = %s AND deleted_at IS NULL", (task_id,))
                    exists = cur.fetchone() is not None
            conn.commit()

        if not row:
            if exists and expected_revision is not None:
                raise HTTPException(status_code=409, detail="Task changed on another device")
            raise HTTPException(status_code=404, detail="Task not found")

        return {"task_id": task_id, "status": "pending"}

    except HTTPException:
        raise
    except Exception:
        logger.error("FAILED TO REOPEN TASK")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail="Task reopen failed")

@router.delete("/tasks/{task_id}", dependencies=[Depends(verify_api_key)])
def delete_task(task_id: str, expected_revision: int | None = Query(None, ge=1)):
    try:
        with get_conn() as conn:
            with conn.transaction():
                with conn.cursor() as cur:
                    cur.execute("""
                        UPDATE tasks
                        SET
                            deleted_at = now(),
                            deleted_reason = 'manual',
                            updated_at = now(),
                            revision = revision + 1
                        WHERE id = %s
                          AND deleted_at IS NULL
                          AND (%s IS NULL OR revision = %s)
                        RETURNING id;
                    """, (task_id, expected_revision, expected_revision))
                    row = cur.fetchone()
                    if row is None:
                        cur.execute("SELECT 1 FROM tasks WHERE id = %s AND deleted_at IS NULL", (task_id,))
                        exists = cur.fetchone() is not None

        if not row:
            if exists and expected_revision is not None:
                raise HTTPException(status_code=409, detail="Task changed on another device")
            raise HTTPException(status_code=404, detail="Task not found")

        return Response(status_code=204)

    except HTTPException:
        raise
    except Exception:
        logger.error("FAILED TO DELETE TASK")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail="Task deletion failed")


@router.post("/tasks/{task_id}/restore", dependencies=[Depends(verify_api_key)])
def restore_task(task_id: str):
    try:
        with get_conn() as conn:
            with conn.transaction():
                with conn.cursor() as cur:
                    cur.execute("""
                        UPDATE tasks
                        SET
                            deleted_at = NULL,
                            deleted_reason = NULL,
                            updated_at = now(),
                            revision = revision + 1
                        WHERE id = %s
                        RETURNING id;
                    """, (task_id,))
                    row = cur.fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="Task not found")

        return {"task_id": task_id, "status": "restored"}

    except HTTPException:
        raise
    except Exception:
        logger.error("FAILED TO RESTORE TASK")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail="Task restore failed")
