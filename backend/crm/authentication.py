"""Cookie-session authentication for the OTP login flow.

Reads the `fjq_session` cookie, validates the token hash, and exposes the
logged-in email as `request.user_email`. Pairs with DRF's IsAuthenticated.
"""

from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed

from crm.services import otp


class OtpUser:
    """Minimal user-like object for DRF's IsAuthenticated check."""

    def __init__(self, email: str):
        self.email = email
        self.is_authenticated = True
        self.is_anonymous = False


class CookieSessionAuthentication(BaseAuthentication):
    def authenticate(self, request):
        raw = request.COOKIES.get(otp.SESSION_COOKIE, "")
        email = otp.resolve_session(raw)
        if email is None:
            return None  # anonymous — IsAuthenticated will 401
        request.user_email = email
        return OtpUser(email), None

    def authenticate_header(self, request):
        return 'Cookie realm="fjq"'
