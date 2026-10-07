import logging
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import FINISHED_JOB_STATUSES, Certificate, CertificateStatus, Job, JobStatus, utcnow
from app.services import storage
from app.services.generator import CertificateData, render_certificate
from app.services.jobs import count_by_status

logger = logging.getLogger(__name__)

MAX_ERROR_LENGTH = 500


def _generate_certificate(db: Session, job: Job, certificate: Certificate) -> None:
    relative_path = storage.certificate_relative_path(job.id, certificate.id)
    data = CertificateData(
        certificate_id=str(certificate.id),
        recipient_name=certificate.recipient_name,
        course_name=job.course_name,
        issuer_name=job.issuer_name,
        issue_date=job.issue_date,
    )
    try:
        render_certificate(data, storage.absolute_path(relative_path))
    except Exception as exc:
        logger.exception("Certificate %s in job %s failed", certificate.id, job.id)
        certificate.status = CertificateStatus.FAILED
        certificate.error = f"{type(exc).__name__}: {exc}"[:MAX_ERROR_LENGTH]
    else:
        certificate.status = CertificateStatus.GENERATED
        certificate.file_path = relative_path
        certificate.generated_at = utcnow()
    db.commit()


def _finalize_job(db: Session, job: Job) -> None:
    counts = count_by_status(db, job.id)
    generated = counts.get(CertificateStatus.GENERATED, 0)
    total = sum(counts.values())

    if generated == total:
        job.status = JobStatus.COMPLETED
    elif generated == 0:
        job.status = JobStatus.FAILED
    else:
        job.status = JobStatus.COMPLETED_WITH_ERRORS
    job.completed_at = utcnow()
    db.commit()


def process_job(job_id: uuid.UUID) -> None:
    with SessionLocal() as db:
        job = db.get(Job, job_id)
        if job is None or job.status in FINISHED_JOB_STATUSES:
            return

        job.status = JobStatus.PROCESSING
        job.started_at = job.started_at or utcnow()
        db.commit()

        pending = db.scalars(
            select(Certificate)
            .where(
                Certificate.job_id == job.id,
                Certificate.status == CertificateStatus.PENDING,
            )
            .order_by(Certificate.position)
        ).all()

        for certificate in pending:
            _generate_certificate(db, job, certificate)

        _finalize_job(db, job)
        logger.info("Job %s finished with status %s", job.id, job.status.value)


def resume_unfinished_jobs() -> list[uuid.UUID]:
    with SessionLocal() as db:
        job_ids = db.scalars(
            select(Job.id)
            .where(Job.status.in_([JobStatus.PENDING, JobStatus.PROCESSING]))
            .order_by(Job.created_at)
        ).all()

    for job_id in job_ids:
        try:
            process_job(job_id)
        except Exception:
            logger.exception("Could not resume job %s", job_id)
    return list(job_ids)
