import re
import tempfile
import uuid
import zipfile
from pathlib import Path

from app.config import get_settings
from app.models import Certificate


def certificate_relative_path(job_id: uuid.UUID, certificate_id: uuid.UUID) -> str:
    return f"{job_id}/{certificate_id}.pdf"


def absolute_path(relative_path: str) -> Path:
    return get_settings().storage_dir / relative_path


def download_filename(certificate: Certificate) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "-", certificate.recipient_name or "").strip("-").lower()
    return f"{slug or 'certificate'}-{certificate.id.hex[:8]}.pdf"


def build_job_archive(certificates: list[Certificate]) -> Path:
    handle = tempfile.NamedTemporaryFile(suffix=".zip", delete=False)
    with handle, zipfile.ZipFile(handle, "w", zipfile.ZIP_DEFLATED) as archive:
        for certificate in certificates:
            source = absolute_path(certificate.file_path)
            if source.is_file():
                archive.write(source, arcname=download_filename(certificate))
    return Path(handle.name)
