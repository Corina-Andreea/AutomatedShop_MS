import os
import smtplib
from email.message import EmailMessage


def send_email(order: dict, pdf_path: str):
    """
    Sends real confirmation email with PDF invoice attachment.

    Required ENV variables:
      SMTP_HOST
      SMTP_PORT (default 587)
      SMTP_USER
      SMTP_PASS
      EMAIL_TO
      EMAIL_FROM (optional, default SMTP_USER)
    """

    smtp_host = os.getenv("SMTP_HOST")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER")
    smtp_pass = os.getenv("SMTP_PASS")
    email_to = os.getenv("EMAIL_TO")
    email_from = os.getenv("EMAIL_FROM", smtp_user)

    if not all([smtp_host, smtp_user, smtp_pass, email_to, email_from]):
        raise RuntimeError(
            "Missing SMTP settings. Set env vars: "
            "SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, EMAIL_TO (and optional EMAIL_FROM)."
        )

    invoice_id = order.get("invoice_id", "UNKNOWN")
    product = order.get("product", "Unknown product")
    total_price = order.get("total_price", 0)
    shipping_days = order.get("shipping_final_days", 0)

    msg = EmailMessage()
    msg["Subject"] = f"Order Confirmation - Invoice {invoice_id}"
    msg["From"] = email_from
    msg["To"] = email_to

    msg.set_content(
        f"Hello,\n\n"
        f"Your order has been finalized.\n\n"
        f"Invoice ID: {invoice_id}\n"
        f"Product: {product}\n"
        f"Shipping: {shipping_days} days\n"
        f"Total: {total_price} RON\n\n"
        f"Invoice PDF is attached.\n\n"
        f"Thank you!"
    )

    # attach pdf
    with open(pdf_path, "rb") as f:
        pdf_data = f.read()

    msg.add_attachment(
        pdf_data,
        maintype="application",
        subtype="pdf",
        filename=os.path.basename(pdf_path),
    )

    with smtplib.SMTP(smtp_host, smtp_port) as server:
        server.ehlo()
        server.starttls()
        server.login(smtp_user, smtp_pass)
        server.send_message(msg)

    print(f"[EMAIL] Sent successfully to {email_to} (invoice {invoice_id}).")
