"""Seed command: counts, re-anchor offset, referential-integrity rejection."""

import json
from datetime import date, timedelta

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils import timezone

from crm.models import Contact, Customer, Interaction

pytestmark = pytest.mark.django_db

ANCHOR = date(2026, 9, 1)


def test_seed_counts_and_reanchor(settings):
    call_command("load_demo_data")
    assert Customer.objects.count() == 12
    assert Contact.objects.count() == 15
    assert Interaction.objects.count() == 56

    shift = (timezone.localdate() - ANCHOR).days
    assert Customer.objects.get(id="cust_001").created_at == date(2026, 5, 12) + timedelta(days=shift)
    # newest interaction (int_056: 2026-08-31) lands at ANCHOR-1 + shift == today - 1
    newest = Interaction.objects.order_by("-occurred_at").first()
    assert newest.occurred_at == timezone.localdate() - timedelta(days=1)


def test_seed_is_idempotent(settings):
    call_command("load_demo_data")
    call_command("load_demo_data")
    assert Customer.objects.count() == 12
    assert Interaction.objects.count() == 56


BAD_FIXTURES = {
    "cross-customer-contact": {
        "customers": [{"id": "cust_001", "name": "A", "status": "prospect", "created_at": "2026-08-01"},
                      {"id": "cust_002", "name": "B", "status": "customer", "created_at": "2026-08-01"}],
        "contacts": [{"id": "contact_001", "customer_id": "cust_001", "name": "C",
                      "email": "c@x.example", "role": "Owner"}],
        "interactions": [{"id": "int_001", "customer_id": "cust_002", "contact_id": "contact_001",
                          "type": "call", "occurred_at": "2026-08-02", "notes": "x"}],
    },
    "unknown-contact": {
        "customers": [{"id": "cust_001", "name": "A", "status": "prospect", "created_at": "2026-08-01"}],
        "contacts": [],
        "interactions": [{"id": "int_001", "customer_id": "cust_001", "contact_id": "contact_x",
                          "type": "call", "occurred_at": "2026-08-02", "notes": "x"}],
    },
    "unknown-customer": {
        "customers": [],
        "contacts": [{"id": "contact_001", "customer_id": "cust_missing", "name": "C",
                      "email": "c@x.example", "role": "Owner"}],
        "interactions": [],
    },
}


@pytest.mark.parametrize("fixture_name", list(BAD_FIXTURES))
def test_bad_fixture_raises_command_error(settings, tmp_path, fixture_name):
    bad_path = tmp_path / "bad-sample.json"
    bad_path.write_text(json.dumps(BAD_FIXTURES[fixture_name]))
    settings.SAMPLE_DATA_PATH = bad_path
    with pytest.raises(CommandError):
        call_command("load_demo_data")
