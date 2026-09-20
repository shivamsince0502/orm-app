"""Auth views: request/verify OTP, session cookie, logout, whoami."""

from django.conf import settings
from rest_framework import serializers, status
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from crm.authentication import CookieSessionAuthentication
from crm.services import emailer, otp


class RequestOtpSerializer(serializers.Serializer):
    email = serializers.EmailField()


class VerifyOtpSerializer(serializers.Serializer):
    email = serializers.EmailField()
    code = serializers.RegexField(r"^\d{6}$")


def _set_session_cookie(response, token):
    response.set_cookie(
        otp.SESSION_COOKIE,
        token,
        max_age=otp.SESSION_TTL_DAYS * 24 * 3600,
        httponly=True,
        samesite="Lax",
        secure=settings.SESSION_COOKIE_SECURE,
        path="/",
    )


@api_view(["POST"])
def request_otp(request):
    serializer = RequestOtpSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    email = serializer.validated_data["email"].strip().lower()
    try:
        otp.request_otp(email)
    except otp.Cooldown:
        return Response(
            {"detail": "Please wait a minute before requesting another code."},
            status=status.HTTP_429_TOO_MANY_REQUESTS,
        )
    except ValueError as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    except emailer.EmailDeliveryError:
        return Response({"detail": "Could not send the email."}, status=502)
    return Response({"sent": True, "cooldown_seconds": otp.OTP_RESEND_COOLDOWN_SECONDS})


@api_view(["POST"])
def verify_otp(request):
    serializer = VerifyOtpSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    email = serializer.validated_data["email"].strip().lower()
    code = serializer.validated_data["code"]
    try:
        token = otp.verify_otp(email, code)
    except otp.InvalidOtp as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    response = Response({"email": email})
    _set_session_cookie(response, token)
    return response


@api_view(["POST"])
def logout(request):
    otp.drop_session(request.COOKIES.get(otp.SESSION_COOKIE, ""))
    response = Response({"ok": True})
    response.delete_cookie(otp.SESSION_COOKIE, path="/")
    return response


@api_view(["GET"])
@authentication_classes([CookieSessionAuthentication])
@permission_classes([IsAuthenticated])
def me(request):
    return Response({"email": request.user_email})
