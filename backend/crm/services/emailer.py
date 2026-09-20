"""Single email gateway for the whole app: OTP login mails + follow-up sends.

Backend comes from EMAIL_BACKEND (env): Django's console backend prints mails to
the container log (dev default — OTPs are readable in `docker logs`); set SMTP_*
env vars to switch to real delivery. No credentials are hardcoded anywhere.
"""

from django.conf import settings
from django.core.mail import EmailMessage, send_mail


class EmailDeliveryError(Exception):
    pass


def send_email(to, subject, body, attachments=None) -> None:
    """attachments: optional list of (filename, bytes, mimetype)."""
    try:
        if attachments:
            message = EmailMessage(subject, body, settings.DEFAULT_FROM_EMAIL, [to])
            for filename, content, mimetype in attachments:
                message.attach(filename, content, mimetype or "application/octet-stream")
            message.send(fail_silently=False)
        else:
            send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [to], fail_silently=False)
    except Exception as exc:  # network/auth errors from the chosen backend
        raise EmailDeliveryError(str(exc)) from exc


def otp_email(code: str, minutes_valid: int) -> tuple[str, str]:
    subject = f"Your Practice by Numbers login code: {code}"
    body = (
        f"Your verification code is {code}.\n\n"
        f"It expires in {minutes_valid} minutes. If you didn't request it, "
        "you can ignore this email.\n\n"
        "Practice by Numbers"
    )
    return subject, body
