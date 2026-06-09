from email.message import EmailMessage
import smtplib

import email_settings


def send_verification_code(email, code):
    settings = email_settings.read_private()
    if settings.get("email_provider") != "smtp":
        raise RuntimeError("email provider is not configured")
    if not settings.get("smtp_host") or not settings.get("smtp_password"):
        raise RuntimeError("smtp is not configured")

    sender = settings.get("smtp_from") or settings.get("smtp_username")
    if not sender:
        raise RuntimeError("smtp sender is not configured")

    message = EmailMessage()
    message["Subject"] = "fake-ui password reset code"
    message["From"] = sender
    message["To"] = email
    message.set_content(f"Your fake-ui password reset code is: {code}\nIt expires in 10 minutes.")

    host = settings.get("smtp_host")
    port = int(settings.get("smtp_port") or 587)
    if settings.get("smtp_tls", True):
        with smtplib.SMTP(host, port, timeout=15) as client:
            client.starttls()
            if settings.get("smtp_username"):
                client.login(settings.get("smtp_username"), settings.get("smtp_password"))
            client.send_message(message)
    else:
        with smtplib.SMTP(host, port, timeout=15) as client:
            if settings.get("smtp_username"):
                client.login(settings.get("smtp_username"), settings.get("smtp_password"))
            client.send_message(message)
