import enum
import uuid
from datetime import date, datetime, timezone

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Index, Integer, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class JobStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    COMPLETED_WITH_ERRORS = "completed_with_errors"
    FAILED = "failed"


class CertificateStatus(str, enum.Enum):
    PENDING = "pending"
    GENERATED = "generated"
    FAILED = "failed"
    INVALID = "invalid"


FINISHED_JOB_STATUSES = frozenset(
    {JobStatus.COMPLETED, JobStatus.COMPLETED_WITH_ERRORS, JobStatus.FAILED}
)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def status_column(enum_class: type[enum.Enum]) -> Enum:
    return Enum(
        enum_class,
        native_enum=False,
        length=32,
        values_callable=lambda members: [member.value for member in members],
    )


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    course_name: Mapped[str] = mapped_column(String(200))
    issuer_name: Mapped[str] = mapped_column(String(200))
    issue_date: Mapped[date] = mapped_column(Date)
    status: Mapped[JobStatus] = mapped_column(
        status_column(JobStatus), default=JobStatus.PENDING, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    certificates: Mapped[list["Certificate"]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )


class Certificate(Base):
    __tablename__ = "certificates"
    __table_args__ = (
        UniqueConstraint("job_id", "position", name="uq_certificates_job_position"),
        Index("ix_certificates_job_status", "job_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"))
    position: Mapped[int] = mapped_column(Integer)
    recipient_name: Mapped[str | None] = mapped_column(String(255))
    recipient_email: Mapped[str | None] = mapped_column(String(320))
    status: Mapped[CertificateStatus] = mapped_column(
        status_column(CertificateStatus), default=CertificateStatus.PENDING
    )
    error: Mapped[str | None] = mapped_column(Text)
    file_path: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    job: Mapped[Job] = relationship(back_populates="certificates")
