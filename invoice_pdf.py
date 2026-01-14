import os
from fpdf import FPDF


def generate_invoice_pdf(order: dict) -> str:
    """
    Generates invoice PDF and returns absolute path.
    """

    invoice_id = order.get("invoice_id", "UNKNOWN")
    product = order.get("product", "Unknown product")
    base_price = order.get("base_price", 0)

    upsells = order.get("upsells", [])
    expedited_fee = order.get("expedited_fee", 0)
    total_price = order.get("total_price", 0)

    shipping_days = order.get("shipping_final_days", 0)

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)

    pdf.cell(200, 10, f"Invoice ID: {invoice_id}", ln=True)
    pdf.ln(5)

    pdf.cell(200, 10, f"Product: {product}", ln=True)
    pdf.cell(200, 10, f"Base Price: {base_price} RON", ln=True)
    pdf.cell(200, 10, f"Shipping: {shipping_days} days", ln=True)
    pdf.ln(5)

    if upsells:
        pdf.cell(200, 10, "Upsells:", ln=True)
        for u in upsells:
            name = u.get("name", "Upsell")
            price = u.get("price", 0)
            pdf.cell(200, 10, f"- {name}: {price} RON", ln=True)
        pdf.ln(2)

    pdf.cell(200, 10, f"Expedited fee: {expedited_fee} RON", ln=True)
    pdf.cell(200, 10, f"TOTAL: {total_price} RON", ln=True)

    filename = f"invoice_{invoice_id}.pdf"
    filepath = os.path.abspath(filename)

    pdf.output(filepath)

    print(f"[PDF] Invoice generated: {filepath}")
    return filepath
