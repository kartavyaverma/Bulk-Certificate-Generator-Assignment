import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.config import API_PREFIX, get_settings
from app.models import Certificate, CertificateStatus, Job, JobStatus

MAX_RECIPIENTS = get_settings().max_recipients_per_job


class RecipientInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=2, max_length=80)
    email: EmailStr

    @field_validator("name")
    @classmethod
    def normalise_name(cls, value: str) -> str:
        value = " ".join(value.split())
        if not any(character.isalpha() for character in value):
            raise ValueError("must contain at least one letter")
        return value


class JobCreateRequest(BaseModel):
    model_config = ConfigDict(
        str_strip_whitespace=True,
        json_schema_extra={
            "examples": [
                {
                    "course_name": "Python Backend Bootcamp",
                    "issuer_name": "Acme Academy",
                    "issue_date": "2026-10-07",
                    "recipients": [
                        {"name": "Asha Rao", "email": "asha.rao@example.com"},
                        {"name": "Rohan Mehta", "email": "rohan.mehta@example.com"},
                    ],
                }
            ]
        },
    )

    course_name: str = Field(min_length=2, max_length=120)
    issuer_name: str = Field(min_length=2, max_length=80)
    issue_date: date | None = None
    recipients: list[dict[str, Any]] = Field(min_length=1, max_length=MAX_RECIPIENTS)


class CertificateResponse(BaseModel):
    id: uuid.UUID
    job_id: uuid.UUID
    position: int
    recipient_name: str | None
    recipient_email: str | None
    status: CertificateStatus
    error: str | None
    generated_at: datetime | None
    download_url: str | None

    @classmethod
    def from_model(cls, certificate: Certificate) -> "CertificateResponse":
        download_url = None
        if certificate.status == CertificateStatus.GENERATED:
            download_url = f"{API_PREFIX}/certificates/{certificate.id}/download"
        return cls(
            id=certificate.id,
            job_id=certificate.job_id,
            position=certificate.position,
            recipient_name=certificate.recipient_name,
            recipient_email=certificate.recipient_email,
            status=certificate.status,
            error=certificate.error,
            generated_at=certificate.generated_at,
            download_url=download_url,
        )


class CertificateListResponse(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[CertificateResponse]


class JobProgress(BaseModel):
    total: int
    pending: int
    generated: int
    failed: int
    invalid: int
    percent_complete: float

    @classmethod
    def from_counts(cls, counts: dict[CertificateStatus, int]) -> "JobProgress":
        total = sum(counts.values())
        pending = counts.get(CertificateStatus.PENDING, 0)
        percent_complete = round(100 * (total - pending) / total, 2) if total else 0.0
        return cls(
            total=total,
            pending=pending,
            generated=counts.get(CertificateStatus.GENERATED, 0),
            failed=counts.get(CertificateStatus.FAILED, 0),
            invalid=counts.get(CertificateStatus.INVALID, 0),
            percent_complete=percent_complete,
        )


class JobLinks(BaseModel):
    status: str
    certificates: str
    download: str


class JobResponse(BaseModel):
    id: uuid.UUID
    course_name: str
    issuer_name: str
    issue_date: date
    status: JobStatus
    progress: JobProgress
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    links: JobLinks

    @classmethod
    def from_model(cls, job: Job, counts: dict[CertificateStatus, int], **extra: Any) -> "JobResponse":
        base_url = f"{API_PREFIX}/jobs/{job.id}"
        return cls(
            id=job.id,
            course_name=job.course_name,
            issuer_name=job.issuer_name,
            issue_date=job.issue_date,
            status=job.status,
            progress=JobProgress.from_counts(counts),
            created_at=job.created_at,
            started_at=job.started_at,
            completed_at=job.completed_at,
            links=JobLinks(
                status=base_url,
                certificates=f"{base_url}/certificates",
                download=f"{base_url}/download",
            ),
            **extra,
        )


class JobCreatedResponse(JobResponse):
    invalid_recipients: list[CertificateResponse]
