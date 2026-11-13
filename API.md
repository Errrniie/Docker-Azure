# life-api — API reference

**Source of truth:** [`main.py`](main.py)

**Maintenance:** Update this file whenever you add, remove, or change an endpoint, request body, query parameter, response shape, or auth behavior in `main.py`.

---

## Overview

| Item | Value |
|------|--------|
| Framework | FastAPI |
| Content-Type | `application/json` (for bodies) |
| Auth | Header `x-api-key` on all endpoints except `GET /health` |
| IDs | UUID strings in paths and JSON |
| Datetimes | ISO 8601 (e.g. `2026-05-27T21:00:00Z`) |

### Authentication

| Header | Required | Description |
|--------|----------|-------------|
| `x-api-key` | Yes (except `/health`) | Must match server env `API_KEY` |

**401 Unauthorized**

```json
{ "detail": "Unauthorized" }
```

### Common error shape

FastAPI returns errors as:

```json
{ "detail": "<message or validation errors>" }
```

---

## Endpoint index

| Method | Path | Auth |
|--------|------|------|
| GET | `/health` | No |
| GET | `/exercises` | Yes |
| POST | `/sessions` | Yes |
| POST | `/workouts` | Yes |
| PATCH | `/workouts/{session_id}` | Yes |
| GET | `/sessions` | Yes |
| GET | `/sessions/{session_id}` | Yes |
| DELETE | `/sessions/{session_id}` | Yes |
| POST | `/sessions/{session_id}/restore` | Yes |
| GET | `/workouts/full` | Yes |
| POST | `/activities` | Yes |
| GET | `/sessions/{session_id}/activities` | Yes |
| DELETE | `/activities/{activity_id}` | Yes |
| POST | `/records` | Yes |
| GET | `/activities/{activity_id}/records` | Yes |
| DELETE | `/records/{record_id}` | Yes |
| POST | `/tasks` | Yes |
| GET | `/tasks` | Yes |
| PATCH | `/tasks/{task_id}` | Yes |
| POST | `/tasks/{task_id}/complete` | Yes |
| POST | `/tasks/{task_id}/reopen` | Yes |
| DELETE | `/tasks/{task_id}` | Yes |
| POST | `/tasks/{task_id}/restore` | Yes |
| POST | `/journal/page-types` | Yes |
| GET | `/journal/page-types` | Yes |
| DELETE | `/journal/page-types/{type_key}` | Yes |
| POST | `/journal/page-types/{type_key}/restore` | Yes |
| POST | `/journal/entries` | Yes |
| PATCH | `/journal/entries/{journal_entry_id}` | Yes |
| DELETE | `/journal/entries/{journal_entry_id}` | Yes |
| POST | `/journal/entries/{journal_entry_id}/restore` | Yes |
| POST | `/journal/pages` | Yes |
| PATCH | `/journal/pages/{journal_page_id}` | Yes |
| DELETE | `/journal/pages/{journal_page_id}` | Yes |
| POST | `/journal/pages/{journal_page_id}/restore` | Yes |
| GET | `/journal/entries` | Yes |
| GET | `/journal/entries/{journal_entry_id}` | Yes |
| GET | `/journal/by-date/{entry_date}` | Yes |
| GET | `/journal/entries/{journal_entry_id}/pages` | Yes |

---

## Health

### `GET /health`

No authentication.

**Response `200`**

```json
{ "status": "ok" }
```

---

## Exercises

### `GET /exercises`

List exercises from the server-side exercise library.

**Query parameters**

| Param | Type | Default | Notes |
|-------|------|---------|-------|
| `equipment` | string | — | Filters by `equipment` field (case-insensitive input) |
| `muscle` | string | — | Matches membership in `primary_muscles` or `secondary_muscles` (case-insensitive input) |

**Response `200`**

JSON array of exercise objects. Shape depends on the library; fields commonly include:

- `name` (string)
- `equipment` (string)
- `primary_muscles` (string[])
- `secondary_muscles` (string[])
- `aliases` (string[])
- optional `attachments` (string[]) — commonly present on cable movements (e.g. `["rope"]`, `["straight_bar", "rope"]`)

---

## Sessions

### `POST /sessions`

Create a session.

**Request body**

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `type` | string | Yes | Stored lowercased and trimmed |
| `name` | string \| null | No | |
| `start_time` | datetime | Yes | |
| `end_time` | datetime \| null | No | Optional session end time |
| `source` | string \| null | No | Optional source such as phone, desktop, manual |
| `metadata` | object \| null | No | Optional session-level JSON |
| `notes` | string \| null | No | |

**Example request**

```json
{
  "type": "workout",
  "name": "Morning lift",
  "start_time": "2026-05-27T14:30:00Z",
  "end_time": "2026-05-27T15:30:00Z",
  "source": "phone",
  "metadata": {
    "location": "gym"
  },
  "notes": "Felt strong"
}
```

**Response `200`**

```json
{ "session_id": "550e8400-e29b-41d4-a716-446655440000" }
```

**Errors**

| Status | `detail` |
|--------|----------|
| 401 | Unauthorized |
| 500 | Session creation failed |

---

### `GET /sessions`

List sessions (newest `start_time` first).

**Query parameters**

| Param | Type | Default | Notes |
|-------|------|---------|-------|
| `type` | string | — | Filter; matched lowercased and trimmed |
| `limit` | int | 20 | Min 1, max 100 |
| `start` | datetime | — | `start_time >= start` (unless both `start` and `end` set) |
| `end` | datetime | — | `start_time <= end` (or `BETWEEN` when both set) |
| `include_deleted` | bool | false | Include soft-deleted rows |

**Response `200`** — array of:

| Field | Type |
|-------|------|
| `id` | string |
| `type` | string |
| `name` | string \| null |
| `start_time` | datetime |
| `end_time` | datetime \| null |
| `source` | string \| null |
| `metadata` | object \| null |
| `notes` | string \| null |

**Example response**

```json
[
  {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "type": "workout",
    "name": "Morning lift",
    "start_time": "2026-05-27T14:30:00Z",
    "end_time": "2026-05-27T15:30:00Z",
    "source": "phone",
    "metadata": {
      "location": "gym"
    },
    "notes": null
  }
]
```

---

### `GET /sessions/{session_id}`

Get one non-deleted session.

**Path parameters**

| Param | Type |
|-------|------|
| `session_id` | string (UUID) |

**Response `200`**

Same object shape as one item in `GET /sessions`.

**Errors**

| Status | `detail` |
|--------|----------|
| 404 | Session not found |

---

### `DELETE /sessions/{session_id}`

Soft-delete a session. Cascades: marks related activities and records deleted with `deleted_reason = 'cascade'`.

**Response `204`** — empty body

**Errors**

| Status | `detail` |
|--------|----------|
| 404 | Session not found |
| 500 | Session deletion failed |

---

### `POST /sessions/{session_id}/restore`

Restore a session and cascade-restored children (only rows with `deleted_reason = 'cascade'`).

**Response `200`**

```json
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "restored"
}
```

**Errors**

| Status | `detail` |
|--------|----------|
| 404 | Session not found |
| 500 | Session restore failed |

---

### `GET /workouts/full`

Nested export of all non-deleted workout sessions with activities and records.

**Response `200`** — array of:

```json
[
  {
    "session_id": "550e8400-e29b-41d4-a716-446655440000",
    "type": "workout",
    "name": "Morning lift",
    "start_time": "2026-05-27T14:30:00Z",
    "end_time": "2026-05-27T15:30:00Z",
    "source": "phone",
    "metadata": {
      "location": "gym"
    },
    "notes": null,
    "revision": 1,
    "activities": [
      {
        "activity_id": "660e8400-e29b-41d4-a716-446655440001",
        "type": "exercise",
        "name": "Bench press",
        "metadata": { "equipment": "barbell" },
        "records": [
          {
            "record_id": "770e8400-e29b-41d4-a716-446655440002",
            "record_time": "2026-05-27T14:45:00Z",
            "data": { "sets": 3, "reps": 8, "weight_kg": 80 }
          }
        ]
      }
    ]
  }
]
```

Only sessions where `type = 'workout'`. Ordered by `start_time` DESC.

`revision` increases when the workout or its activities and records change. Clients should send that value when editing a workout.
Writes to a replaced activity or record return `409`; clients should reload the workout before retrying.

### `PATCH /workouts/{session_id}`

Replace a saved workout's title, notes, time, duration, exercises, and sets in one transaction. The body requires the `revision` last read from `GET /workouts/full` and the intended `local_date`. A stale revision returns `409`; reload before saving. Existing exercises and sets are soft-deleted as replaced, and new rows are inserted. Other session metadata and the session ID are retained. Exercise `metadata` and set `extra_data`, `unit`, `record_time`, `weight_key`, and `comment_key` can be sent to preserve older phone fields during an edit.

```json
{
  "expected_revision": 1,
  "start_time": "2026-05-27T09:30:00-05:00",
  "local_date": "2026-05-27",
  "name": "Upper body",
  "notes": "Felt strong",
  "duration_minutes": 45,
  "exercises": [
    {
      "name": "Bench press",
      "muscle_groups": ["Chest"],
      "sets": [{"reps": 8, "weight": 135, "comment": ""}]
    }
  ]
}
```

Success returns `{"session_id": "...", "revision": 2}`. Errors include `404` for a missing workout, `409` for a changed workout, and `422` for invalid data or a time without a UTC offset.

### `POST /workouts`

Create a workout, exercises, and sets in one database transaction. Send a stable `client_request_id` UUID and an offset-aware `start_time`. Repeating the same request ID and body returns the original `session_id` with `reused: true`; reusing the ID with different data returns 409. The session metadata stores `local_date`, `utc_offset_minutes`, and `duration_minutes` for date-safe desktop and phone display.

```json
{
  "client_request_id": "550e8400-e29b-41d4-a716-446655440000",
  "start_time": "2026-05-27T09:30:00-05:00",
  "name": "Morning lift",
  "notes": "Felt strong",
  "duration_minutes": 60,
  "source": "desktop",
  "exercises": [{"name": "Squat", "muscle_groups": ["quads"],
                 "sets": [{"reps": 8, "weight": 80, "comment": ""}]}]
}
```

Response: `{ "session_id": "...", "reused": false }`.

---

## Activities

### `POST /activities`

Create an activity under a session.

**Request body**

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `session_id` | string | Yes | UUID |
| `type` | string | Yes | Lowercased and trimmed; **`task` is rejected** |
| `name` | string \| null | No | |
| `metadata` | object \| null | No | Arbitrary JSON object |

**Example request**

```json
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "type": "exercise",
  "name": "Squat",
  "metadata": { "variant": "back" }
}
```

**Response `200`**

```json
{ "activity_id": "660e8400-e29b-41d4-a716-446655440001" }
```

**Errors**

| Status | `detail` |
|--------|----------|
| 400 | Tasks should not be created as activities |
| 500 | Activity creation failed |

---

### `GET /sessions/{session_id}/activities`

List activities for a session (ordered by `id`).

**Path parameters**

| Param | Type |
|-------|------|
| `session_id` | string (UUID) |

**Query parameters**

| Param | Type | Default |
|-------|------|---------|
| `include_deleted` | bool | false |

**Response `200`** — array of:

| Field | Type |
|-------|------|
| `id` | string |
| `session_id` | string |
| `type` | string |
| `name` | string \| null |
| `metadata` | object \| null |

**Example response**

```json
[
  {
    "id": "660e8400-e29b-41d4-a716-446655440001",
    "session_id": "550e8400-e29b-41d4-a716-446655440000",
    "type": "exercise",
    "name": "Squat",
    "metadata": { "variant": "back" }
  }
]
```

---

### `DELETE /activities/{activity_id}`

Soft-delete one activity (`deleted_reason = 'manual'`).

**Response `204`** — empty body

**Errors**

| Status | `detail` |
|--------|----------|
| 404 | Activity not found |
| 500 | Activity deletion failed |

---

## Records

### `POST /records`

Create a record for an activity. `record_time` is set by the database (not sent in the request).

**Request body**

| Field | Type | Required |
|-------|------|----------|
| `activity_id` | string | Yes |
| `data` | object | Yes |

**Example request**

```json
{
  "activity_id": "660e8400-e29b-41d4-a716-446655440001",
  "data": { "sets": 3, "reps": 10, "weight_kg": 100 }
}
```

**Response `200`**

```json
{ "record_id": "770e8400-e29b-41d4-a716-446655440002" }
```

**Errors**

| Status | `detail` |
|--------|----------|
| 500 | Record creation failed |

---

### `GET /activities/{activity_id}/records`

List records for an activity (ordered by `record_time`).

**Path parameters**

| Param | Type |
|-------|------|
| `activity_id` | string (UUID) |

**Query parameters**

| Param | Type | Default |
|-------|------|---------|
| `include_deleted` | bool | false |

**Response `200`** — array of:

| Field | Type |
|-------|------|
| `id` | string |
| `activity_id` | string |
| `record_time` | datetime |
| `data` | object |

**Example response**

```json
[
  {
    "id": "770e8400-e29b-41d4-a716-446655440002",
    "activity_id": "660e8400-e29b-41d4-a716-446655440001",
    "record_time": "2026-05-27T14:45:00Z",
    "data": { "sets": 3, "reps": 10, "weight_kg": 100 }
  }
]
```

---

### `DELETE /records/{record_id}`

Soft-delete one record (`deleted_reason = 'manual'`).

**Response `204`** — empty body

**Errors**

| Status | `detail` |
|--------|----------|
| 404 | Record not found |
| 500 | Record deletion failed |

---

## Tasks

Tasks use a separate `tasks` table. Do not create tasks via `POST /activities` with `type: "task"`.

### `POST /tasks`

**Request body**

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `title` | string | Yes | |
| `description` | string \| null | No | |
| `category` | string \| null | No | |
| `priority` | int \| null | No | |
| `due_at` | datetime \| null | No | |
| `due_date` | date \| null | No | Calendar deadline, preferred for date-only tasks |
| `session_id` | string \| null | No | Optional parent session |
| `client_request_id` | UUID \| null | No | Stable across retries; same ID and body returns the original task |
| `completed` | bool | No | Defaults to false |

**Example request**

```json
{
  "title": "Buy groceries",
  "description": "Milk and eggs",
  "category": "errands",
  "priority": 2,
  "due_at": "2026-05-28T18:00:00Z",
  "session_id": null
}
```

**Response `200`**

```json
{ "task_id": "880e8400-e29b-41d4-a716-446655440003", "reused": false }
```

**Errors**

| Status | `detail` |
|--------|----------|
| 500 | Task creation failed |

---

### `GET /tasks`

List tasks (newest `created_at` first).

**Query parameters**

| Param | Type | Default | Notes |
|-------|------|---------|-------|
| `status` | string | — | Exact match |
| `category` | string | — | Exact match |
| `limit` | int | 50 | Min 1, max 200 |
| `offset` | int | 0 | Zero-based page offset |
| `include_deleted` | bool | false | |

**Response `200`** — array of:

| Field | Type |
|-------|------|
| `id` | string |
| `title` | string |
| `description` | string \| null |
| `category` | string \| null |
| `status` | string |
| `priority` | int \| null |
| `due_at` | datetime \| null |
| `due_date` | date \| null |
| `completed_at` | datetime \| null |
| `created_at` | datetime |
| `session_id` | string \| null |
| `updated_at` | datetime \| null |
| `deleted_at` | datetime \| null |
| `revision` | int |
| `client_request_id` | UUID \| null |

### `PATCH /tasks/{task_id}`

Update any supplied `title`, `description`, `category`, `priority`, `due_at`, or `due_date` field. Include `expected_revision` from the last GET to detect edits on another device. A stale revision returns 409. A successful update returns the complete task with an incremented `revision`.

```json
{ "description": "New notes", "expected_revision": 3 }
```

---

### `POST /tasks/{task_id}/complete`

Mark a non-deleted task completed (`status = 'completed'`, `completed_at = now()`, `updated_at = now()`). Deleted tasks return 404.
Optional query parameter `expected_revision` returns 409 if the task changed since the last GET. The same parameter is supported by reopen and delete.

**Response `200`**

```json
{
  "task_id": "880e8400-e29b-41d4-a716-446655440003",
  "status": "completed"
}
```

**Errors**

| Status | `detail` |
|--------|----------|
| 404 | Task not found |
| 500 | Task completion failed |

---

### `POST /tasks/{task_id}/reopen`

Mark a non-deleted completed task incomplete again by setting `status = 'pending'`, clearing `completed_at`, and updating `updated_at`.

**Response `200`**

```json
{
  "task_id": "880e8400-e29b-41d4-a716-446655440003",
  "status": "pending"
}
```

**Errors**

| Status | `detail` |
|--------|----------|
| 404 | Task not found |
| 500 | Task reopen failed |

---

### `DELETE /tasks/{task_id}`

Soft-delete a task by setting `deleted_at`, `deleted_reason = 'manual'`, and `updated_at`.

**Response `204`** — empty body

**Errors**

| Status | `detail` |
|--------|----------|
| 404 | Task not found |
| 500 | Task deletion failed |

---

### `POST /tasks/{task_id}/restore`

Restore a task by clearing `deleted_at` and `deleted_reason`, and updating `updated_at`.

**Response `200`**

```json
{
  "task_id": "880e8400-e29b-41d4-a716-446655440003",
  "status": "restored"
}
```

**Errors**

| Status | `detail` |
|--------|----------|
| 404 | Task not found |
| 500 | Task restore failed |

---

## Journal

One `journal_entries` row represents one calendar day. One day can contain multiple `journal_pages` rows.

Page types are managed in the `journal_page_types` table. Use `GET /journal/page-types` to list active types before creating pages. Incoming `page_type` values are normalized with `.lower().strip().replace(" ", "_")` before validation.

Uniqueness is enforced only among **active** pages: a journal day may have at most one non-deleted page per `page_type`. Soft-deleted pages do not block creating a new page of the same type; use `POST /journal/pages/{journal_page_id}/restore` to bring back a deleted page instead.

### `POST /journal/page-types`

Create a new journal page type.

**Request body**

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `type_key` | string | Yes | Normalized with `.lower().strip().replace(" ", "_")` |
| `display_name` | string | Yes | Must be non-empty after trim |
| `page_order` | int | No | Defaults to `0` |

**Example request**

```json
{
  "type_key": "relationship",
  "display_name": "Relationship",
  "page_order": 5
}
```

**Response `200`**

```json
{ "type_key": "relationship" }
```

If the key exists but was soft-deleted, it is restored and `display_name` / `page_order` are updated.

**Errors**

| Status | `detail` |
|--------|----------|
| 400 | Invalid type_key |
| 400 | Invalid display_name |
| 409 | Journal page type already exists |
| 500 | Journal page type creation failed |

---

### `GET /journal/page-types`

List journal page types.

**Query parameters**

| Param | Type | Default |
|-------|------|---------|
| `include_deleted` | bool | false |

**Response `200`** — array of:

| Field | Type |
|-------|------|
| `type_key` | string |
| `display_name` | string |
| `page_order` | int |
| `created_at` | datetime |
| `updated_at` | datetime |

Ordered by `page_order ASC`, then `type_key ASC`.

**Example response**

```json
[
  {
    "type_key": "main",
    "display_name": "Main",
    "page_order": 0,
    "created_at": "2026-06-14T15:00:00Z",
    "updated_at": "2026-06-14T15:00:00Z"
  }
]
```

---

### `DELETE /journal/page-types/{type_key}`

Soft-delete a page type. Existing `journal_pages` rows that reference the type are not modified; the type can no longer be used when creating new pages.

**Response `204`** — no body.

**Errors**

| Status | `detail` |
|--------|----------|
| 400 | The main page type cannot be deleted |
| 404 | Journal page type not found |
| 500 | Journal page type deletion failed |

---

### `POST /journal/page-types/{type_key}/restore`

Restore a soft-deleted page type.

**Response `200`**

```json
{
  "type_key": "relationship",
  "status": "restored"
}
```

**Errors**

| Status | `detail` |
|--------|----------|
| 404 | Journal page type not found |
| 500 | Journal page type restore failed |

---

### `POST /journal/entries`

Create a journal entry for a calendar date.

**Request body**

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `entry_date` | date | Yes | ISO date, e.g. `2026-06-14` |
| `mood` | string \| null | No | |
| `metadata` | object \| null | No | Arbitrary JSON object |

**Example request**

```json
{
  "entry_date": "2026-06-14",
  "mood": "good",
  "metadata": { "energy": 7 }
}
```

**Response `200`**

```json
{ "journal_entry_id": "550e8400-e29b-41d4-a716-446655440000" }
```

**Errors**

| Status | `detail` |
|--------|----------|
| 409 | Journal entry already exists for this date |
| 500 | Journal entry creation failed |

---

### `PATCH /journal/entries/{journal_entry_id}`

Update day-level fields on an existing, non-deleted journal entry.

**Request body** — all fields optional; only fields included in the request are updated. Omitted fields remain unchanged. Explicit JSON `null` may clear nullable fields such as `mood` or `metadata`.

| Field | Type | Notes |
|-------|------|-------|
| `mood` | string \| null | |
| `metadata` | object \| null | Full replacement when supplied |

**Example request**

```json
{
  "mood": "great",
  "metadata": { "energy": 8 }
}
```

**Response `200`** — `JournalEntryOut`:

| Field | Type |
|-------|------|
| `id` | string |
| `entry_date` | date |
| `mood` | string \| null |
| `metadata` | object \| null |
| `created_at` | datetime |
| `updated_at` | datetime |

**Errors**

| Status | `detail` |
|--------|----------|
| 400 | No fields provided for update |
| 404 | Journal entry not found |
| 500 | Journal entry update failed |

---

### `DELETE /journal/entries/{journal_entry_id}`

Soft-delete a journal entry and cascade soft-delete its active child pages.

The entry receives `deleted_reason = 'manual'`. Active child pages receive `deleted_reason = 'cascade'`. Manually deleted pages are not modified.

**Response `204`** — no body.

**Errors**

| Status | `detail` |
|--------|----------|
| 404 | Journal entry not found |
| 500 | Journal entry deletion failed |

---

### `POST /journal/entries/{journal_entry_id}/restore`

Restore a soft-deleted journal entry and only the child pages whose `deleted_reason` was `'cascade'`. Manually deleted pages remain deleted.

**Response `200`**

```json
{
  "journal_entry_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "restored"
}
```

**Errors**

| Status | `detail` |
|--------|----------|
| 404 | Journal entry not found |
| 500 | Journal entry restore failed |

---

### `POST /journal/pages`

Create a page under an existing non-deleted journal entry.

Only one **active** page of each `page_type` may exist per journal entry. If a page of that type was soft-deleted earlier the same day, this endpoint may create a new row. To reuse the deleted row instead, call `POST /journal/pages/{journal_page_id}/restore`.

**Request body**

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `journal_entry_id` | string | Yes | UUID of parent journal entry |
| `page_type` | string | Yes | Must match an active row in `journal_page_types` (see `GET /journal/page-types`) |
| `title` | string \| null | No | |
| `content` | string | No | Defaults to `""` |
| `metadata` | object \| null | No | |
| `page_order` | int | No | Defaults to `0` |

**Example request**

```json
{
  "journal_entry_id": "550e8400-e29b-41d4-a716-446655440000",
  "page_type": "workout",
  "title": "Workout",
  "content": "The workout was difficult today...",
  "page_order": 1
}
```

**Response `200`**

```json
{ "journal_page_id": "660e8400-e29b-41d4-a716-446655440001" }
```

**Errors**

| Status | `detail` |
|--------|----------|
| 400 | Invalid page_type |
| 404 | Journal entry not found |
| 409 | Journal page type already exists for this journal entry (an active page of this type already exists for the day) |
| 500 | Journal page creation failed |

---

### `PATCH /journal/pages/{journal_page_id}`

Update an existing, non-deleted journal page.

**Request body** — all fields optional; only fields included in the request are updated. Omitted fields remain unchanged. Explicit JSON `null` may clear nullable fields such as `title` or `metadata`. `metadata` is a full replacement when supplied.

The following fields cannot be changed through this endpoint: `id`, `journal_entry_id`, `page_type`, `created_at`, `deleted_at`, `deleted_reason`.

| Field | Type | Notes |
|-------|------|-------|
| `title` | string \| null | |
| `content` | string | |
| `metadata` | object \| null | Full replacement when supplied |
| `page_order` | int | |
| `expected_revision` | int \| null | Last observed page revision; stale values return 409 |

**Example request**

```json
{
  "title": "Workout",
  "content": "Updated reflection...",
  "metadata": {},
  "page_order": 1
}
```

**Response `200`** — complete `JournalPageOut`:

| Field | Type |
|-------|------|
| `id` | string |
| `journal_entry_id` | string |
| `page_type` | string |
| `title` | string \| null |
| `content` | string |
| `metadata` | object \| null |
| `page_order` | int |
| `created_at` | datetime |
| `updated_at` | datetime |
| `revision` | int |

**Errors**

| Status | `detail` |
|--------|----------|
| 400 | No fields provided for update |
| 404 | Journal page not found |
| 500 | Journal page update failed |

---

### `DELETE /journal/pages/{journal_page_id}`

Soft-delete one journal page.
Optional query parameter `expected_revision` returns 409 if the page changed since the last GET.

**Response `204`** — no body.

**Errors**

| Status | `detail` |
|--------|----------|
| 404 | Journal page not found |
| 500 | Journal page deletion failed |

---

### `POST /journal/pages/{journal_page_id}/restore`

Restore a soft-deleted journal page. The page's `page_type` must still be active in `journal_page_types`. Restore is only possible when no other **active** page of that `page_type` exists for the same journal entry (partial unique index `journal_pages_entry_type_active_unique`).

**Response `200`**

```json
{
  "journal_page_id": "660e8400-e29b-41d4-a716-446655440001",
  "status": "restored"
}
```

**Errors**

| Status | `detail` |
|--------|----------|
| 404 | Journal page not found |
| 409 | Journal page type is not active |
| 409 | Journal page type already exists for this journal entry (another active page of this type exists for the day) |
| 500 | Journal page restore failed |

---

### `GET /journal/entries`

List journal entries (newest `entry_date` first).

**Query parameters**

| Param | Type | Default | Notes |
|-------|------|---------|-------|
| `start` | date | — | `entry_date >= start` (unless both `start` and `end` set) |
| `end` | date | — | `entry_date <= end` (or `BETWEEN` when both set) |
| `limit` | int | 50 | Min 1, max 200 |
| `include_deleted` | bool | false | |

**Response `200`** — array of:

| Field | Type |
|-------|------|
| `id` | string |
| `entry_date` | date |
| `mood` | string \| null |
| `metadata` | object \| null |
| `created_at` | datetime |
| `updated_at` | datetime |

---

### `GET /journal/entries/{journal_entry_id}`

Get one journal entry, including nested pages.

**Query parameters**

| Param | Type | Default |
|-------|------|---------|
| `include_deleted` | bool | false |

**Response `200`**

Same object shape as `GET /journal/by-date/{entry_date}` (entry fields plus `pages` array). Pages are ordered by `page_order ASC`, then `created_at ASC`.

**Errors**

| Status | `detail` |
|--------|----------|
| 404 | Journal entry not found |

---

### `GET /journal/by-date/{entry_date}`

Get one journal entry for a calendar date, including nested pages.

**Path parameters**

| Param | Type | Notes |
|-------|------|-------|
| `entry_date` | date | ISO date, e.g. `2026-06-14` |

**Query parameters**

| Param | Type | Default |
|-------|------|---------|
| `include_deleted` | bool | false |

**Response `200`**

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "entry_date": "2026-06-14",
  "mood": "good",
  "metadata": null,
  "created_at": "2026-06-14T15:00:00Z",
  "updated_at": "2026-06-14T16:00:00Z",
  "pages": [
    {
      "id": "660e8400-e29b-41d4-a716-446655440001",
      "journal_entry_id": "550e8400-e29b-41d4-a716-446655440000",
      "page_type": "main",
      "title": "Main Page",
      "content": "General reflection about the day...",
      "metadata": null,
      "page_order": 0,
      "created_at": "2026-06-14T15:00:00Z",
      "updated_at": "2026-06-14T15:30:00Z",
      "revision": 1
    }
  ]
}
```

Pages are ordered by `page_order ASC`, then `created_at ASC`.

**Errors**

| Status | `detail` |
|--------|----------|
| 404 | Journal entry not found |

---

### `GET /journal/entries/{journal_entry_id}/pages`

List pages for a journal entry.

**Query parameters**

| Param | Type | Default |
|-------|------|---------|
| `include_deleted` | bool | false |

**Response `200`** — array of:

| Field | Type |
|-------|------|
| `id` | string |
| `journal_entry_id` | string |
| `page_type` | string |
| `title` | string \| null |
| `content` | string |
| `metadata` | object \| null |
| `page_order` | int |
| `created_at` | datetime |
| `updated_at` | datetime |
| `revision` | int |

Ordered by `page_order ASC`, then `created_at ASC`.

**Errors**

| Status | `detail` |
|--------|----------|
| 404 | Journal entry not found |

---

## Data model (app ↔ database)

```
Session (sessions)
  └── Activity (activities) — session_id
        └── Record (records) — activity_id

Task (tasks) — primarily standalone, but may optionally link to a session through session_id

JournalEntry (journal_entries)
  └── JournalPage (journal_pages) — journal_entry_id, page_type → journal_page_types.type_key

JournalPageType (journal_page_types)
```

**Soft delete**

| Table | Columns | List filter |
|-------|---------|-------------|
| `sessions`, `activities`, `records` | `deleted_at`, `deleted_reason` | `include_deleted=false` (default) |
| `tasks` | `deleted_at`, `deleted_reason` | `include_deleted=false` (default) |
| `journal_entries`, `journal_pages`, `journal_page_types` | `deleted_at`, `deleted_reason` | `include_deleted=false` (default) |

**Session delete/restore cascade**

- Delete session → related activities/records get `deleted_reason = 'cascade'`
- Restore session → only restores children where `deleted_reason = 'cascade'`

**Journal entry delete/restore cascade**

- Delete journal entry → active child pages get `deleted_reason = 'cascade'`
- Restore journal entry → only restores child pages where `deleted_reason = 'cascade'`

**Journal delete/restore behavior**

- Delete page type (`DELETE /journal/page-types/{type_key}`) → soft-deletes the type; existing pages are unchanged; new pages using that type are rejected; `main` cannot be deleted
- Restore page type (`POST /journal/page-types/{type_key}/restore`) → clears `deleted_at` and `deleted_reason`
- Delete journal page (`DELETE /journal/pages/{journal_page_id}`) → soft-deletes the page (`deleted_reason = 'manual'`); does not remove the row; an active page of the same `page_type` may be created again afterward
- Restore journal page (`POST /journal/pages/{journal_page_id}/restore`) → clears soft-delete only if the page's `page_type` is still active and no other active page of that type exists for the entry

**Journal page type uniqueness (active rows only)**

Database index:

```sql
CREATE UNIQUE INDEX journal_pages_entry_type_active_unique
ON journal_pages (journal_entry_id, page_type)
WHERE deleted_at IS NULL;
```

- At most one active page per `page_type` per journal day
- Soft-deleted pages are excluded from this rule
- Delete then create again → allowed
- Delete then restore → allowed if no replacement active page was created

Page-type deletion does not cascade to existing journal pages.

---

## Environment (server)

| Variable | Purpose |
|----------|---------|
| `API_KEY` | Expected `x-api-key` value |
| `PGHOST`, `PGPORT`, `PGDATABASE`, `PGUSER`, `PGPASSWORD` | Postgres connection |
| `PGSSLMODE` | Default `require` |

Interactive OpenAPI docs (when the server is running): `/docs`, `/redoc`.
