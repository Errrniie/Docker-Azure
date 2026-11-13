# life-api

FastAPI + Postgres API for sessions, activities, records, and tasks.

## Run locally

1) Create a `.env` with:

- `API_KEY`
- `PGHOST`, `PGPORT`, `PGDATABASE`, `PGUSER`, `PGPASSWORD` (and optional `PGSSLMODE`)

2) Install deps and run:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload
```

Docs at `http://localhost:8000/docs`.
