import uuid
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from starlette.background import BackgroundTask

from app.database import get_db
from app.models import FINISHED_JOB_STATUSES, CertificateStatus, Job
from app.schemas import (
    CertificateListResponse,
    CertificateResponse,
    JobCreatedResponse,
    JobCreateRequest,
    JobResponse,
)
from app.services import jobs as jobs_service
from app.services import storage
from app.services.processor import process_job

router = APIRouter(prefix="/jobs", tags=["jobs"])

DbSession = Annotated[Session, Depends(get_db)]


def _get_job_or_404(db: Session, job_id: uuid.UUID) -> Job:
    job = jobs_service.get_job(db, job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Job not found")
    return job


@router.post(
    "",
    response_model=JobCreatedResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Submit a bulk certificate generation job",
)
def submit_job(
    payload: JobCreateRequest, background_tasks: BackgroundTasks, db: DbSession
) -> JobCreatedResponse:
    try:
        job = jobs_service.create_job(db, payload)
    except jobs_service.NoValidRecipientsError as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "message": str(exc),
                "invalid_recipients": [
                    {
                        "position": recipient.position,
                        "name": recipient.name,
                        "email": recipient.email,
                        "error": recipient.error,
                    }
                    for recipient in exc.recipients
                ],
            },
        ) from exc

    background_tasks.add_task(process_job, job.id)

    _, invalid = jobs_service.list_certificates(db, job.id, status=CertificateStatus.INVALID)
    return JobCreatedResponse.from_model(
        job,
        jobs_service.count_by_status(db, job.id),
        invalid_recipients=[CertificateResponse.from_model(item) for item in invalid],
    )


@router.get("/{job_id}", response_model=JobResponse, summary="Get job status and progress")
def get_job(job_id: uuid.UUID, db: DbSession) -> JobResponse:
    job = _get_job_or_404(db, job_id)
    return JobResponse.from_model(job, jobs_service.count_by_status(db, job.id))


@router.get(
    "/{job_id}/certificates",
    response_model=CertificateListResponse,
    summary="List the certificates of a job",
)
def list_job_certificates(
    job_id: uuid.UUID,
    db: DbSession,
    status_filter: Annotated[CertificateStatus | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> CertificateListResponse:
    job = _get_job_or_404(db, job_id)
    total, certificates = jobs_service.list_certificates(
        db, job.id, status=status_filter, limit=limit, offset=offset
    )
    return CertificateListResponse(
        total=total,
        limit=limit,
        offset=offset,
        items=[CertificateResponse.from_model(item) for item in certificates],
    )


@router.get(
    "/{job_id}/download",
    response_class=FileResponse,
    summary="Download every generated certificate of a job as a ZIP archive",
)
def download_job_archive(job_id: uuid.UUID, db: DbSession) -> FileResponse:
    job = _get_job_or_404(db, job_id)
    if job.status not in FINISHED_JOB_STATUSES:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail=f"Job is still {job.status.value}; the archive is available once it finishes",
        )

    _, certificates = jobs_service.list_certificates(
        db, job.id, status=CertificateStatus.GENERATED
    )
    if not certificates:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail="No certificates were generated for this job"
        )

    archive_path = storage.build_job_archive(certificates)
    return FileResponse(
        archive_path,
        media_type="application/zip",
        filename=f"certificates-{job.id}.zip",
        background=BackgroundTask(archive_path.unlink, missing_ok=True),
    )
