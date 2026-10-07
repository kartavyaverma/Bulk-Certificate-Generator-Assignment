from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from app.schemas import RecipientInput


@dataclass(frozen=True)
class ValidatedRecipient:
    position: int
    name: str | None
    email: str | None
    error: str | None

    @property
    def is_valid(self) -> bool:
        return self.error is None


def _as_text(value: Any, limit: int) -> str | None:
    if value is None:
        return None
    return str(value)[:limit]


def _format_errors(exc: ValidationError) -> str:
    messages = []
    for error in exc.errors():
        field = ".".join(str(part) for part in error["loc"]) or "recipient"
        messages.append(f"{field}: {error['msg']}")
    return "; ".join(messages)


def validate_recipients(raw_recipients: list[dict[str, Any]]) -> list[ValidatedRecipient]:
    seen_emails: set[str] = set()
    results: list[ValidatedRecipient] = []

    for position, raw in enumerate(raw_recipients):
        try:
            recipient = RecipientInput.model_validate(raw)
        except ValidationError as exc:
            results.append(
                ValidatedRecipient(
                    position=position,
                    name=_as_text(raw.get("name"), 255),
                    email=_as_text(raw.get("email"), 320),
                    error=_format_errors(exc),
                )
            )
            continue

        email_key = recipient.email.lower()
        if email_key in seen_emails:
            results.append(
                ValidatedRecipient(
                    position=position,
                    name=recipient.name,
                    email=recipient.email,
                    error="email: duplicate of an earlier recipient in this request",
                )
            )
            continue

        seen_emails.add(email_key)
        results.append(
            ValidatedRecipient(
                position=position, name=recipient.name, email=recipient.email, error=None
            )
        )

    return results
