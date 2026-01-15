import os
from fpdf import FPDF


def _safe_pdf_text(s: str) -> str:
    """
    FPDF (classic) supports latin-1 only.
    This removes emojis and any non-latin1 chars.
    """
    if s is None:
        return ""
    s = str(s)

    # replace common unicode dashes/quotes with safe ASCII
    s = s.replace("–", "-").replace("—", "-")
    s = s.replace("“", '"').replace("”", '"').replace("’", "'").replace("‘", "'")

    # remove emoji / unsupported chars
    s = s.encode("latin-1", "ignore").decode("latin-1")
    return s


def generate_invoice_pdf(order: dict) -> str:
    """
    Generates invoice PDF and returns absolute path.
    Uses FINAL total price (including expedited fee).
    """

    invoice_id = order.get("invoice_id", "UNKNOWN")
    product = order.get("product", "Unknown product")

    base_price = order.get("base_price", 0)
    upsells = order.get("upsells", [])
    expedited_fee = order.get("expedited_fee", 0)

    shipping_days = order.get("shipping_final_days", order.get("shipping_days", 0))

    # ✅ IMPORTANT: final total
    total_price = order.get("final_total_price", order.get("total_price", 0))

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)

    pdf.cell(200, 10, _safe_pdf_text(f"Invoice ID: {invoice_id}"), ln=True)
    pdf.ln(5)

    pdf.cell(200, 10, _safe_pdf_text(f"Product: {product}"), ln=True)
    pdf.cell(200, 10, _safe_pdf_text(f"Base Price: {base_price} RON"), ln=True)

    pdf.ln(4)

    if upsells:
        pdf.cell(200, 10, _safe_pdf_text("Upsells:"), ln=True)
        for u in upsells:
            name = u.get("name", "Upsell")
            price = u.get("price", 0)
            pdf.cell(200, 10, _safe_pdf_text(f"- {name}: {price} RON"), ln=True)
        pdf.ln(2)

    pdf.cell(200, 10, _safe_pdf_text(f"Shipping: {shipping_days} days"), ln=True)
    pdf.cell(200, 10, _safe_pdf_text(f"Expedited fee: {expedited_fee} RON"), ln=True)

    pdf.ln(5)
    pdf.set_font("Arial", "B", 12)
    pdf.cell(200, 10, _safe_pdf_text(f"FINAL TOTAL: {total_price} RON"), ln=True)

    filename = f"invoice_{invoice_id}.pdf"
    filepath = os.path.abspath(filename)

    pdf.output(filepath)

    print(f"[PDF] Invoice generated: {filepath}")
    return filepath
