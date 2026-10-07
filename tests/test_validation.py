import pytest
from sqlalchemy import func, select

from app.models import Job
from app.services.validation import validate_recipients
from tests.conftest import TEST_MAX_RECIPIENTS


@pytest.mark.parametrize("field", ["course_name", "issuer_name", "recipients"])
def test_missing_required_field_is_rejected(client, job_payload, field):
    del job_payload[field]

    response = client.post("/api/v1/jobs", json=job_payload)

    assert response.status_code == 422


def test_blank_course_name_is_rejected(submit_job):
    assert submit_job(course_name="   ").status_code == 422


def test_empty_recipient_list_is_rejected(submit_job):
    assert submit_job(recipients=[]).status_code == 422


def test_recipient_list_above_the_limit_is_rejected(submit_job):
    too_many = [
        {"name": "Participant", "email": f"p{i}@example.com"}
        for i in range(TEST_MAX_RECIPIENTS + 1)
    ]

    assert submit_job(recipients=too_many).status_code == 422


def test_invalid_recipients_are_reported_and_valid_ones_still_processed(client, submit_job):
    response = submit_job(
        recipients=[
            {"name": "Asha Rao", "email": "asha.rao@example.com"},
            {"name": "Bad Email", "email": "not-an-email"},
            {"email": "missing.name@example.com"},
            {"name": "12345", "email": "digits@example.com"},
        ]
    )

    assert response.status_code == 202
    body = response.json()
    invalid = body["invalid_recipients"]
    assert [item["position"] for item in invalid] == [1, 2, 3]
    assert all(item["status"] == "invalid" for item in invalid)
    assert "email" in invalid[0]["error"]
    assert "name" in invalid[1]["error"]
    assert "at least one letter" in invalid[2]["error"]
    assert body["progress"]["invalid"] == 3
    assert body["progress"]["pending"] == 1

    finished = client.get(f"/api/v1/jobs/{body['id']}").json()
    assert finished["status"] == "completed_with_errors"
    assert finished["progress"]["generated"] == 1
    assert finished["progress"]["invalid"] == 3


def test_duplicate_email_in_one_request_is_flagged(submit_job):
    response = submit_job(
        recipients=[
            {"name": "Asha Rao", "email": "asha.rao@example.com"},
            {"name": "Asha R", "email": "ASHA.RAO@example.com"},
        ]
    )

    body = response.json()
    assert response.status_code == 202
    assert [item["position"] for item in body["invalid_recipients"]] == [1]
    assert "duplicate" in body["invalid_recipients"][0]["error"]


def test_request_with_no_valid_recipient_is_rejected_and_creates_no_job(submit_job, db):
    response = submit_job(recipients=[{"name": "", "email": "nope"}, {"name": "X"}])

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert [item["position"] for item in detail["invalid_recipients"]] == [0, 1]
    assert db.scalar(select(func.count()).select_from(Job)) == 0


def test_validate_recipients_normalises_whitespace():
    result = validate_recipients([{"name": "  Asha    Rao ", "email": " asha@example.com "}])

    assert result[0].is_valid
    assert result[0].name == "Asha Rao"
    assert result[0].email == "asha@example.com"


def test_validate_recipients_keeps_submitted_values_for_invalid_rows():
    result = validate_recipients([{"name": 42, "email": "broken"}])

    assert not result[0].is_valid
    assert result[0].name == "42"
    assert result[0].email == "broken"
    assert "name" in result[0].error and "email" in result[0].error
