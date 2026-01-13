from fpdf import FPDF

def generate_invoice_pdf(order):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)

    pdf.cell(200, 10, f"Invoice {order.invoice_id}", ln=True)
    pdf.cell(200, 10, f"Product: {order.product}", ln=True)
    pdf.cell(200, 10, f"Base Price: €{order.base_price}", ln=True)

    for u in order.upsells:
        pdf.cell(200, 10, f"{u['name']} €{u['price']}", ln=True)

    pdf.cell(200, 10, f"Shipping Fee €{order.expedited_fee}", ln=True)
    pdf.cell(200, 10, f"TOTAL €{order.total_price}", ln=True)

    pdf.output("invoice.pdf")
