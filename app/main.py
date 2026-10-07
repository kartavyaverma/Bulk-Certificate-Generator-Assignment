import logging
import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, status
from sqlalchemy import text

from app.config import API_PREFIX, get_settings
from app.database import Base, engine
from app.routers import certificates, jobs
from app.services.processor import resume_unfinished_jobs

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    get_settings().storage_dir.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(bind=engine)
    threading.Thread(target=resume_unfinished_jobs, name="resume-jobs", daemon=True).start()
    yield


app = FastAPI(
    title=get_settings().app_name,
    version="1.0.0",
    description="Submit a list of recipients, track the generation job and download the certificates.",
    lifespan=lifespan,
)

app.include_router(jobs.router, prefix=API_PREFIX)
app.include_router(certificates.router, prefix=API_PREFIX)


@app.get("/health", tags=["health"], summary="Check that the API can reach the database")
def health() -> dict[str, str]:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, detail="Database is unreachable"
        ) from exc
    return {"status": "ok"}
