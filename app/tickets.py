"""
Ticket Generation — QR codes + PDF tickets using ReportLab.

Each ticket item gets:
  • A unique ticket_code  (UUID-based, stored in OrderTicket table)
  • A QR code image       (encodes a signed verification URL)
  • A PDF page            (one page per ticket quantity × tier)

PDF is stored in  static/tickets/<order_uuid>.pdf
"""

import io
import json
import os
import uuid as _uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import qrcode
from qrcode.image.pil import PilImage
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas as rl_canvas

# ── Paths ─────────────────────────────────────────────────────────────────────
TICKETS_DIR = Path("static/tickets")
TICKETS_DIR.mkdir(parents=True, exist_ok=True)

# ── Brand colours (RGB 0-1) ───────────────────────────────────────────────────
BRAND_BLUE  = colors.HexColor("#0369a1")
BRAND_LIGHT = colors.HexColor("#e0f2fe")
INK_900     = colors.HexColor("#0f172a")
INK_600     = colors.HexColor("#475569")
INK_300     = colors.HexColor("#cbd5e1")
WHITE       = colors.white
GREEN_OK    = colors.HexColor("#059669")


# ── QR code helper ────────────────────────────────────────────────────────────
def make_qr_image(data: str, box_size: int = 6, border: int = 2) -> PilImage:
    """Return a PIL image of the QR code."""
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=box_size,
        border=border,
    )
    qr.add_data(data)
    qr.make(fit=True)
    return qr.make_image(fill_color="black", back_color="white")


def qr_bytes(data: str) -> bytes:
    """Return QR code as PNG bytes."""
    img = make_qr_image(data)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf.read()


# ── PDF builder ───────────────────────────────────────────────────────────────
def _draw_ticket_page(
    c: rl_canvas.Canvas,
    *,
    event_title: str,
    event_date:  str,
    event_venue: str,
    tier_name:   str,
    ticket_code: str,
    order_id:    int,
    holder_name: str,
    holder_email: str,
    verify_url:  str,
    ticket_num:  int,
    total_tickets: int,
    amount_paid: Optional[float] = None,
    mpesa_receipt: Optional[str] = None,
) -> None:
    """Draw one A4 ticket page on the current canvas page."""
    W, H = A4  # 595 × 841 pts

    # ── Background ─────────────────────────────────────────────────────────
    c.setFillColor(colors.HexColor("#f8fafc"))
    c.rect(0, 0, W, H, fill=1, stroke=0)

    # ── Top accent band ─────────────────────────────────────────────────────
    c.setFillColor(BRAND_BLUE)
    c.rect(0, H - 90*mm, W, 90*mm, fill=1, stroke=0)

    # Logo area — "TicketInit" wordmark
    c.setFillColor(WHITE)
    c.setFont("Helvetica-Bold", 22)
    c.drawString(14*mm, H - 20*mm, "TicketInit")
    c.setFont("Helvetica", 10)
    c.drawString(14*mm, H - 28*mm, "ticketinit.co.ke")

    # Ticket X of Y
    c.setFont("Helvetica", 9)
    right_x = W - 14*mm
    c.drawRightString(right_x, H - 20*mm, f"Ticket {ticket_num} of {total_tickets}")
    c.setFont("Helvetica-Bold", 10)
    c.drawRightString(right_x, H - 30*mm, f"Order #{order_id}")

    # Event title
    c.setFillColor(WHITE)
    c.setFont("Helvetica-Bold", 20)
    # Truncate long titles
    title_display = event_title if len(event_title) <= 50 else event_title[:47] + "…"
    c.drawString(14*mm, H - 48*mm, title_display)

    # Tier badge
    c.setFillColor(colors.HexColor("#0ea5e9"))
    c.roundRect(14*mm, H - 62*mm, len(tier_name)*5.5*mm + 10*mm, 8*mm, 3*mm, fill=1, stroke=0)
    c.setFillColor(WHITE)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(19*mm, H - 57*mm, tier_name)

    # Date + venue on blue band
    c.setFillColor(colors.HexColor("#bae6fd"))
    c.setFont("Helvetica", 10)
    c.drawString(14*mm, H - 75*mm, f"📅  {event_date}")
    if event_venue:
        c.drawString(14*mm, H - 83*mm, f"📍  {event_venue}")

    # ── Divider with tear-notch look ────────────────────────────────────────
    divider_y = H - 105*mm
    c.setStrokeColor(INK_300)
    c.setDash(4, 4)
    c.setLineWidth(0.8)
    c.line(14*mm, divider_y, W - 14*mm, divider_y)
    c.setDash()  # reset

    # Circles on divider edges (tear-line effect)
    c.setFillColor(colors.HexColor("#f8fafc"))
    c.setStrokeColor(INK_300)
    c.circle(0, divider_y, 6*mm, fill=1, stroke=1)
    c.circle(W, divider_y, 6*mm, fill=1, stroke=1)

    # ── QR section ──────────────────────────────────────────────────────────
    qr_size = 50*mm
    qr_x    = W - 14*mm - qr_size
    qr_y    = divider_y - qr_size - 10*mm

    # QR box background
    c.setFillColor(WHITE)
    c.setStrokeColor(INK_300)
    c.setLineWidth(0.5)
    c.roundRect(qr_x - 3*mm, qr_y - 3*mm, qr_size + 6*mm, qr_size + 6*mm, 3*mm, fill=1, stroke=1)

    # Draw QR code
    qr_png = qr_bytes(verify_url)
    qr_img_reader = io.BytesIO(qr_png)
    c.drawImage(qr_img_reader, qr_x, qr_y, width=qr_size, height=qr_size)

    c.setFillColor(INK_600)
    c.setFont("Helvetica", 7)
    c.drawCentredString(qr_x + qr_size/2, qr_y - 7*mm, "Scan to verify ticket")

    # ── Ticket details (left of QR) ─────────────────────────────────────────
    detail_x  = 14*mm
    detail_y  = divider_y - 18*mm
    row_gap   = 12*mm

    def draw_detail(label, value, y):
        c.setFillColor(INK_600)
        c.setFont("Helvetica", 8)
        c.drawString(detail_x, y + 4*mm, label.upper())
        c.setFillColor(INK_900)
        c.setFont("Helvetica-Bold", 11)
        c.drawString(detail_x, y, value or "—")

    draw_detail("Ticket holder",  holder_name,   detail_y)
    draw_detail("Email",          holder_email,  detail_y - row_gap)
    draw_detail("Ticket code",    ticket_code[:8].upper() + "…", detail_y - 2*row_gap)

    if amount_paid:
        draw_detail("Amount paid", f"KES {int(amount_paid):,}", detail_y - 3*row_gap)
    if mpesa_receipt:
        draw_detail("M-Pesa receipt", mpesa_receipt, detail_y - 4*row_gap)

    # ── Verification URL (small) ─────────────────────────────────────────────
    c.setFillColor(INK_600)
    c.setFont("Helvetica-Oblique", 7)
    c.drawString(14*mm, 30*mm, f"Verify at: {verify_url}")

    # ── Footer ───────────────────────────────────────────────────────────────
    c.setFillColor(BRAND_BLUE)
    c.rect(0, 0, W, 22*mm, fill=1, stroke=0)
    c.setFillColor(WHITE)
    c.setFont("Helvetica", 8)
    c.drawCentredString(W / 2, 12*mm, "This ticket is valid for one person only. Non-transferable.")
    c.setFont("Helvetica", 7)
    c.drawCentredString(W / 2, 6*mm, "For support: hello@ticketinit.co.ke  |  +254 707 991 991")


def generate_pdf_tickets(
    order,
    items: list[dict],
    base_url: str = "https://ticketinit.co.ke",
) -> tuple[Path, list[dict]]:
    """
    Generate a multi-page PDF for all tickets in an order.

    Returns (pdf_path, ticket_records) where ticket_records is a list of
    { tier_name, ticket_code, verify_url, quantity_index } dicts — one entry
    per individual ticket (so 2× VIP = 2 records).
    """
    pdf_path = TICKETS_DIR / f"{order.uuid}.pdf"
    event_date_str = _fmt_order_date(order)

    # Count total tickets
    total_tickets = sum(item.get("quantity", 1) for item in items)
    ticket_num    = 0
    ticket_records: list[dict] = []

    c = rl_canvas.Canvas(str(pdf_path), pagesize=A4)

    for item in items:
        qty = item.get("quantity", 1)
        for i in range(qty):
            ticket_num  += 1
            ticket_code  = str(_uuid.uuid4()).replace("-", "").upper()
            verify_url   = f"{base_url}/tickets/verify/{ticket_code}"

            _draw_ticket_page(
                c,
                event_title    = item.get("event_title", "Event"),
                event_date     = event_date_str,
                event_venue    = item.get("event_venue", ""),
                tier_name      = item.get("name", "General"),
                ticket_code    = ticket_code,
                order_id       = order.id,
                holder_name    = order.name,
                holder_email   = order.email,
                verify_url     = verify_url,
                ticket_num     = ticket_num,
                total_tickets  = total_tickets,
                amount_paid    = float(order.total),
                mpesa_receipt  = getattr(order, "mpesa_receipt", None),
            )
            c.showPage()

            ticket_records.append({
                "tier_name":   item.get("name", "General"),
                "event_title": item.get("event_title", ""),
                "ticket_code": ticket_code,
                "verify_url":  verify_url,
                "qty_index":   i + 1,
            })

    c.save()
    return pdf_path, ticket_records


# ── Helpers ───────────────────────────────────────────────────────────────────
def _fmt_order_date(order) -> str:
    """Return a readable date string for the order (creation date as fallback)."""
    created = getattr(order, "created_at", None)
    if created:
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        return created.strftime("%a, %b %d, %Y")
    return datetime.now(timezone.utc).strftime("%a, %b %d, %Y")