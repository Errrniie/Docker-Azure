import logging
import os
import traceback

import psycopg

logger = logging.getLogger("life-api")


def get_conn():
    return psycopg.connect(
        host=os.environ["PGHOST"],
        port=int(os.environ.get("PGPORT", "5432")),
        dbname=os.environ["PGDATABASE"],
        user=os.environ["PGUSER"],
        password=os.environ["PGPASSWORD"],
        sslmode=os.environ.get("PGSSLMODE", "require"),
    )


def ensure_schema():
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                # UUID generation for primary keys
                cur.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto;")

                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS sessions (
                        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        type TEXT NOT NULL,
                        name TEXT NULL,
                        start_time TIMESTAMPTZ NOT NULL,
                        end_time TIMESTAMPTZ NULL,
                        source TEXT NULL,
                        metadata JSONB NULL,
                        notes TEXT NULL,
                        client_request_id UUID NULL,
                        request_hash TEXT NULL,
                        revision BIGINT NOT NULL DEFAULT 1,
                        created_at TIMESTAMPTZ DEFAULT now(),
                        deleted_at TIMESTAMPTZ NULL,
                        deleted_reason TEXT NULL,
                        CONSTRAINT chk_sessions_time_order
                        CHECK (end_time IS NULL OR end_time >= start_time)
                    );
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS activities (
                        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        session_id UUID NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                        type TEXT NOT NULL,
                        name TEXT NULL,
                        metadata JSONB NULL,
                        activity_order INTEGER NOT NULL DEFAULT 0,
                        created_at TIMESTAMPTZ DEFAULT now(),
                        deleted_at TIMESTAMPTZ NULL,
                        deleted_reason TEXT NULL
                    );
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS records (
                        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        activity_id UUID NOT NULL REFERENCES activities(id) ON DELETE CASCADE,
                        record_time TIMESTAMPTZ NOT NULL DEFAULT now(),
                        data JSONB NOT NULL,
                        set_order INTEGER NOT NULL DEFAULT 0,
                        deleted_at TIMESTAMPTZ NULL,
                        deleted_reason TEXT NULL
                    );
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS tasks (
                        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        title TEXT NOT NULL,
                        description TEXT NULL,
                        category TEXT NULL,
                        session_id UUID NULL REFERENCES sessions(id) ON DELETE CASCADE,
                        status TEXT NOT NULL DEFAULT 'pending',
                        revision BIGINT NOT NULL DEFAULT 1,
                        client_request_id UUID NULL,
                        request_hash TEXT NULL,
                        priority INT NULL,
                        due_date DATE NULL,
                        due_at TIMESTAMPTZ NULL,
                        completed_at TIMESTAMPTZ NULL,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                        updated_at TIMESTAMPTZ DEFAULT now(),
                        deleted_at TIMESTAMPTZ NULL,
                        deleted_reason TEXT NULL
                    );
                    """
                )

                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_sessions_start_time ON sessions(start_time DESC);"
                )
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_sessions_type_start_time ON sessions(type, start_time DESC);"
                )
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_activities_session_id ON activities(session_id);"
                )
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_records_activity_id_record_time ON records(activity_id, record_time);"
                )
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_tasks_created_at ON tasks(created_at DESC);"
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS journal_entries (
                        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        entry_date DATE NOT NULL,
                        mood TEXT NULL,
                        metadata JSONB NULL,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                        deleted_at TIMESTAMPTZ NULL,
                        deleted_reason TEXT NULL,
                        CONSTRAINT journal_entries_entry_date_unique UNIQUE (entry_date)
                    );
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS journal_page_types (
                        type_key TEXT PRIMARY KEY,
                        display_name TEXT NOT NULL,
                        page_order INTEGER NOT NULL DEFAULT 0,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                        deleted_at TIMESTAMPTZ NULL,
                        deleted_reason TEXT NULL
                    );
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS journal_pages (
                        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        journal_entry_id UUID NOT NULL REFERENCES journal_entries(id) ON DELETE CASCADE,
                        page_type TEXT NOT NULL,
                        title TEXT NULL,
                        content TEXT NOT NULL DEFAULT '',
                        metadata JSONB NULL,
                        page_order INTEGER NOT NULL DEFAULT 0,
                        revision BIGINT NOT NULL DEFAULT 1,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                        deleted_at TIMESTAMPTZ NULL,
                        deleted_reason TEXT NULL
                    );
                    """
                )
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_journal_entries_entry_date ON journal_entries(entry_date DESC);"
                )
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_journal_pages_entry_id ON journal_pages(journal_entry_id);"
                )
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_journal_pages_page_type ON journal_pages(page_type);"
                )
                cur.execute(
                    """
                    CREATE UNIQUE INDEX IF NOT EXISTS journal_pages_entry_type_active_unique
                    ON journal_pages (journal_entry_id, page_type)
                    WHERE deleted_at IS NULL;
                    """
                )
                cur.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_journal_page_types_active
                    ON journal_page_types(page_order ASC, type_key ASC)
                    WHERE deleted_at IS NULL;
                    """
                )
                cur.execute(
                    """
                    INSERT INTO journal_page_types (type_key, display_name, page_order)
                    VALUES
                        ('main', 'Main', 0),
                        ('workout', 'Workout', 1),
                        ('school', 'School', 2),
                        ('job', 'Job', 3),
                        ('goose', 'Goose Project', 4)
                    ON CONFLICT (type_key) DO NOTHING;
                    """
                )
                cur.execute(
                    """
                    DO $$
                    BEGIN
                        IF NOT EXISTS (
                            SELECT 1
                            FROM pg_constraint
                            WHERE conname = 'journal_pages_page_type_fkey'
                        ) THEN
                            ALTER TABLE journal_pages
                            ADD CONSTRAINT journal_pages_page_type_fkey
                            FOREIGN KEY (page_type)
                            REFERENCES journal_page_types(type_key);
                        END IF;
                    END $$;
                    """
                )

                # Back-compat for older schemas.
                cur.execute("ALTER TABLE sessions ADD COLUMN IF NOT EXISTS end_time TIMESTAMPTZ;")
                cur.execute("ALTER TABLE sessions ADD COLUMN IF NOT EXISTS source TEXT;")
                cur.execute("ALTER TABLE sessions ADD COLUMN IF NOT EXISTS metadata JSONB;")
                cur.execute("ALTER TABLE sessions ADD COLUMN IF NOT EXISTS client_request_id UUID;")
                cur.execute("ALTER TABLE sessions ADD COLUMN IF NOT EXISTS request_hash TEXT;")
                cur.execute("ALTER TABLE sessions ADD COLUMN IF NOT EXISTS revision BIGINT NOT NULL DEFAULT 1;")
                cur.execute("""
                    CREATE UNIQUE INDEX IF NOT EXISTS sessions_client_request_id_unique
                    ON sessions (client_request_id)
                    WHERE client_request_id IS NOT NULL;
                """)
                cur.execute(
                    "ALTER TABLE sessions ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT now();"
                )
                cur.execute("ALTER TABLE sessions ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;")
                cur.execute("ALTER TABLE sessions ADD COLUMN IF NOT EXISTS deleted_reason TEXT;")
                cur.execute(
                    """
                    DO $$
                    BEGIN
                        IF NOT EXISTS (
                            SELECT 1
                            FROM pg_constraint
                            WHERE conname = 'chk_sessions_time_order'
                        ) THEN
                            ALTER TABLE sessions
                            ADD CONSTRAINT chk_sessions_time_order
                            CHECK (end_time IS NULL OR end_time >= start_time);
                        END IF;
                    END $$;
                    """
                )
                cur.execute(
                    "ALTER TABLE activities ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT now();"
                )
                cur.execute("ALTER TABLE activities ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;")
                cur.execute("ALTER TABLE activities ADD COLUMN IF NOT EXISTS deleted_reason TEXT;")
                cur.execute("ALTER TABLE activities ADD COLUMN IF NOT EXISTS activity_order INTEGER NOT NULL DEFAULT 0;")
                cur.execute("ALTER TABLE records ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;")
                cur.execute("ALTER TABLE records ADD COLUMN IF NOT EXISTS deleted_reason TEXT;")
                cur.execute("ALTER TABLE records ADD COLUMN IF NOT EXISTS set_order INTEGER NOT NULL DEFAULT 0;")
                cur.execute(
                    """
                    ALTER TABLE tasks
                    ADD COLUMN IF NOT EXISTS session_id UUID NULL
                    REFERENCES sessions(id) ON DELETE CASCADE;
                    """
                )
                cur.execute(
                    "ALTER TABLE tasks ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT now();"
                )
                cur.execute("ALTER TABLE tasks ADD COLUMN IF NOT EXISTS revision BIGINT NOT NULL DEFAULT 1;")
                cur.execute("ALTER TABLE tasks ADD COLUMN IF NOT EXISTS client_request_id UUID;")
                cur.execute("ALTER TABLE tasks ADD COLUMN IF NOT EXISTS request_hash TEXT;")
                cur.execute("""
                    CREATE UNIQUE INDEX IF NOT EXISTS tasks_client_request_id_unique
                    ON tasks (client_request_id)
                    WHERE client_request_id IS NOT NULL;
                """)
                cur.execute("ALTER TABLE tasks ADD COLUMN IF NOT EXISTS deleted_reason TEXT;")
                cur.execute("ALTER TABLE tasks ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;")
                cur.execute("ALTER TABLE tasks ADD COLUMN IF NOT EXISTS due_date DATE;")
                cur.execute("ALTER TABLE tasks ALTER COLUMN status SET DEFAULT 'pending';")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_tasks_active ON tasks(created_at DESC) WHERE deleted_at IS NULL;")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_tasks_deleted_at ON tasks(deleted_at);")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_tasks_due_at ON tasks(due_at);")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_tasks_due_date ON tasks(due_date);")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);")
                cur.execute("ALTER TABLE journal_pages ADD COLUMN IF NOT EXISTS revision BIGINT NOT NULL DEFAULT 1;")
                cur.execute(
                    """
                    DO $$
                    BEGIN
                        IF EXISTS (
                            SELECT 1
                            FROM pg_constraint
                            WHERE conname = 'journal_pages_entry_type_unique'
                        ) THEN
                            ALTER TABLE journal_pages
                            DROP CONSTRAINT journal_pages_entry_type_unique;
                        END IF;
                    END $$;
                    """
                )
                cur.execute(
                    """
                    CREATE UNIQUE INDEX IF NOT EXISTS journal_pages_entry_type_active_unique
                    ON journal_pages (journal_entry_id, page_type)
                    WHERE deleted_at IS NULL;
                    """
                )
            conn.commit()
    except Exception:
        logger.error("FAILED TO ENSURE DB SCHEMA")
        logger.error(traceback.format_exc())
        raise
