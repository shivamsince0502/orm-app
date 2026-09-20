"""Email-OTP login: code creation/verification + cookie session lifecycle."""

import hashlib
import secrets

from django.utils import timezone

from crm.models import ApiSession, EmailOtp
from crm.services import emailer

OTP_TTL_MINUTES = 10
OTP_RESEND_COOLDOWN_SECONDS = 60
OTP_MAX_ATTEMPTS = 5
SESSION_TTL_DAYS = 7
SESSION_COOKIE = "fjq_session"


def _hash(salt: str, code: str) -> str:
    return hashlib.sha256((salt + code).encode()).hexdigest()


def request_otp(email: str) -> None:
    """Create + email a fresh code for this email (single active code per email)."""
    recent = EmailOtp.objects.filter(email=email).order_by("-created_at").first()
    if recent and (timezone.now() - recent.created_at).total_seconds() < OTP_RESEND_COOLDOWN_SECONDS:
        raise Cooldown()

    # Single active code per email.
    EmailOtp.objects.filter(email=email, consumed=False).update(consumed=True)

    code = f"{secrets.randbelow(10**6):06d}"
    salt = secrets.token_hex(8)
    EmailOtp.objects.create(
        email=email,
        salt=salt,
        code_hash=_hash(salt, code),
        expires_at=timezone.now() + timezone.timedelta(minutes=OTP_TTL_MINUTES),
    )

    subject, body = emailer.otp_email(code, OTP_TTL_MINUTES)
    emailer.send_email(email, subject, body)


def verify_otp(email: str, code: str) -> str:
    """Validate the code; on success returns the raw session token (for the cookie)."""
    otp = EmailOtp.objects.filter(email=email, consumed=False).order_by("-created_at").first()
    if otp is None or otp.expires_at < timezone.now():
        raise InvalidOtp("Code expired or not found — request a new one.")
    if otp.attempts >= OTP_MAX_ATTEMPTS:
        otp.consumed = True
        otp.save(update_fields=["consumed"])
        raise InvalidOtp("Too many attempts — request a new code.")

    if secrets.compare_digest(otp.code_hash, _hash(otp.salt, code)):
        otp.consumed = True
        otp.save(update_fields=["consumed"])
        return _issue_session(email)

    otp.attempts += 1
    otp.save(update_fields=["attempts"])
    remaining = OTP_MAX_ATTEMPTS - otp.attempts
    if remaining <= 0:
        otp.consumed = True
        otp.save(update_fields=["consumed"])
        raise InvalidOtp("Too many attempts — request a new code.")
    raise InvalidOtp(f"Wrong code — {remaining} attempt(s) left.")


def _issue_session(email: str) -> str:
    raw_token = secrets.token_urlsafe(32)
    ApiSession.objects.create(
        email=email,
        token_hash=hashlib.sha256(raw_token.encode()).hexdigest(),
        expires_at=timezone.now() + timezone.timedelta(days=SESSION_TTL_DAYS),
    )
    return raw_token


def resolve_session(raw_token: str):
    """Return the session's email for a valid, unexpired token; else None."""
    if not raw_token:
        return None
    session = ApiSession.objects.filter(
        token_hash=hashlib.sha256(raw_token.encode()).hexdigest()
    ).first()
    if session is None or session.expires_at < timezone.now():
        return None
    return session.email


def drop_session(raw_token: str) -> None:
    if raw_token:
        ApiSession.objects.filter(
            token_hash=hashlib.sha256(raw_token.encode()).hexdigest()
        ).delete()


class InvalidOtp(Exception):
    pass


class Cooldown(Exception):
    pass
