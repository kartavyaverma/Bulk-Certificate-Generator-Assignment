import os
import shutil
import tempfile

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://postgres:postgres@localhost:5433/certificates_test",
)
TEST_STORAGE_DIR = tempfile.mkdtemp(prefix="certificates-test-")
TEST_MAX_RECIPIENTS = 50

if not make_url(TEST_DATABASE_URL).database.endswith("_test"):
    raise RuntimeError("TEST_DATABASE_URL must point to a database whose name ends with '_test'")

os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ["STORAGE_DIR"] = TEST_STORAGE_DIR
os.environ["MAX_RECIPIENTS_PER_JOB"] = str(TEST_MAX_RECIPIENTS)


def ensure_database_exists(url: str) -> None:
    target = make_url(url)
    admin_engine = create_engine(target.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin_engine.connect() as connection:
        exists = connection.scalar(
            text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": target.database}
        )
        if not exists:
            connection.execute(text(f'CREATE DATABASE "{target.database}"'))
    admin_engine.dispose()


ensure_database_exists(TEST_DATABASE_URL)

from fastapi.testclient import TestClient

from app.database import Base, SessionLocal, engine
from app.main import app

JOBS_URL = "/api/v1/jobs"


@pytest.fixture(scope="session", autouse=True)
def database_schema():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)
    engine.dispose()
    shutil.rmtree(TEST_STORAGE_DIR, ignore_errors=True)


@pytest.fixture(autouse=True)
def clean_tables():
    yield
    with engine.begin() as connection:
        connection.execute(text("TRUNCATE TABLE certificates, jobs"))


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def db():
    with SessionLocal() as session:
        yield session


@pytest.fixture
def recipients():
    return [
        {"name": "Asha Rao", "email": "asha.rao@example.com"},
        {"name": "Rohan Mehta", "email": "rohan.mehta@example.com"},
        {"name": "Zoë Fernández", "email": "zoe.fernandez@example.com"},
    ]


@pytest.fixture
def job_payload(recipients):
    return {
        "course_name": "Python Backend Bootcamp",
        "issuer_name": "Acme Academy",
        "issue_date": "2026-10-07",
        "recipients": recipients,
    }


@pytest.fixture
def submit_job(client, job_payload):
    def _submit(**overrides):
        return client.post(JOBS_URL, json={**job_payload, **overrides})

    return _submit


@pytest.fixture
def defer_processing(monkeypatch):
    monkeypatch.setattr("app.routers.jobs.process_job", lambda job_id: None)
