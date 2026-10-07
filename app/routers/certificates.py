import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Certificate, CertificateStatus
from app.schemas import CertificateResponse
from app.services import storage

router = APIRouter(prefix="/certificates", tags=["certificates"])

DbSession = Annotated[Session, Depends(get_db)]


def _get_certificate_or_404(db: Session, certificate_id: uuid.UUID) -> Certificate:
    certificate = db.get(Certificate, certificate_id)
    if certificate is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Certificate not found")
    return certificate


@router.get(
    "/{certificate_id}",
    response_model=CertificateResponse,
    summary="Get the status of a single certificate",
)
def get_certificate(certificate_id: uuid.UUID, db: DbSession) -> CertificateResponse:
    return CertificateResponse.from_model(_get_certificate_or_404(db, certificate_id))


@router.get(
    "/{certificate_id}/download",
    response_class=FileResponse,
    summary="Download a generated certificate as a PDF",
)
def download_certificate(certificate_id: uuid.UUID, db: DbSession) -> FileResponse:
    certificate = _get_certificate_or_404(db, certificate_id)
    if certificate.status != CertificateStatus.GENERATED:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={
                "message": "Certificate is not available for download",
                "status": certificate.status.value,
                "error": certificate.error,
            },
        )

    path = storage.absolute_path(certificate.file_path)
    if not path.is_file():
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail="Certificate file is missing from storage"
        )

    return FileResponse(
        path, media_type="application/pdf", filename=storage.download_filename(certificate)
    )
