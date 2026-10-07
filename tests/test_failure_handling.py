import pytest

from app.services import processor


@pytest.fixture
def fail_for(monkeypatch):
    def _fail_for(*names):
        original = processor.render_certificate

        def flaky_render(data, destination):
            if data.recipient_name in names:
                raise RuntimeError("disk full")
            original(data, destination)

        monkeypatch.setattr(processor, "render_certificate", flaky_render)

    return _fail_for


def certificates_by_name(client, job_id):
    items = client.get(f"/api/v1/jobs/{job_id}/certificates").json()["items"]
    return {item["recipient_name"]: item for item in items}


def test_one_failed_certificate_does_not_stop_the_others(client, submit_job, fail_for):
    fail_for("Rohan Mehta")

    job_id = submit_job().json()["id"]
    job = client.get(f"/api/v1/jobs/{job_id}").json()
    certificates = certificates_by_name(client, job_id)

    assert job["status"] == "completed_with_errors"
    assert job["progress"]["generated"] == 2
    assert job["progress"]["failed"] == 1
    assert job["progress"]["pending"] == 0
    assert job["progress"]["percent_complete"] == 100.0

    assert certificates["Rohan Mehta"]["status"] == "failed"
    assert certificates["Rohan Mehta"]["error"] == "RuntimeError: disk full"
    assert certificates["Rohan Mehta"]["download_url"] is None
    assert certificates["Asha Rao"]["status"] == "generated"
    assert certificates["Zoë Fernández"]["status"] == "generated"
    assert client.get(certificates["Asha Rao"]["download_url"]).status_code == 200


def test_failed_certificates_can_be_listed_on_their_own(client, submit_job, fail_for):
    fail_for("Asha Rao", "Rohan Mehta")

    job_id = submit_job().json()["id"]
    failed = client.get(f"/api/v1/jobs/{job_id}/certificates", params={"status": "failed"}).json()

    assert failed["total"] == 2
    assert {item["recipient_name"] for item in failed["items"]} == {"Asha Rao", "Rohan Mehta"}


def test_name_the_template_cannot_render_fails_only_that_certificate(client, submit_job):
    job_id = submit_job(
        recipients=[
            {"name": "Asha Rao", "email": "asha.rao@example.com"},
            {"name": "मयंक शर्मा", "email": "mayank@example.com"},
        ]
    ).json()["id"]

    job = client.get(f"/api/v1/jobs/{job_id}").json()
    certificates = certificates_by_name(client, job_id)

    assert job["status"] == "completed_with_errors"
    assert certificates["Asha Rao"]["status"] == "generated"
    assert certificates["मयंक शर्मा"]["status"] == "failed"
    assert "cannot render" in certificates["मयंक शर्मा"]["error"]


def test_job_is_failed_when_every_certificate_fails(client, submit_job, fail_for):
    fail_for("Asha Rao", "Rohan Mehta", "Zoë Fernández")

    job_id = submit_job().json()["id"]
    job = client.get(f"/api/v1/jobs/{job_id}").json()

    assert job["status"] == "failed"
    assert job["progress"]["failed"] == 3
    assert job["progress"]["generated"] == 0


def test_downloading_a_failed_certificate_returns_409_with_the_reason(client, submit_job, fail_for):
    fail_for("Rohan Mehta")

    job_id = submit_job().json()["id"]
    certificate_id = certificates_by_name(client, job_id)["Rohan Mehta"]["id"]
    response = client.get(f"/api/v1/certificates/{certificate_id}/download")

    assert response.status_code == 409
    assert response.json()["detail"]["status"] == "failed"
    assert response.json()["detail"]["error"] == "RuntimeError: disk full"
