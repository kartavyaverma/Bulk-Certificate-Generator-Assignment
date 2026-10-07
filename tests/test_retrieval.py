import io
import uuid
import zipfile

from app.services import storage


def test_list_certificates_of_a_job(client, submit_job):
    job_id = submit_job().json()["id"]

    body = client.get(f"/api/v1/jobs/{job_id}/certificates").json()

    assert body["total"] == 3
    assert [item["position"] for item in body["items"]] == [0, 1, 2]
    for item in body["items"]:
        assert item["job_id"] == job_id
        assert item["status"] == "generated"
        assert item["download_url"] == f"/api/v1/certificates/{item['id']}/download"


def test_list_certificates_is_paginated(client, submit_job):
    job_id = submit_job().json()["id"]

    body = client.get(
        f"/api/v1/jobs/{job_id}/certificates", params={"limit": 2, "offset": 1}
    ).json()

    assert body["total"] == 3
    assert body["limit"] == 2
    assert body["offset"] == 1
    assert [item["position"] for item in body["items"]] == [1, 2]


def test_list_certificates_can_filter_by_status(client, submit_job):
    job_id = submit_job(
        recipients=[
            {"name": "Asha Rao", "email": "asha.rao@example.com"},
            {"name": "Broken", "email": "broken"},
        ]
    ).json()["id"]

    generated = client.get(f"/api/v1/jobs/{job_id}/certificates", params={"status": "generated"})
    invalid = client.get(f"/api/v1/jobs/{job_id}/certificates", params={"status": "invalid"})

    assert [item["recipient_name"] for item in generated.json()["items"]] == ["Asha Rao"]
    assert [item["recipient_name"] for item in invalid.json()["items"]] == ["Broken"]


def test_get_single_certificate(client, submit_job):
    job_id = submit_job().json()["id"]
    listed = client.get(f"/api/v1/jobs/{job_id}/certificates").json()["items"][0]

    response = client.get(f"/api/v1/certificates/{listed['id']}")

    assert response.status_code == 200
    assert response.json() == listed


def test_download_single_certificate_as_pdf(client, submit_job):
    job_id = submit_job().json()["id"]
    item = client.get(f"/api/v1/jobs/{job_id}/certificates").json()["items"][0]

    response = client.get(item["download_url"])

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert "asha-rao-" in response.headers["content-disposition"]
    assert response.content.startswith(b"%PDF")


def test_download_job_as_zip(client, submit_job):
    job_id = submit_job().json()["id"]

    response = client.get(f"/api/v1/jobs/{job_id}/download")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        names = archive.namelist()
        assert len(names) == 3
        assert all(name.endswith(".pdf") for name in names)
        assert any(name.startswith("asha-rao-") for name in names)
        assert all(archive.read(name).startswith(b"%PDF") for name in names)


def test_zip_only_contains_generated_certificates(client, submit_job):
    job_id = submit_job(
        recipients=[
            {"name": "Asha Rao", "email": "asha.rao@example.com"},
            {"name": "Broken", "email": "broken"},
        ]
    ).json()["id"]

    response = client.get(f"/api/v1/jobs/{job_id}/download")

    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        assert len(archive.namelist()) == 1


def test_zip_is_not_available_until_the_job_finishes(client, submit_job, defer_processing):
    job_id = submit_job().json()["id"]

    response = client.get(f"/api/v1/jobs/{job_id}/download")

    assert response.status_code == 409
    assert "pending" in response.json()["detail"]


def test_downloading_a_pending_certificate_returns_409(client, submit_job, defer_processing):
    job_id = submit_job().json()["id"]
    item = client.get(f"/api/v1/jobs/{job_id}/certificates").json()["items"][0]

    response = client.get(f"/api/v1/certificates/{item['id']}/download")

    assert item["download_url"] is None
    assert response.status_code == 409
    assert response.json()["detail"]["status"] == "pending"


def test_download_returns_404_when_the_file_is_gone(client, submit_job):
    job_id = submit_job().json()["id"]
    item = client.get(f"/api/v1/jobs/{job_id}/certificates").json()["items"][0]
    storage.absolute_path(f"{job_id}/{item['id']}.pdf").unlink()

    response = client.get(item["download_url"])

    assert response.status_code == 404


def test_unknown_certificate_returns_404(client):
    certificate_id = uuid.uuid4()

    assert client.get(f"/api/v1/certificates/{certificate_id}").status_code == 404
    assert client.get(f"/api/v1/certificates/{certificate_id}/download").status_code == 404


def test_unknown_job_archive_returns_404(client):
    assert client.get(f"/api/v1/jobs/{uuid.uuid4()}/download").status_code == 404
