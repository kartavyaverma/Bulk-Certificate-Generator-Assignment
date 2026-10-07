import uuid

from sqlalchemy import select

from app.models import Certificate
from app.services.processor import process_job, resume_unfinished_jobs


def test_job_is_pending_before_processing_starts(client, submit_job, defer_processing):
    job_id = submit_job().json()["id"]

    body = client.get(f"/api/v1/jobs/{job_id}").json()

    assert body["status"] == "pending"
    assert body["started_at"] is None
    assert body["completed_at"] is None
    assert body["progress"] == {
        "total": 3,
        "pending": 3,
        "generated": 0,
        "failed": 0,
        "invalid": 0,
        "percent_complete": 0.0,
    }


def test_job_is_completed_after_processing(client, submit_job, defer_processing):
    job_id = submit_job().json()["id"]

    process_job(uuid.UUID(job_id))
    body = client.get(f"/api/v1/jobs/{job_id}").json()

    assert body["status"] == "completed"
    assert body["started_at"] is not None
    assert body["completed_at"] is not None
    assert body["progress"] == {
        "total": 3,
        "pending": 0,
        "generated": 3,
        "failed": 0,
        "invalid": 0,
        "percent_complete": 100.0,
    }


def test_progress_counts_invalid_rows_as_already_processed(client, submit_job, defer_processing):
    job_id = submit_job(
        recipients=[
            {"name": "Asha Rao", "email": "asha.rao@example.com"},
            {"name": "Rohan Mehta", "email": "rohan.mehta@example.com"},
            {"name": "Broken", "email": "broken"},
            {"name": "Broken Too", "email": "also-broken"},
        ]
    ).json()["id"]

    progress = client.get(f"/api/v1/jobs/{job_id}").json()["progress"]

    assert progress["invalid"] == 2
    assert progress["pending"] == 2
    assert progress["percent_complete"] == 50.0


def test_processing_a_finished_job_again_changes_nothing(submit_job, db):
    job_id = uuid.UUID(submit_job().json()["id"])
    query = select(Certificate.generated_at).where(Certificate.job_id == job_id)
    first_run = db.scalars(query).all()

    process_job(job_id)

    assert db.scalars(query).all() == first_run


def test_unfinished_jobs_are_resumed(client, submit_job, defer_processing):
    job_id = submit_job().json()["id"]

    resumed = resume_unfinished_jobs()

    assert resumed == [uuid.UUID(job_id)]
    assert client.get(f"/api/v1/jobs/{job_id}").json()["status"] == "completed"
    assert resume_unfinished_jobs() == []


def test_unknown_job_returns_404(client):
    assert client.get(f"/api/v1/jobs/{uuid.uuid4()}").status_code == 404


def test_malformed_job_id_returns_422(client):
    assert client.get("/api/v1/jobs/not-a-uuid").status_code == 422
