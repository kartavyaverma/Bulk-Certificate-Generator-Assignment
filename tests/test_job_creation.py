import uuid
from datetime import date

from sqlalchemy import select

from app.models import Certificate, CertificateStatus, Job, JobStatus


def test_submit_job_returns_202_with_job_details(submit_job):
    response = submit_job()

    assert response.status_code == 202
    body = response.json()
    assert uuid.UUID(body["id"])
    assert body["status"] == "pending"
    assert body["course_name"] == "Python Backend Bootcamp"
    assert body["issuer_name"] == "Acme Academy"
    assert body["issue_date"] == "2026-10-07"
    assert body["progress"]["total"] == 3
    assert body["progress"]["pending"] == 3
    assert body["invalid_recipients"] == []
    assert body["links"] == {
        "status": f"/api/v1/jobs/{body['id']}",
        "certificates": f"/api/v1/jobs/{body['id']}/certificates",
        "download": f"/api/v1/jobs/{body['id']}/download",
    }


def test_submit_job_stores_one_certificate_row_per_recipient(submit_job, db, defer_processing):
    job_id = uuid.UUID(submit_job().json()["id"])

    job = db.get(Job, job_id)
    rows = db.scalars(
        select(Certificate).where(Certificate.job_id == job_id).order_by(Certificate.position)
    ).all()

    assert job.status == JobStatus.PENDING
    assert [row.position for row in rows] == [0, 1, 2]
    assert [row.recipient_name for row in rows] == ["Asha Rao", "Rohan Mehta", "Zoë Fernández"]
    assert all(row.status == CertificateStatus.PENDING for row in rows)


def test_one_request_handles_many_recipients(client, submit_job):
    many = [{"name": f"Participant {chr(65 + i % 26)}{i}", "email": f"p{i}@example.com"} for i in range(40)]

    job_id = submit_job(recipients=many).json()["id"]
    body = client.get(f"/api/v1/jobs/{job_id}").json()

    assert body["status"] == "completed"
    assert body["progress"]["total"] == 40
    assert body["progress"]["generated"] == 40


def test_issue_date_defaults_to_today(submit_job, job_payload, client):
    del job_payload["issue_date"]

    response = client.post("/api/v1/jobs", json=job_payload)

    assert response.status_code == 202
    assert response.json()["issue_date"] == date.today().isoformat()
