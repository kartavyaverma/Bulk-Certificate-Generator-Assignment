import uuid
from datetime import date
from pathlib import Path

import pytest
from pypdf import PdfReader
from sqlalchemy import select

from app.models import Certificate, CertificateStatus
from app.services import storage
from app.services.generator import CertificateData, CertificateRenderError, render_certificate


def make_data(**overrides):
    values = {
        "certificate_id": "c0ffee00-0000-4000-8000-000000000001",
        "recipient_name": "Asha Rao",
        "course_name": "Python Backend Bootcamp",
        "issuer_name": "Acme Academy",
        "issue_date": date(2026, 10, 7),
    }
    return CertificateData(**{**values, **overrides})


def read_pdf_text(path: Path) -> str:
    reader = PdfReader(str(path))
    assert len(reader.pages) == 1
    return reader.pages[0].extract_text()


def test_render_certificate_writes_a_pdf_with_recipient_details(tmp_path):
    destination = tmp_path / "nested" / "certificate.pdf"

    render_certificate(make_data(), destination)

    assert destination.read_bytes().startswith(b"%PDF")
    text = read_pdf_text(destination)
    assert "CERTIFICATE OF COMPLETION" in text
    assert "Asha Rao" in text
    assert "Python Backend Bootcamp" in text
    assert "Acme Academy" in text
    assert "07 October 2026" in text
    assert "c0ffee00-0000-4000-8000-000000000001" in text


def test_render_certificate_supports_accented_and_long_names(tmp_path):
    long_name = "Zoë Fernández de la Cruz Montenegro y Villanueva de los Santos"
    destination = tmp_path / "certificate.pdf"

    render_certificate(make_data(recipient_name=long_name), destination)

    assert "Fernández" in read_pdf_text(destination)


def test_render_certificate_rejects_text_the_template_cannot_draw(tmp_path):
    destination = tmp_path / "certificate.pdf"

    with pytest.raises(CertificateRenderError, match="Recipient name"):
        render_certificate(make_data(recipient_name="मयंक शर्मा"), destination)

    assert list(tmp_path.iterdir()) == []


def test_job_generates_one_pdf_per_recipient(submit_job, db):
    job_id = uuid.UUID(submit_job().json()["id"])

    rows = db.scalars(
        select(Certificate).where(Certificate.job_id == job_id).order_by(Certificate.position)
    ).all()

    assert len(rows) == 3
    for row in rows:
        assert row.status == CertificateStatus.GENERATED
        assert row.generated_at is not None
        assert row.file_path == f"{job_id}/{row.id}.pdf"
        text = read_pdf_text(storage.absolute_path(row.file_path))
        assert row.recipient_name in text
        assert str(row.id) in text
