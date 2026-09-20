"""Email-OTP login flow + send-email endpoint (locmem mail backend via test env)."""

from datetime import timedelta

import pytest
from django.core import mail
from rest_framework.test import APIClient

from crm.models import Contact, Customer, EmailOtp
from crm.services import otp

pytestmark = pytest.mark.django_db

EMAIL = "rep@example.com"


def make_customer_with_contact():
    customer = Customer.objects.create(
        id="cust_a", name="A Dental", status="prospect", created_at="2026-01-01"
    )
    contact = Contact.objects.create(
        id="contact_a", customer=customer, name="Alex", email="alex@adental.example", role="Owner"
    )
    return customer, contact


def request_otp(client, email=EMAIL):
    return client.post("/api/auth/request-otp/", {"email": email}, format="json")


def latest_otp_code(email):
    """Reconstruct the code from the DB is impossible (hashed); tests read the mail."""
    return mail.outbox[-1].subject.split(":")[-1].strip()


def login(client, email=EMAIL):
    request_otp(client, email)
    code = latest_otp_code(email)
    response = client.post("/api/auth/verify-otp/", {"email": email, "code": code}, format="json")
    assert response.status_code == 200
    return response


def test_request_otp_sends_email():
    client = APIClient()
    response = request_otp(client)
    assert response.status_code == 200
    assert response.json() == {"sent": True, "cooldown_seconds": 60}
    assert len(mail.outbox) == 1
    assert EMAIL in mail.outbox[0].to
    assert mail.outbox[0].subject.startswith("Your Practice by Numbers login code:")
    # code stored hashed only
    row = EmailOtp.objects.latest("created_at")
    assert row.code_hash != latest_otp_code(EMAIL)


def test_request_otp_cooldown():
    client = APIClient()
    assert request_otp(client).status_code == 200
    assert request_otp(client).status_code == 429


def test_request_otp_rejects_bad_email():
    client = APIClient()
    response = client.post("/api/auth/request-otp/", {"email": "not-an-email"}, format="json")
    assert response.status_code == 400


def test_verify_success_sets_cookie_and_session_works():
    client = APIClient()
    response = login(client)
    assert response.json() == {"email": EMAIL}
    cookie = response.cookies["fjq_session"]
    assert cookie.value  # raw token issued
    assert cookie["httponly"]

    # protected endpoint with cookie
    authed = APIClient()
    authed.cookies["fjq_session"] = cookie.value
    assert authed.get("/api/accounts/").status_code == 200
    assert authed.get("/api/auth/me/").json()["email"] == EMAIL

    # OTP row consumed — code is single-use
    assert EmailOtp.objects.filter(email=EMAIL, consumed=True).exists()


def test_protected_endpoints_require_login():
    client = APIClient()
    assert client.get("/api/accounts/").status_code == 401
    assert client.get("/api/accounts/cust_001/").status_code == 401
    assert client.post("/api/accounts/cust_001/actions/", {"action": "done"}, format="json").status_code == 401
    assert client.get("/api/health/").status_code == 200  # health stays open


def test_verify_wrong_code_increments_attempts_then_locks():
    client = APIClient()
    request_otp(client)
    for i in range(5):
        response = client.post(
            "/api/auth/verify-otp/", {"email": EMAIL, "code": "000000"}, format="json"
        )
        assert response.status_code == 400
    row = EmailOtp.objects.latest("created_at")
    assert row.attempts == 5 and row.consumed is True
    # even the right code no longer works after lockout
    assert client.post(
        "/api/auth/verify-otp/", {"email": EMAIL, "code": latest_otp_code(EMAIL)}, format="json"
    ).status_code == 400


def test_wrong_code_message_shows_remaining_attempts():
    client = APIClient()
    request_otp(client)
    response = client.post(
        "/api/auth/verify-otp/", {"email": EMAIL, "code": "000000"}, format="json"
    )
    assert "4 attempt(s) left" in response.json()["detail"]


def test_expired_code_rejected():
    client = APIClient()
    request_otp(client)
    row = EmailOtp.objects.latest("created_at")
    row.expires_at = row.expires_at - timedelta(days=1)
    row.save()
    code = latest_otp_code(EMAIL)
    response = client.post("/api/auth/verify-otp/", {"email": EMAIL, "code": code}, format="json")
    assert response.status_code == 400
    assert "expired" in response.json()["detail"]


def test_logout_invalidates_session():
    client = APIClient()
    login(client)
    cookie = client.cookies["fjq_session"].value
    assert client.get("/api/auth/me/").status_code == 200
    assert client.post("/api/auth/logout/").status_code == 200
    fresh = APIClient()
    fresh.cookies["fjq_session"] = cookie
    assert fresh.get("/api/auth/me/").status_code == 401


def test_send_email_to_customer_contact():
    customer, contact = make_customer_with_contact()
    client = APIClient()
    login(client)
    response = client.post(
        f"/api/accounts/{customer.id}/send-email/",
        {"contact_id": contact.id, "subject": "Quick check-in", "body": "Hi Alex!"},
        format="json",
    )
    assert response.status_code == 200
    assert response.json() == {"sent": True, "to": contact.email, "attachments": []}
    assert len(mail.outbox) == 2  # 1 OTP + 1 follow-up
    follow_up = mail.outbox[-1]
    assert follow_up.subject == "Quick check-in"
    assert contact.email in follow_up.to


def test_send_email_rejects_foreign_contact():
    customer, contact = make_customer_with_contact()
    other = Customer.objects.create(
        id="cust_b", name="B Dental", status="customer", created_at="2026-01-01"
    )
    other_contact = Contact.objects.create(
        id="contact_b", customer=other, name="Bo", email="bo@bdental.example", role="Owner"
    )
    client = APIClient()
    login(client)
    response = client.post(
        f"/api/accounts/{customer.id}/send-email/",
        {"contact_id": other_contact.id, "subject": "s", "body": "b"},
        format="json",
    )
    assert response.status_code == 400


def test_draft_prompt_over_limit_rejected():
    make_customer_with_contact()
    client = APIClient()
    login(client)
    response = client.post(
        "/api/accounts/cust_a/draft/",
        {"tone": "warm", "prompt": "x" * 501},
        format="json",
    )
    assert response.status_code == 400


def test_send_email_with_attachments():
    customer, contact = make_customer_with_contact()
    client = APIClient()
    login(client)
    response = client.post(
        f"/api/accounts/{customer.id}/send-email/",
        {
            "contact_id": contact.id,
            "subject": "Proposal attached",
            "body": "Hi Alex, see attached.",
            "attachments": [
                _simple_file("case-study.pdf", b"%PDF-1.4 fake"),
                _simple_file("pricing-notes.txt", b"notes"),
            ],
        },
        format="multipart",
    )
    assert response.status_code == 200
    assert response.json() == {
        "sent": True,
        "to": contact.email,
        "attachments": ["case-study.pdf", "pricing-notes.txt"],
    }
    sent = mail.outbox[-1]
    assert len(sent.attachments) == 2
    assert sent.attachments[0][0] == "case-study.pdf"  # (filename, content, mimetype)
    assert sent.attachments[0][2] == "application/pdf"


def test_send_email_attachment_limits():
    customer, contact = make_customer_with_contact()
    client = APIClient()
    login(client)

    too_many = [_simple_file(f"f{i}.txt", b"x") for i in range(6)]
    response = client.post(
        f"/api/accounts/{customer.id}/send-email/",
        {"contact_id": contact.id, "subject": "s", "body": "b", "attachments": too_many},
        format="multipart",
    )
    assert response.status_code == 400

    oversize = _simple_file("big.bin", b"x" * (10 * 1024 * 1024 + 1))
    response = client.post(
        f"/api/accounts/{customer.id}/send-email/",
        {"contact_id": contact.id, "subject": "s", "body": "b", "attachments": [oversize]},
        format="multipart",
    )
    assert response.status_code == 400


def _simple_file(name, content):
    import io

    from django.core.files.uploadedfile import SimpleUploadedFile

    return SimpleUploadedFile(name, content)


def test_send_email_requires_login():
    customer, contact = make_customer_with_contact()
    client = APIClient()
    response = client.post(
        f"/api/accounts/{customer.id}/send-email/",
        {"contact_id": contact.id, "subject": "s", "body": "b"},
        format="json",
    )
    assert response.status_code == 401
