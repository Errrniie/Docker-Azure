import logging
import traceback
from datetime import date
from typing import List

import psycopg
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from psycopg.types.json import Json

from db import get_conn
from dependencies import verify_api_key
from models.journal import (
    JournalEntryCreate,
    JournalEntryOut,
    JournalEntryUpdate,
    JournalEntryWithPagesOut,
    JournalPageCreate,
    JournalPageOut,
    JournalPageTypeCreate,
    JournalPageTypeOut,
    JournalPageUpdate,
)

logger = logging.getLogger("life-api")

router = APIRouter()


def _normalize_type_key(value: str) -> str:
    return value.lower().strip().replace(" ", "_")


def _entry_row_to_dict(row) -> dict:
    return {
        "id": str(row[0]),
        "entry_date": row[1],
        "mood": row[2],
        "metadata": row[3],
        "created_at": row[4],
        "updated_at": row[5],
    }


def _page_row_to_dict(row) -> dict:
    return {
        "id": str(row[0]),
        "journal_entry_id": str(row[1]),
        "page_type": row[2],
        "title": row[3],
        "content": row[4],
        "metadata": row[5],
        "page_order": row[6],
        "created_at": row[7],
        "updated_at": row[8],
        "revision": row[9],
    }


def _page_type_row_to_dict(row) -> dict:
    return {
        "type_key": row[0],
        "display_name": row[1],
        "page_order": row[2],
        "created_at": row[3],
        "updated_at": row[4],
    }


def _fetch_entry(
    cur,
    journal_entry_id: str,
    include_deleted: bool = False,
) -> dict | None:
    query = """
        SELECT id, entry_date, mood, metadata, created_at, updated_at
        FROM journal_entries
        WHERE id = %s
    """
    params = [journal_entry_id]

    if not include_deleted:
        query += " AND deleted_at IS NULL"

    cur.execute(query, params)
    row = cur.fetchone()
    if not row:
        return None
    return _entry_row_to_dict(row)


def _fetch_pages_for_entry(
    cur,
    journal_entry_id: str,
    include_deleted: bool = False,
) -> list[dict]:
    query = """
        SELECT
            id,
            journal_entry_id,
            page_type,
            title,
            content,
            metadata,
            page_order,
            created_at,
            updated_at,
            revision
        FROM journal_pages
        WHERE journal_entry_id = %s
    """
    params = [journal_entry_id]

    if not include_deleted:
        query += " AND deleted_at IS NULL"

    query += " ORDER BY page_order ASC, created_at ASC"

    cur.execute(query, params)
    return [_page_row_to_dict(row) for row in cur.fetchall()]


@router.post("/journal/entries", dependencies=[Depends(verify_api_key)])
def create_journal_entry(entry: JournalEntryCreate):
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO journal_entries (entry_date, mood, metadata)
                    VALUES (%s, %s, %s)
                    RETURNING id;
                """, (
                    entry.entry_date,
                    entry.mood,
                    Json(entry.metadata) if entry.metadata is not None else None,
                ))
                journal_entry_id = cur.fetchone()[0]
            conn.commit()

        return {"journal_entry_id": journal_entry_id}

    except psycopg.errors.UniqueViolation:
        raise HTTPException(
            status_code=409,
            detail="Journal entry already exists for this date",
        )
    except HTTPException:
        raise
    except Exception:
        logger.error("FAILED TO CREATE JOURNAL ENTRY")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail="Journal entry creation failed")


@router.patch(
    "/journal/entries/{journal_entry_id}",
    response_model=JournalEntryOut,
    dependencies=[Depends(verify_api_key)],
)
def update_journal_entry(journal_entry_id: str, entry: JournalEntryUpdate):
    updates = entry.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields provided for update")

    set_clauses = ["updated_at = now()"]
    params = []

    if "mood" in updates:
        set_clauses.append("mood = %s")
        params.append(updates["mood"])
    if "metadata" in updates:
        set_clauses.append("metadata = %s")
        params.append(Json(updates["metadata"]) if updates["metadata"] is not None else None)

    params.append(journal_entry_id)

    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(f"""
                    UPDATE journal_entries
                    SET {", ".join(set_clauses)}
                    WHERE id = %s
                      AND deleted_at IS NULL
                    RETURNING id, entry_date, mood, metadata, created_at, updated_at;
                """, params)
                row = cur.fetchone()
            conn.commit()

        if not row:
            raise HTTPException(status_code=404, detail="Journal entry not found")

        return _entry_row_to_dict(row)

    except HTTPException:
        raise
    except Exception:
        logger.error("FAILED TO UPDATE JOURNAL ENTRY")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail="Journal entry update failed")


@router.delete(
    "/journal/entries/{journal_entry_id}",
    dependencies=[Depends(verify_api_key)],
)
def delete_journal_entry(journal_entry_id: str):
    try:
        with get_conn() as conn:
            with conn.transaction():
                with conn.cursor() as cur:
                    cur.execute("""
                        UPDATE journal_entries
                        SET
                            deleted_at = now(),
                            deleted_reason = 'manual',
                            updated_at = now()
                        WHERE id = %s
                          AND deleted_at IS NULL
                        RETURNING id;
                    """, (journal_entry_id,))
                    entry_row = cur.fetchone()

                    if entry_row:
                        cur.execute("""
                            UPDATE journal_pages
                            SET
                                deleted_at = now(),
                                deleted_reason = 'cascade',
                                updated_at = now(),
                                revision = revision + 1
                            WHERE journal_entry_id = %s
                              AND deleted_at IS NULL;
                        """, (journal_entry_id,))

        if not entry_row:
            raise HTTPException(status_code=404, detail="Journal entry not found")

        return Response(status_code=204)

    except HTTPException:
        raise
    except Exception:
        logger.error("FAILED TO DELETE JOURNAL ENTRY")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail="Journal entry deletion failed")


@router.post(
    "/journal/entries/{journal_entry_id}/restore",
    dependencies=[Depends(verify_api_key)],
)
def restore_journal_entry(journal_entry_id: str):
    try:
        with get_conn() as conn:
            with conn.transaction():
                with conn.cursor() as cur:
                    cur.execute("""
                        UPDATE journal_entries
                        SET
                            deleted_at = NULL,
                            deleted_reason = NULL,
                            updated_at = now()
                        WHERE id = %s
                          AND deleted_at IS NOT NULL
                        RETURNING id;
                    """, (journal_entry_id,))
                    entry_row = cur.fetchone()

                    if entry_row:
                        cur.execute("""
                            UPDATE journal_pages
                            SET
                                deleted_at = NULL,
                                deleted_reason = NULL,
                                updated_at = now(),
                                revision = revision + 1
                            WHERE journal_entry_id = %s
                              AND deleted_reason = 'cascade';
                        """, (journal_entry_id,))

        if not entry_row:
            raise HTTPException(status_code=404, detail="Journal entry not found")

        return {"journal_entry_id": journal_entry_id, "status": "restored"}

    except HTTPException:
        raise
    except Exception:
        logger.error("FAILED TO RESTORE JOURNAL ENTRY")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail="Journal entry restore failed")


@router.post("/journal/pages", dependencies=[Depends(verify_api_key)])
def create_journal_page(page: JournalPageCreate):
    page_type = _normalize_type_key(page.page_type)

    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT type_key
                    FROM journal_page_types
                    WHERE type_key = %s
                      AND deleted_at IS NULL;
                """, (page_type,))
                if not cur.fetchone():
                    raise HTTPException(status_code=400, detail="Invalid page_type")

                cur.execute("""
                    SELECT id
                    FROM journal_entries
                    WHERE id = %s
                      AND deleted_at IS NULL;
                """, (page.journal_entry_id,))
                parent_row = cur.fetchone()

                if not parent_row:
                    raise HTTPException(status_code=404, detail="Journal entry not found")

                cur.execute("""
                    INSERT INTO journal_pages (
                        journal_entry_id,
                        page_type,
                        title,
                        content,
                        metadata,
                        page_order
                    )
                    VALUES (%s, %s, %s, %s, %s, %s)
                    RETURNING id;
                """, (
                    page.journal_entry_id,
                    page_type,
                    page.title,
                    page.content,
                    Json(page.metadata) if page.metadata is not None else None,
                    page.page_order,
                ))
                journal_page_id = cur.fetchone()[0]
            conn.commit()

        return {"journal_page_id": journal_page_id}

    except psycopg.errors.UniqueViolation:
        raise HTTPException(
            status_code=409,
            detail="Journal page type already exists for this journal entry",
        )
    except HTTPException:
        raise
    except Exception:
        logger.error("FAILED TO CREATE JOURNAL PAGE")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail="Journal page creation failed")


@router.patch(
    "/journal/pages/{journal_page_id}",
    response_model=JournalPageOut,
    dependencies=[Depends(verify_api_key)],
)
def update_journal_page(journal_page_id: str, page_update: JournalPageUpdate):
    updates = page_update.model_dump(exclude_unset=True)
    expected_revision = updates.pop("expected_revision", None)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields provided for update")
    if "content" in updates and updates["content"] is None:
        raise HTTPException(status_code=422, detail="Journal page content cannot be null")
    if "page_order" in updates and updates["page_order"] is None:
        raise HTTPException(status_code=422, detail="Journal page order cannot be null")

    set_clauses = ["updated_at = now()", "revision = revision + 1"]
    params = []

    if "title" in updates:
        set_clauses.append("title = %s")
        params.append(updates["title"])
    if "content" in updates:
        set_clauses.append("content = %s")
        params.append(updates["content"])
    if "metadata" in updates:
        set_clauses.append("metadata = %s")
        params.append(Json(updates["metadata"]) if updates["metadata"] is not None else None)
    if "page_order" in updates:
        set_clauses.append("page_order = %s")
        params.append(updates["page_order"])

    params.append(journal_page_id)
    revision_condition = ""
    if expected_revision is not None:
        revision_condition = " AND revision = %s"
        params.append(expected_revision)

    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(f"""
                    UPDATE journal_pages
                    SET {", ".join(set_clauses)}
                    WHERE id = %s
                      AND deleted_at IS NULL
                      {revision_condition}
                    RETURNING
                        id,
                        journal_entry_id,
                        page_type,
                        title,
                        content,
                        metadata,
                        page_order,
                        created_at,
                        updated_at,
                        revision;
                """, params)
                row = cur.fetchone()
                if row is None:
                    cur.execute("SELECT 1 FROM journal_pages WHERE id = %s AND deleted_at IS NULL", (journal_page_id,))
                    exists = cur.fetchone() is not None
            conn.commit()

        if not row:
            if exists and expected_revision is not None:
                raise HTTPException(status_code=409, detail="Journal page changed on another device")
            raise HTTPException(status_code=404, detail="Journal page not found")

        return _page_row_to_dict(row)

    except HTTPException:
        raise
    except Exception:
        logger.error("FAILED TO UPDATE JOURNAL PAGE")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail="Journal page update failed")


@router.get(
    "/journal/entries",
    response_model=List[JournalEntryOut],
    dependencies=[Depends(verify_api_key)],
)
def get_journal_entries(
    start: date | None = None,
    end: date | None = None,
    limit: int = Query(50, ge=1, le=200),
    include_deleted: bool = Query(False),
):
    query = """
        SELECT id, entry_date, mood, metadata, created_at, updated_at
        FROM journal_entries
    """
    params = []
    conditions = []

    if not include_deleted:
        conditions.append("deleted_at IS NULL")

    if start and end:
        conditions.append("entry_date BETWEEN %s AND %s")
        params.extend([start, end])
    elif start:
        conditions.append("entry_date >= %s")
        params.append(start)
    elif end:
        conditions.append("entry_date <= %s")
        params.append(end)

    if conditions:
        query += " WHERE " + " AND ".join(conditions)

    query += " ORDER BY entry_date DESC LIMIT %s"
    params.append(limit)

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            rows = cur.fetchall()

    return [_entry_row_to_dict(row) for row in rows]


@router.get(
    "/journal/entries/{journal_entry_id}",
    response_model=JournalEntryWithPagesOut,
    dependencies=[Depends(verify_api_key)],
)
def get_journal_entry(
    journal_entry_id: str,
    include_deleted: bool = Query(False),
):
    with get_conn() as conn:
        with conn.cursor() as cur:
            entry = _fetch_entry(cur, journal_entry_id, include_deleted=include_deleted)

            if not entry:
                raise HTTPException(status_code=404, detail="Journal entry not found")

            entry["pages"] = _fetch_pages_for_entry(
                cur,
                journal_entry_id,
                include_deleted=include_deleted,
            )

    return entry


@router.get(
    "/journal/by-date/{entry_date}",
    response_model=JournalEntryWithPagesOut,
    dependencies=[Depends(verify_api_key)],
)
def get_journal_by_date(
    entry_date: date,
    include_deleted: bool = Query(False),
):
    with get_conn() as conn:
        with conn.cursor() as cur:
            query = """
                SELECT id, entry_date, mood, metadata, created_at, updated_at
                FROM journal_entries
                WHERE entry_date = %s
            """
            params = [entry_date]

            if not include_deleted:
                query += " AND deleted_at IS NULL"

            cur.execute(query, params)
            row = cur.fetchone()

            if not row:
                raise HTTPException(status_code=404, detail="Journal entry not found")

            entry = _entry_row_to_dict(row)
            entry["pages"] = _fetch_pages_for_entry(
                cur,
                entry["id"],
                include_deleted=include_deleted,
            )

    return entry


@router.get(
    "/journal/entries/{journal_entry_id}/pages",
    response_model=List[JournalPageOut],
    dependencies=[Depends(verify_api_key)],
)
def get_journal_pages_for_entry(
    journal_entry_id: str,
    include_deleted: bool = Query(False),
):
    with get_conn() as conn:
        with conn.cursor() as cur:
            entry = _fetch_entry(cur, journal_entry_id, include_deleted=include_deleted)

            if not entry:
                raise HTTPException(status_code=404, detail="Journal entry not found")

            pages = _fetch_pages_for_entry(
                cur,
                journal_entry_id,
                include_deleted=include_deleted,
            )

    return pages


@router.post("/journal/page-types", dependencies=[Depends(verify_api_key)])
def create_journal_page_type(page_type: JournalPageTypeCreate):
    type_key = _normalize_type_key(page_type.type_key)
    display_name = page_type.display_name.strip()

    if not type_key:
        raise HTTPException(status_code=400, detail="Invalid type_key")
    if not display_name:
        raise HTTPException(status_code=400, detail="Invalid display_name")

    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT deleted_at
                    FROM journal_page_types
                    WHERE type_key = %s;
                """, (type_key,))
                existing = cur.fetchone()

                if existing:
                    if existing[0] is None:
                        raise HTTPException(
                            status_code=409,
                            detail="Journal page type already exists",
                        )

                    cur.execute("""
                        UPDATE journal_page_types
                        SET
                            deleted_at = NULL,
                            deleted_reason = NULL,
                            display_name = %s,
                            page_order = %s,
                            updated_at = now()
                        WHERE type_key = %s
                        RETURNING type_key;
                    """, (display_name, page_type.page_order, type_key))
                else:
                    cur.execute("""
                        INSERT INTO journal_page_types (type_key, display_name, page_order)
                        VALUES (%s, %s, %s)
                        RETURNING type_key;
                    """, (type_key, display_name, page_type.page_order))

                cur.fetchone()
            conn.commit()

        return {"type_key": type_key}

    except HTTPException:
        raise
    except Exception:
        logger.error("FAILED TO CREATE JOURNAL PAGE TYPE")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail="Journal page type creation failed")


@router.get(
    "/journal/page-types",
    response_model=List[JournalPageTypeOut],
    dependencies=[Depends(verify_api_key)],
)
def get_journal_page_types(include_deleted: bool = Query(False)):
    query = """
        SELECT type_key, display_name, page_order, created_at, updated_at
        FROM journal_page_types
    """
    params = []

    if not include_deleted:
        query += " WHERE deleted_at IS NULL"

    query += " ORDER BY page_order ASC, type_key ASC"

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            rows = cur.fetchall()

    return [_page_type_row_to_dict(row) for row in rows]


@router.delete(
    "/journal/page-types/{type_key}",
    dependencies=[Depends(verify_api_key)],
)
def delete_journal_page_type(type_key: str):
    normalized_type_key = _normalize_type_key(type_key)

    if normalized_type_key == "main":
        raise HTTPException(
            status_code=400,
            detail="The main page type cannot be deleted",
        )

    try:
        with get_conn() as conn:
            with conn.transaction():
                with conn.cursor() as cur:
                    cur.execute("""
                        UPDATE journal_page_types
                        SET
                            deleted_at = now(),
                            deleted_reason = 'manual',
                            updated_at = now()
                        WHERE type_key = %s
                          AND deleted_at IS NULL
                        RETURNING type_key;
                    """, (normalized_type_key,))
                    row = cur.fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="Journal page type not found")

        return Response(status_code=204)

    except HTTPException:
        raise
    except Exception:
        logger.error("FAILED TO DELETE JOURNAL PAGE TYPE")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail="Journal page type deletion failed")


@router.post(
    "/journal/page-types/{type_key}/restore",
    dependencies=[Depends(verify_api_key)],
)
def restore_journal_page_type(type_key: str):
    normalized_type_key = _normalize_type_key(type_key)

    try:
        with get_conn() as conn:
            with conn.transaction():
                with conn.cursor() as cur:
                    cur.execute("""
                        UPDATE journal_page_types
                        SET
                            deleted_at = NULL,
                            deleted_reason = NULL,
                            updated_at = now()
                        WHERE type_key = %s
                        RETURNING type_key;
                    """, (normalized_type_key,))
                    row = cur.fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="Journal page type not found")

        return {"type_key": normalized_type_key, "status": "restored"}

    except HTTPException:
        raise
    except Exception:
        logger.error("FAILED TO RESTORE JOURNAL PAGE TYPE")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail="Journal page type restore failed")


@router.delete(
    "/journal/pages/{journal_page_id}",
    dependencies=[Depends(verify_api_key)],
)
def delete_journal_page(journal_page_id: str,
                        expected_revision: int | None = Query(None, ge=1)):
    try:
        with get_conn() as conn:
            with conn.transaction():
                with conn.cursor() as cur:
                    cur.execute("""
                        UPDATE journal_pages
                        SET
                            deleted_at = now(),
                            deleted_reason = 'manual',
                            updated_at = now(),
                            revision = revision + 1
                        WHERE id = %s
                          AND deleted_at IS NULL
                          AND (%s IS NULL OR revision = %s)
                        RETURNING id;
                    """, (journal_page_id, expected_revision, expected_revision))
                    row = cur.fetchone()
                    if row is None:
                        cur.execute("SELECT 1 FROM journal_pages WHERE id = %s AND deleted_at IS NULL", (journal_page_id,))
                        exists = cur.fetchone() is not None

        if not row:
            if exists and expected_revision is not None:
                raise HTTPException(status_code=409, detail="Journal page changed on another device")
            raise HTTPException(status_code=404, detail="Journal page not found")

        return Response(status_code=204)

    except HTTPException:
        raise
    except Exception:
        logger.error("FAILED TO DELETE JOURNAL PAGE")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail="Journal page deletion failed")


@router.post(
    "/journal/pages/{journal_page_id}/restore",
    dependencies=[Depends(verify_api_key)],
)
def restore_journal_page(journal_page_id: str):
    try:
        with get_conn() as conn:
            with conn.transaction():
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT journal_entry_id, page_type
                        FROM journal_pages
                        WHERE id = %s;
                    """, (journal_page_id,))
                    page_row = cur.fetchone()

                    if not page_row:
                        raise HTTPException(status_code=404, detail="Journal page not found")

                    journal_entry_id, page_type = page_row

                    cur.execute("""
                        SELECT type_key
                        FROM journal_page_types
                        WHERE type_key = %s
                          AND deleted_at IS NULL;
                    """, (page_type,))
                    if not cur.fetchone():
                        raise HTTPException(
                            status_code=409,
                            detail="Journal page type is not active",
                        )

                    cur.execute("""
                        SELECT id
                        FROM journal_pages
                        WHERE journal_entry_id = %s
                          AND page_type = %s
                          AND deleted_at IS NULL
                          AND id != %s;
                    """, (journal_entry_id, page_type, journal_page_id))
                    if cur.fetchone():
                        raise HTTPException(
                            status_code=409,
                            detail="Journal page type already exists for this journal entry",
                        )

                    cur.execute("""
                        UPDATE journal_pages
                        SET
                            deleted_at = NULL,
                            deleted_reason = NULL,
                            updated_at = now(),
                            revision = revision + 1
                        WHERE id = %s
                        RETURNING id;
                    """, (journal_page_id,))
                    row = cur.fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="Journal page not found")

        return {"journal_page_id": journal_page_id, "status": "restored"}

    except psycopg.errors.UniqueViolation:
        raise HTTPException(
            status_code=409,
            detail="Journal page type already exists for this journal entry",
        )
    except HTTPException:
        raise
    except Exception:
        logger.error("FAILED TO RESTORE JOURNAL PAGE")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail="Journal page restore failed")
