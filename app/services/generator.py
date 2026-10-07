import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

PAGE_WIDTH, PAGE_HEIGHT = landscape(A4)
CENTER_X = PAGE_WIDTH / 2
CONTENT_WIDTH = PAGE_WIDTH - 160
SIGNATURE_WIDTH = 300
TEMPLATE_ENCODING = "cp1252"

NAVY = HexColor("#1F3A5F")
GOLD = HexColor("#B8860B")
GREY = HexColor("#555555")


class CertificateRenderError(Exception):
    pass


@dataclass(frozen=True)
class CertificateData:
    certificate_id: str
    recipient_name: str
    course_name: str
    issuer_name: str
    issue_date: date


def _ensure_renderable(label: str, value: str) -> None:
    try:
        value.encode(TEMPLATE_ENCODING)
    except UnicodeEncodeError as exc:
        raise CertificateRenderError(
            f"{label} contains characters the certificate template cannot render"
        ) from exc


def _fit_font_size(
    text: str, font: str, max_size: int, min_size: int, max_width: float = CONTENT_WIDTH
) -> int:
    size = max_size
    while size > min_size and stringWidth(text, font, size) > max_width:
        size -= 1
    return size


def _draw_frame(pdf: canvas.Canvas) -> None:
    pdf.setStrokeColor(NAVY)
    pdf.setLineWidth(4)
    pdf.rect(24, 24, PAGE_WIDTH - 48, PAGE_HEIGHT - 48)
    pdf.setStrokeColor(GOLD)
    pdf.setLineWidth(1.2)
    pdf.rect(36, 36, PAGE_WIDTH - 72, PAGE_HEIGHT - 72)


def _draw_body(pdf: canvas.Canvas, data: CertificateData) -> None:
    pdf.setFillColor(NAVY)
    pdf.setFont("Helvetica-Bold", 34)
    pdf.drawCentredString(CENTER_X, PAGE_HEIGHT - 135, "CERTIFICATE OF COMPLETION")

    pdf.setStrokeColor(GOLD)
    pdf.setLineWidth(2)
    pdf.line(CENTER_X - 130, PAGE_HEIGHT - 155, CENTER_X + 130, PAGE_HEIGHT - 155)

    pdf.setFillColor(GREY)
    pdf.setFont("Helvetica", 15)
    pdf.drawCentredString(CENTER_X, PAGE_HEIGHT - 205, "This certificate is proudly presented to")

    name_size = _fit_font_size(data.recipient_name, "Times-BoldItalic", 44, 14)
    pdf.setFillColor(NAVY)
    pdf.setFont("Times-BoldItalic", name_size)
    pdf.drawCentredString(CENTER_X, PAGE_HEIGHT - 268, data.recipient_name)

    pdf.setStrokeColor(GREY)
    pdf.setLineWidth(0.8)
    pdf.line(CENTER_X - 220, PAGE_HEIGHT - 284, CENTER_X + 220, PAGE_HEIGHT - 284)

    pdf.setFillColor(GREY)
    pdf.setFont("Helvetica", 15)
    pdf.drawCentredString(CENTER_X, PAGE_HEIGHT - 325, "for successfully completing")

    course_size = _fit_font_size(data.course_name, "Helvetica-Bold", 26, 10)
    pdf.setFillColor(NAVY)
    pdf.setFont("Helvetica-Bold", course_size)
    pdf.drawCentredString(CENTER_X, PAGE_HEIGHT - 368, data.course_name)


def _draw_signature_block(pdf: canvas.Canvas, x: float, value: str, label: str) -> None:
    pdf.setFillColor(NAVY)
    pdf.setFont("Helvetica-Bold", _fit_font_size(value, "Helvetica-Bold", 14, 7, SIGNATURE_WIDTH))
    pdf.drawCentredString(x, 118, value)
    pdf.setStrokeColor(GREY)
    pdf.setLineWidth(0.8)
    pdf.line(x - 100, 108, x + 100, 108)
    pdf.setFillColor(GREY)
    pdf.setFont("Helvetica", 11)
    pdf.drawCentredString(x, 92, label)


def _draw_footer(pdf: canvas.Canvas, data: CertificateData) -> None:
    _draw_signature_block(pdf, 200, data.issue_date.strftime("%d %B %Y"), "Date of Issue")
    _draw_signature_block(pdf, PAGE_WIDTH - 200, data.issuer_name, "Issued By")
    pdf.setFillColor(GREY)
    pdf.setFont("Helvetica", 9)
    pdf.drawCentredString(CENTER_X, 52, f"Certificate ID: {data.certificate_id}")


def render_certificate(data: CertificateData, destination: Path) -> None:
    _ensure_renderable("Recipient name", data.recipient_name)
    _ensure_renderable("Course name", data.course_name)
    _ensure_renderable("Issuer name", data.issuer_name)

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".tmp")
    try:
        pdf = canvas.Canvas(str(temporary), pagesize=landscape(A4))
        pdf.setTitle(f"Certificate - {data.recipient_name}")
        pdf.setAuthor(data.issuer_name)
        pdf.setSubject(data.course_name)
        _draw_frame(pdf)
        _draw_body(pdf, data)
        _draw_footer(pdf, data)
        pdf.showPage()
        pdf.save()
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
