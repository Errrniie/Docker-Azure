import logging
import os

from dotenv import load_dotenv
from fastapi import FastAPI

import dependencies
from db import ensure_schema
from routers import activities, exercises, journal, records, sessions, tasks

# API contract: keep API.md in sync when adding/removing/changing endpoints.

logging.basicConfig(level=logging.INFO)

load_dotenv()
dependencies.API_KEY = os.getenv("API_KEY")

if not dependencies.API_KEY:
    raise RuntimeError("API_KEY environment variable is not set")

app = FastAPI()


@app.on_event("startup")
def startup():
    ensure_schema()


@app.get("/health")
def health():
    return {"status": "ok"}


app.include_router(exercises.router)
app.include_router(sessions.router)
app.include_router(activities.router)
app.include_router(records.router)
app.include_router(tasks.router)
app.include_router(journal.router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
