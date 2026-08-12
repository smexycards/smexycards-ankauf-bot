from __future__ import annotations

from io import BytesIO
from pathlib import Path
from textwrap import shorten

from pypdf import PdfReader, PdfWriter
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from config import GENERATED_DIR, PDF_TEMPLATE


def format_eur(cents: int) -> str:
    value = cents / 100
    raw = f"{value:,.2f}"
    return raw.replace(",", "X").replace(".", ",").replace("X", ".") + " €"


def _fit(text: str | None, width: int) -> str:
    value = (text or "").strip()
    return shorten(value, width=width, placeholder="...") if len(value) > width else value


def _check(c: canvas.Canvas, x: float, y: float) -> None:
    c.setFont("Helvetica-Bold", 10)
    c.drawString(x, y, "X")


def generate_prefilled_pdf(ticket: dict, date_text: str) -> Path:
    """Create a prefilled copy of the original Smexycards purchase form.

    The original PDF remains the background so the layout and buyer details stay identical.
    Seller/deal information is stamped on top. Signature lines stay empty.
    """
    if not ticket.get("seller_name"):
        raise ValueError("Verkäuferdaten fehlen")
    if ticket.get("agreed_price_cents") is None:
        raise ValueError("Ankaufspreis fehlt")

    overlay_buffer = BytesIO()
    c = canvas.Canvas(overlay_buffer, pagesize=A4)
    c.setFillColorRGB(0.10, 0.16, 0.25)
    c.setFont("Helvetica", 9)

    # Seller details / receipt date.
    c.drawString(128, 687, _fit(ticket.get("seller_name"), 35))
    c.drawString(420, 687, _fit(date_text, 22))
    c.drawString(128, 658, _fit(ticket.get("seller_street"), 52))
    c.drawString(94, 629, _fit(ticket.get("seller_city"), 35))
    c.drawString(428, 629, _fit(ticket.get("seller_contact"), 38))

    # Purchase type checkbox.
    kind = ticket.get("kind")
    if kind == "single":
        _check(c, 41, 559)
    elif kind == "collection":
        _check(c, 320, 559)
    else:
        _check(c, 418, 559)

    details = ticket.get("details", {})
    price = format_eur(int(ticket["agreed_price_cents"])).replace(" €", "")

    if kind == "single":
        card = details.get("card", "Einzelkarte")
        parallel = details.get("parallel", "")
        description = f"{card} - {parallel}" if parallel else card
        set_year = details.get("set_year", "")
        condition = details.get("condition", "")
        qty = "1"
    else:
        count = details.get("count", "")
        description = "Sammlung / Lot" + (f" - {count}" if count else "")
        set_year = details.get("category", "")
        condition = details.get("grading_mix", "")
        qty = "1 Lot"

    # First article row. Collection tickets deliberately stay summarized rather than listing every card.
    c.setFont("Helvetica", 7.8)
    c.drawString(68, 469, _fit(description, 50))
    c.drawString(266, 469, _fit(set_year, 22))
    c.drawString(348, 469, _fit(condition, 20))
    c.drawString(431, 469, _fit(str(qty), 9))
    c.drawRightString(548, 469, price)

    # Total.
    c.setFont("Helvetica-Bold", 9)
    c.drawString(119, 271, price)

    # Payment checkbox.
    payment = (ticket.get("payment_method") or "").lower()
    if "bar" in payment:
        _check(c, 240, 270)
    elif "paypal" in payment:
        _check(c, 342, 270)
    elif "über" in payment or "ueber" in payment or "bank" in payment:
        _check(c, 421, 270)

    # Notes: ticket reference + optional deal description/payment fallback.
    notes = f"Discord-Ticket #{int(ticket['id']):04d}"
    deal_desc = (ticket.get("deal_description") or "").strip()
    if deal_desc:
        notes += f" | {deal_desc}"
    if payment and not any(k in payment for k in ("bar", "paypal", "über", "ueber", "bank")):
        notes += f" | Auszahlung: {ticket.get('payment_method')}"

    c.setFont("Helvetica", 7.5)
    c.drawString(104, 160, _fit(notes, 105))
    c.save()
    overlay_buffer.seek(0)

    template_reader = PdfReader(str(PDF_TEMPLATE))
    overlay_reader = PdfReader(overlay_buffer)
    page = template_reader.pages[0]
    page.merge_page(overlay_reader.pages[0])

    writer = PdfWriter()
    writer.add_page(page)

    GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    out_path = GENERATED_DIR / f"Smexycards_Ankaufsformular_Ticket_{int(ticket['id']):04d}.pdf"
    with out_path.open("wb") as f:
        writer.write(f)
    return out_path
