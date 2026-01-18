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

    SMTP_HOST = "smtp.gmail.com"
    SMTP_PORT = "587"
    SMTP_USER = "simonaistrate1234@gmail.com"
    SMTP_PASS = "klnr vlhy pzbo fasl"
    EMAIL_TO = "simonamariana.istrate@ulbsibiu.ro"
    EMAIL_FROM = "simonaistrate1234@gmail.com"


    # SMTP_HOST ="smtp.gmail.com"
    # SMTP_PORT ="587"
    # SMTP_USER ="andreeacorina.hera@ulbsibiu.ro"
    # SMTP_PASS =""
    # EMAIL_TO ="corybarby88@yahoo.it"
    # EMAIL_FROM ="andreeacorina.hera@ulbsibiu.ro"

    smtp_host = SMTP_HOST
    smtp_port = SMTP_PORT
    smtp_user = SMTP_USER
    smtp_pass = SMTP_PASS
    email_to = EMAIL_TO
    email_from = EMAIL_FROM

    if not all([smtp_host, smtp_user, smtp_pass, email_to, email_from]):
        raise RuntimeError(
            "Missing SMTP settings. Set vars: "
            "SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, EMAIL_TO (and optional EMAIL_FROM)."
        )

    invoice_id = order.get("invoice_id", "UNKNOWN")
    product = order.get("product", "Unknown product")

    base_price = order.get("base_price", 0)
    expedited_fee = order.get("expedited_fee", 0)
    shipping_days = order.get("shipping_final_days", 0)

    # IMPORTANT: use final_total_price (includes expedited fee), fallback to total_price
    total_price = order.get("final_total_price", order.get("total_price", 0))

    msg = EmailMessage()
    msg["Subject"] = f"Order Confirmation - Invoice {invoice_id}"
    msg["From"] = email_from
    msg["To"] = email_to

    msg.set_content(
        f"Hello,\n\n"
        f"Your order has been finalized.\n\n"
        f"Invoice ID: {invoice_id}\n"
        f"Product: {product}\n"
        f"Base Price: {base_price} RON\n"
        f"Shipping: {shipping_days} days\n"
        f"Expedited fee: {expedited_fee} RON\n"
        f"FINAL TOTAL: {total_price} RON\n\n"
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

    with smtplib.SMTP(smtp_host, int(smtp_port)) as server:
        server.ehlo()
        server.starttls()
        server.login(smtp_user, smtp_pass)
        server.send_message(msg)

    print(f"[EMAIL] Sent successfully to {email_to} (invoice {invoice_id}).")
