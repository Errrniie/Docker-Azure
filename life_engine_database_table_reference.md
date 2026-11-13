# Life Engine Database Table Reference

This document explains every table currently in the `life_engine` PostgreSQL database, what each column stores, how the tables relate to each other, and how each table should be used by the API and applications.

## Database Overview

The database currently contains seven tables:

| Table | Main responsibility |
|---|---|
| `sessions` | Stores complete tracked sessions, especially workouts |
| `activities` | Stores activities or exercises that belong to a session |
| `records` | Stores measured/logged data that belongs to an activity |
| `tasks` | Stores standalone tasks, reminders, deadlines, and planned work |
| `journal_entries` | Stores one journal container for each calendar day |
| `journal_page_types` | Stores the database-managed journal page types that applications may use |
| `journal_pages` | Stores multiple categorized pages inside a daily journal entry |

The major relationships are:

```text
sessions
  └── activities
        └── records

sessions
  └── tasks (optional relationship)

journal_page_types
  └── journal_pages

journal_entries
  └── journal_pages
```

- `journal_entries` represents one calendar day.
- `journal_pages` stores pages belonging to that day.
- `journal_page_types` controls which page types are available to applications.
- Page types are no longer controlled by a hardcoded Python list.

Tasks are primarily standalone, although a task may optionally be linked to a session.

---

# 1. `sessions`

## Purpose

The `sessions` table stores a complete block of tracked activity.

For workouts, one row represents the entire workout. The exercises inside that workout belong in `activities`, and the sets or measurements belong in `records`.

Examples:

- Push Day
- Legs with Katie
- Back and Biceps
- Cardio session
- Study session
- Work session

## Columns

| Column | Type | Required | Purpose |
|---|---|---:|---|
| `id` | UUID | Yes | Primary key. Automatically generated with `gen_random_uuid()` |
| `type` | TEXT | Yes | Broad session type, such as `workout` |
| `start_time` | TIMESTAMPTZ | Yes | Time the session started. Defaults to `now()` |
| `end_time` | TIMESTAMPTZ | No | Time the session ended |
| `source` | TEXT | No | Where the session came from, such as `phone`, `desktop`, or `manual` |
| `metadata` | JSONB | No | Flexible session-level information |
| `notes` | TEXT | No | Human-readable notes about the session |
| `name` | TEXT | No | User-facing session name, such as `Chest Aurora` |
| `deleted_at` | TIMESTAMPTZ | No | Soft-delete timestamp |
| `deleted_reason` | TEXT | No | Why the row was deleted, such as `manual` |
| `created_at` | TIMESTAMPTZ | No | Time the row was created. Defaults to `now()` |
| `client_request_id` | UUID | No | Unique retry key for atomic workout creation |
| `request_hash` | TEXT | No | Fingerprint used to reject a changed retry payload |
| `revision` | BIGINT | Yes | Starts at 1; increments when a workout or its children change so stale edits can be rejected |

## Constraints

```text
end_time must be NULL or greater than/equal to start_time
```

Constraint name:

```text
chk_sessions_time_order
```

## Relationships

```text
sessions.id
  ├── activities.session_id
  └── tasks.session_id
```

Both foreign keys use `ON DELETE CASCADE` at the PostgreSQL level.

## Indexes

- Primary key on `id`
- `idx_sessions_start_time` on `start_time DESC`
- `idx_sessions_type_start_time` on `(type, start_time DESC)`

## Intended use

For workouts, use:

```text
type = workout
name = specific workout name
```

Example:

```text
type = workout
name = Chest and Triceps
```

Do not use the workout name as the `type`. The type should remain broad and consistent.

---

# 2. `activities`

## Purpose

The `activities` table stores individual activities that belong to a session.

For workouts, one activity normally represents one exercise.

Example:

```text
Session: Push Day
  Activity: Bench Press
  Activity: Incline Dumbbell Press
  Activity: Tricep Pushdown
```

## Columns

| Column | Type | Required | Purpose |
|---|---|---:|---|
| `id` | UUID | Yes | Primary key. Automatically generated |
| `session_id` | UUID | Yes | Parent session |
| `type` | TEXT | Yes | Activity category, such as `strength`, `cardio`, or `warmup` |
| `name` | TEXT | No | Activity or exercise name |
| `metadata` | JSONB | No | Extra information such as tags, equipment, or muscle groups |
| `activity_order` | INTEGER | Yes | Exercise order in a workout. Defaults to 0 |
| `created_at` | TIMESTAMPTZ | No | Creation time. Defaults to `now()` |
| `deleted_at` | TIMESTAMPTZ | No | Soft-delete timestamp |
| `deleted_reason` | TEXT | No | Usually `manual` or `cascade` |

## Relationships

```text
activities.session_id → sessions.id
```

The relationship uses:

```text
ON DELETE CASCADE
```

Activities are also referenced by `records`:

```text
activities.id → records.activity_id
```

## Indexes

- Primary key on `id`
- `idx_activities_session_id` on `session_id`

## Intended use

Workout activity examples:

```text
type = strength
name = BB Bench Press
```

```text
type = cardio
name = Cardio
```

```text
type = warmup
name = Pull Ups
```

Recommended metadata example:

```json
{
  "tags": ["chest", "triceps"],
  "equipment": "barbell"
}
```

Tasks should not be stored as activities.

---

# 3. `records`

## Purpose

The `records` table stores the smallest logged unit of data for an activity.

For workouts, one record usually represents one completed set or measurement.

Example:

```text
Activity: Bench Press
  Record: 135 lb × 10 reps
  Record: 155 lb × 8 reps
  Record: 175 lb × 5 reps
```

## Columns

| Column | Type | Required | Purpose |
|---|---|---:|---|
| `id` | UUID | Yes | Primary key. Automatically generated |
| `activity_id` | UUID | Yes | Parent activity |
| `record_time` | TIMESTAMPTZ | Yes | Time the record was logged. Defaults to `now()` |
| `data` | JSONB | Yes | Actual measurement or logged information |
| `set_order` | INTEGER | Yes | Set order within an exercise. Defaults to 0 |
| `deleted_at` | TIMESTAMPTZ | No | Soft-delete timestamp |
| `deleted_reason` | TEXT | No | Usually `manual` or `cascade` |

## Relationships

```text
records.activity_id → activities.id
```

The relationship uses:

```text
ON DELETE CASCADE
```

## Indexes

- Primary key on `id`
- `idx_records_activity_id_record_time` on `(activity_id, record_time)`
- `idx_records_activity_time` on `(activity_id, record_time)`

The two non-primary indexes currently cover the same columns.

## Current JSON keys found in `data`

The database currently contains these keys:

```text
notes
pain
reps
set
unit
weight
```

Example:

```json
{
  "set": 1,
  "reps": 10,
  "weight": 135,
  "unit": "lbs",
  "pain": 0,
  "notes": "Felt good"
}
```

## Intended use

Use one row per set or measurement. Do not place an entire workout into one record.

---

# 4. `tasks`

## Purpose

The `tasks` table stores standalone planned work.

Examples:

- Finish homework
- Journal today
- Email professor
- Workout with Katie
- Submit assignment
- Make breakfast

A task can be a reminder to write a journal entry, but the actual journal content belongs in the journal tables.

## Columns

| Column | Type | Required | Purpose |
|---|---|---:|---|
| `id` | UUID | Yes | Primary key. Automatically generated |
| `title` | TEXT | Yes | Main task title |
| `description` | TEXT | No | Details or notes |
| `category` | TEXT | No | Group such as `general`, `school`, or `work` |
| `status` | TEXT | Yes | Task state. Defaults to `pending` |
| `priority` | INTEGER | No | Priority value |
| `due_at` | TIMESTAMPTZ | No | Due date and time |
| `due_date` | DATE | No | Calendar deadline independent of time zone |
| `revision` | BIGINT | Yes | Incremented for edits and soft deletes; defaults to 1 |
| `client_request_id` | UUID | No | Unique retry key for task creation |
| `request_hash` | TEXT | No | Fingerprint used to reject a changed retry payload |
| `completed_at` | TIMESTAMPTZ | No | Time the task was completed |
| `created_at` | TIMESTAMPTZ | No | Creation time. Defaults to `now()` |
| `session_id` | UUID | No | Optional linked session |
| `deleted_at` | TIMESTAMPTZ | No | Soft-delete timestamp |
| `updated_at` | TIMESTAMPTZ | No | Last update time. Defaults to `now()` |
| `deleted_reason` | TEXT | No | Usually `manual` |

## Relationships

Optional relationship:

```text
tasks.session_id → sessions.id
```

The relationship uses:

```text
ON DELETE CASCADE
```

Most tasks may leave `session_id` as `NULL`.

## Indexes

- Primary key on `id`
- `idx_tasks_active` on `created_at` for rows where `deleted_at IS NULL`
- `idx_tasks_created_at` on `created_at`
- `idx_tasks_deleted_at` on `deleted_at`
- `idx_tasks_due_at` on `due_at`
- `idx_tasks_due_date` on `due_date`
- `idx_tasks_status` on `status`
- Partial unique index `tasks_client_request_id_unique` on non-null `client_request_id`

## Intended use

Tasks are for planned work and reminders.

Use:

```text
title = Journal Today
```

when the task is a reminder.

Do not store the full journal page in `description`.

---

# 5. `journal_entries`

## Purpose

The `journal_entries` table stores the daily journal container.

There can be only one journal entry row per calendar date.

Example:

```text
Journal entry for 2026-06-14
```

The actual written pages for that day belong in `journal_pages`.

## Columns

| Column | Type | Required | Purpose |
|---|---|---:|---|
| `id` | UUID | Yes | Primary key. Automatically generated |
| `entry_date` | DATE | Yes | Calendar date represented by the journal |
| `mood` | TEXT | No | Overall mood for the day |
| `metadata` | JSONB | No | Flexible day-level data |
| `created_at` | TIMESTAMPTZ | Yes | Creation time. Defaults to `now()` |
| `updated_at` | TIMESTAMPTZ | Yes | Last update time. Defaults to `now()` |
| `deleted_at` | TIMESTAMPTZ | No | Soft-delete timestamp |
| `deleted_reason` | TEXT | No | Why the journal entry was deleted |

## Constraints

Only one journal entry may exist for each date:

```text
UNIQUE (entry_date)
```

Constraint name:

```text
journal_entries_entry_date_unique
```

## Relationships

```text
journal_entries.id → journal_pages.journal_entry_id
```

Deleting a journal entry at the database level cascades to its pages.

## Indexes

- Primary key on `id`
- Unique index/constraint on `entry_date`
- `idx_journal_entries_entry_date` on `entry_date DESC`

## Intended use

A row represents the day, not a page.

Example:

```json
{
  "entry_date": "2026-06-14",
  "mood": "good",
  "metadata": {
    "energy": 7
  }
}
```

---

# 6. `journal_page_types`

## Purpose

The `journal_page_types` table stores the database-managed page types that applications may use when creating journal pages.

Examples include `main`, `workout`, `school`, `job`, and `goose`. Additional types may be added through the API after that functionality is implemented.

## Columns

| Column | Type | Required | Purpose |
|---|---|---:|---|
| `type_key` | TEXT | Yes | Primary key and machine-readable page-type identifier |
| `display_name` | TEXT | Yes | User-facing page-type name |
| `page_order` | INTEGER | Yes | Default display order; defaults to `0` |
| `created_at` | TIMESTAMPTZ | Yes | Creation timestamp; defaults to `now()` |
| `updated_at` | TIMESTAMPTZ | Yes | Last update timestamp; defaults to `now()` |
| `deleted_at` | TIMESTAMPTZ | No | Soft-delete timestamp |
| `deleted_reason` | TEXT | No | Reason the page type was removed, normally `manual` |

## Constraints

```text
PRIMARY KEY (type_key)
```

## Indexes

```text
idx_journal_page_types_active
ON (page_order, type_key)
WHERE deleted_at IS NULL
```

## Relationships

```text
journal_pages.page_type → journal_page_types.type_key
```

The foreign key does not use `ON DELETE CASCADE`.

## Soft-delete behavior

- Active page types have `deleted_at IS NULL`.
- Soft-deleting a page type prevents new journal pages from using it.
- Existing journal pages retain their original type and content.
- The API should normally prevent deletion of the `main` type.
- A deleted page type may be restored later.

## Seeded page types

| `type_key` | `display_name` | `page_order` |
|---|---|---:|
| `main` | Main | 0 |
| `workout` | Workout | 1 |
| `school` | School | 2 |
| `job` | Job | 3 |
| `goose` | Goose Project | 4 |

Applications may create additional page types through the API after that functionality is implemented.

---

# 7. `journal_pages`

## Purpose

The `journal_pages` table stores multiple categorized pages inside one daily journal.

Example daily journal:

```text
June 14, 2026
  Main page
  Workout page
  School page
  Job page
  Goose Project page
```

Each page is a separate row connected to the same `journal_entries` row.

## Columns

| Column | Type | Required | Purpose |
|---|---|---:|---|
| `id` | UUID | Yes | Primary key. Automatically generated |
| `journal_entry_id` | UUID | Yes | Parent daily journal entry |
| `page_type` | TEXT | Yes | Foreign-key reference to `journal_page_types.type_key` |
| `title` | TEXT | No | User-facing page title |
| `content` | TEXT | Yes | Written page content. Defaults to an empty string |
| `metadata` | JSONB | No | Flexible page-level data |
| `page_order` | INTEGER | Yes | Display order. Defaults to `0` |
| `revision` | BIGINT | Yes | Incremented for edits and soft deletes; defaults to 1 |
| `created_at` | TIMESTAMPTZ | Yes | Creation time. Defaults to `now()` |
| `updated_at` | TIMESTAMPTZ | Yes | Last update time. Defaults to `now()` |
| `deleted_at` | TIMESTAMPTZ | No | Soft-delete timestamp |
| `deleted_reason` | TEXT | No | Why the page was deleted |

`page_type` is a foreign-key reference to `journal_page_types.type_key`. A journal page may only use a page type that exists in `journal_page_types`. The API should additionally require that the referenced type is active.

## Constraints

A daily journal cannot contain two **active** pages with the same `page_type`:

```sql
CREATE UNIQUE INDEX journal_pages_entry_type_active_unique
ON journal_pages (journal_entry_id, page_type)
WHERE deleted_at IS NULL;
```

Index name:

```text
journal_pages_entry_type_active_unique
```

This is a **partial unique index**. Rows with `deleted_at IS NOT NULL` are excluded.

Effects:

- One active page of each type per calendar day
- Different days may each have their own active page of the same type
- After soft-deleting a page, `POST /journal/pages` may insert a new active page of that type
- A soft-deleted page may be restored with `POST /journal/pages/{journal_page_id}/restore` if no other active page of that type exists for the entry

The former full-table constraint `journal_pages_entry_type_unique` was removed in favor of this index.

Example (active pages only):

```text
One active `main` page per daily journal
One active `workout` page per daily journal
One active `goose` page per daily journal
```

## Relationships

```text
journal_pages.journal_entry_id → journal_entries.id
journal_pages.page_type → journal_page_types.type_key
```

Foreign-key behavior:

- `journal_entry_id` uses `ON DELETE CASCADE`.
- `page_type` references `journal_page_types(type_key)` without `ON DELETE CASCADE`.

## Indexes

- Primary key on `id`
- Partial unique index `journal_pages_entry_type_active_unique` on `(journal_entry_id, page_type)` where `deleted_at IS NULL`
- `idx_journal_pages_entry_id` on `journal_entry_id`
- `idx_journal_pages_page_type` on `page_type`

## Intended use

Example:

```json
{
  "page_type": "goose",
  "title": "Goose Project",
  "content": "Worked on firmware today...",
  "page_order": 4,
  "metadata": null
}
```

Another valid example when the type is present and active:

```json
{
  "page_type": "workout",
  "title": "Workout",
  "content": "The workout was difficult today...",
  "page_order": 1,
  "metadata": null
}
```

---

# Journal JSON Shape

A complete journal response from the API should likely look like this:

```json
{
  "id": "journal-entry-uuid",
  "entry_date": "2026-06-14",
  "mood": "good",
  "metadata": null,
  "created_at": "2026-06-14T15:00:00Z",
  "updated_at": "2026-06-14T16:00:00Z",
  "pages": [
    {
      "id": "main-page-uuid",
      "page_type": "main",
      "title": "Main Page",
      "content": "General reflection about the day...",
      "metadata": null,
      "page_order": 0,
      "created_at": "2026-06-14T15:00:00Z",
      "updated_at": "2026-06-14T15:30:00Z"
    },
    {
      "id": "workout-page-uuid",
      "page_type": "workout",
      "title": "Workout",
      "content": "Reflection about the workout...",
      "metadata": null,
      "page_order": 1,
      "created_at": "2026-06-14T15:05:00Z",
      "updated_at": "2026-06-14T15:35:00Z"
    },
    {
      "id": "goose-page-uuid",
      "page_type": "goose",
      "title": "Goose Project",
      "content": "Worked on firmware today...",
      "metadata": null,
      "page_order": 4,
      "created_at": "2026-06-14T16:00:00Z",
      "updated_at": "2026-06-14T16:20:00Z"
    }
  ]
}
```

---

# Soft Delete Behavior

The database uses soft-delete columns in every major table.

```text
deleted_at
deleted_reason
```

A row is considered active when:

```sql
deleted_at IS NULL
```

Common reasons:

```text
manual
cascade
```

## Existing workout behavior

When a session is deleted through the API:

```text
session → manual delete
activities → cascade delete
records → cascade delete
```

When restored, only children deleted with `deleted_reason = 'cascade'` should be restored.

## Journal page type behavior

```text
Delete page type:
journal_page_types row → manual soft delete
existing journal_pages → unchanged
new journal_pages using that type → rejected by API
```

Page-type deletion does not cascade to existing pages.

## Journal page behavior

```text
Delete journal page:
journal_pages row → manual soft delete (row retained)

Create page after delete:
allowed when no other active page of that page_type exists for the entry
inserts a new row OR restore the deleted row via API

Restore journal page:
clears deleted_at / deleted_reason on the existing row
only succeeds when no other active page of that page_type exists for the entry
```

Journal pages and page types may be restored through API endpoints.

## Journal entry behavior

When a journal entry is soft-deleted through the API:

```text
journal entry → manual soft delete (deleted_reason = 'manual', updated_at = now())
active journal pages → cascade soft delete (deleted_reason = 'cascade', updated_at = now())
```

When restored through `POST /journal/entries/{journal_entry_id}/restore`:

```text
restore the journal entry (clear deleted_at / deleted_reason, updated_at = now())
restore only pages with deleted_reason = 'cascade'
leave manually deleted pages deleted
```

Day-level fields such as `mood` and `metadata` may be updated through `PATCH /journal/entries/{journal_entry_id}`.

Journal page content may be updated through `PATCH /journal/pages/{journal_page_id}` without changing `page_type` or `journal_entry_id`.

Deleting directly with a PostgreSQL `DELETE` statement will physically delete child journal pages because of `ON DELETE CASCADE`. The API should normally use soft deletes instead.

---

# Complete Data Responsibility Summary

| Data | Correct table |
|---|---|
| Entire workout | `sessions` |
| Exercise inside a workout | `activities` |
| Set, reps, weight, pain, or measurement | `records` |
| Homework, reminder, deadline, planned action | `tasks` |
| One calendar day's journal container | `journal_entries` |
| Available journal page category/type | `journal_page_types` |
| A categorized page inside a daily journal | `journal_pages` |

---

# Current Database Structure

```text
sessions
  id
  type
  start_time
  end_time
  source
  metadata
  notes
  name
  deleted_at
  deleted_reason
  created_at

activities
  id
  session_id → sessions.id
  type
  name
  metadata
  created_at
  deleted_at
  deleted_reason

records
  id
  activity_id → activities.id
  record_time
  data
  deleted_at
  deleted_reason

tasks
  id
  title
  description
  category
  status
  priority
  due_at
  completed_at
  created_at
  session_id → sessions.id (optional)
  deleted_at
  updated_at
  deleted_reason

journal_entries
  id
  entry_date
  mood
  metadata
  created_at
  updated_at
  deleted_at
  deleted_reason

journal_page_types
  type_key
  display_name
  page_order
  created_at
  updated_at
  deleted_at
  deleted_reason

journal_pages
  id
  journal_entry_id → journal_entries.id
  page_type → journal_page_types.type_key
  title
  content
  metadata
  page_order
  created_at
  updated_at
  deleted_at
  deleted_reason

journal_entries
  └── journal_pages
        └── page_type → journal_page_types.type_key
```

---

# Development Rule

Whenever a table or column changes, update all affected layers:

1. PostgreSQL schema
2. Database setup or migration code in `db.py`
3. FastAPI models
4. FastAPI routers and SQL queries
5. `API.md`
6. Phone app request/response models
7. Desktop app request/response models
8. This database reference document
