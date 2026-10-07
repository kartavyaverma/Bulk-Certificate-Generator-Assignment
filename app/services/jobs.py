import uuid
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Certificate, CertificateStatus, Job
from app.schemas import JobCreateRequest
from app.services.validation import ValidatedRecipient, validate_recipients


class NoValidRecipientsError(Exception):
    def __init__(self, recipients: list[ValidatedRecipient]) -> None:
        super().__init__("None of the submitted recipients are valid")
        self.recipients = recipients


def create_job(db: Session, payload: JobCreateRequest) -> Job:
    recipients = validate_recipients(payload.recipients)
    if not any(recipient.is_valid for recipient in recipients):
        raise NoValidRecipientsError(recipients)

    job = Job(
        course_name=payload.course_name,
        issuer_name=payload.issuer_name,
        issue_date=payload.issue_date or date.today(),
    )
    job.certificates = [
        Certificate(
            position=recipient.position,
            recipient_name=recipient.name,
            recipient_email=recipient.email,
            status=CertificateStatus.PENDING if recipient.is_valid else CertificateStatus.INVALID,
            error=recipient.error,
        )
        for recipient in recipients
    ]
    db.add(job)
    db.commit()
    return job


def get_job(db: Session, job_id: uuid.UUID) -> Job | None:
    return db.get(Job, job_id)


def count_by_status(db: Session, job_id: uuid.UUID) -> dict[CertificateStatus, int]:
    rows = db.execute(
        select(Certificate.status, func.count())
        .where(Certificate.job_id == job_id)
        .group_by(Certificate.status)
    ).all()
    return {status: count for status, count in rows}


def list_certificates(
    db: Session,
    job_id: uuid.UUID,
    status: CertificateStatus | None = None,
    limit: int | None = None,
    offset: int = 0,
) -> tuple[int, list[Certificate]]:
    filters = [Certificate.job_id == job_id]
    if status is not None:
        filters.append(Certificate.status == status)

    total = db.scalar(select(func.count()).select_from(Certificate).where(*filters)) or 0
    query = select(Certificate).where(*filters).order_by(Certificate.position).offset(offset)
    if limit is not None:
        query = query.limit(limit)
    return total, list(db.scalars(query).all())
