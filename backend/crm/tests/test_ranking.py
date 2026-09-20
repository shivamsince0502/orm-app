"""Ranking lifecycle: enforced order, hidden rule, staleness. DB-backed, mocked LLM."""

import json
from datetime import date, timedelta

import pytest
from django.utils import timezone

from crm.models import AccountAction, Customer, RankingRun
from crm.services import actions, ranking

pytestmark = pytest.mark.django_db

TODAY = timezone.localdate()


def make_customer(cid, pinned=False, done=False, snoozed_until=None, kept_open=False):
    customer = Customer.objects.create(
        id=cid, name=f"Customer {cid}", status="prospect", created_at=date(2026, 1, 1)
    )
    AccountAction.objects.create(
        customer=customer, pinned=pinned, done=done,
        snoozed_until=snoozed_until, kept_open=kept_open,
    )
    return customer


def make_run(order):
    ranked = [
        {"customer_id": cid, "tier": "high" if i == 0 else "medium",
         "reason": f"reason {cid}", "suggested_action": f"action {cid}",
         "summary": f"summary {cid}"}
        for i, cid in enumerate(order)
    ]
    return RankingRun.objects.create(
        payload={"open_case_ids": list(order), "ranked": ranked}, stale=False
    )


def test_pinned_first_overrides_payload_order():
    c1 = make_customer("cust_001")
    make_customer("cust_002", pinned=True)
    make_customer("cust_003")
    run = make_run(["cust_001", "cust_002", "cust_003"])  # LLM put pinned last
    ordered = ranking.ordered_queue(run)
    assert [c.id for c, _ in ordered] == ["cust_002", "cust_001", "cust_003"]
    assert ordered[0][1]["pinned"] is True
    assert c1 is not None


def test_hidden_done_and_snooze_rules():
    today = date(2026, 9, 15)
    done_customer = make_customer("cust_done", done=True)
    snoozed = make_customer("cust_snoozed", snoozed_until=today + timedelta(days=2))
    expired_today = make_customer("cust_expired", snoozed_until=today)
    visible = make_customer("cust_visible")

    assert ranking.is_hidden(done_customer, today) is True
    assert ranking.is_hidden(snoozed, today) is True
    assert ranking.is_hidden(expired_today, today) is False  # visible ON the expiry day
    assert ranking.is_hidden(visible, today) is False


def test_no_action_row_is_not_hidden():
    customer = Customer.objects.create(
        id="cust_x", name="X", status="prospect", created_at=date(2026, 1, 1)
    )
    assert ranking.is_hidden(customer, TODAY) is False


def test_stale_lifecycle_and_single_rerank(monkeypatch):
    make_customer("cust_001")
    make_customer("cust_002")

    calls = []

    def fake_rank(inputs, today):
        calls.append([i["customer_id"] for i in inputs])
        return [
            {"customer_id": cid, "tier": "low", "reason": "r", "suggested_action": "a",
             "summary": "s"}
            for cid in sorted(i["customer_id"] for i in inputs)
        ]

    monkeypatch.setattr(ranking.ai, "rank_accounts", fake_rank)

    run1 = ranking.ensure_fresh_rank()
    assert run1.stale is False
    assert len(calls) == 1

    actions.apply(Customer.objects.get(id="cust_001"), "keep_open", today=TODAY)
    run1.refresh_from_db()
    assert run1.stale is True  # keep_open marks stale (D6)

    run2 = ranking.ensure_fresh_rank()
    assert len(calls) == 2  # exactly one re-rank
    assert run2.stale is False
    assert run2.created_at >= run1.created_at

    # fresh now — no extra LLM call
    ranking.ensure_fresh_rank()
    assert len(calls) == 2


def test_zero_open_cases_empty_ranking_without_llm(monkeypatch):
    def boom(messages, temperature, timeout):
        raise AssertionError("LLM transport must not be called for zero open cases")

    monkeypatch.setattr(ranking.ai, "_post_chat", boom)
    run = ranking.run_ranking(TODAY)  # DB has no customers
    assert run.payload == {"open_case_ids": [], "ranked": []}
    assert run.stale is False


def test_days_since():
    customer = make_customer("cust_d")
    from crm.models import Contact, Interaction

    contact = Contact.objects.create(
        id="contact_d", customer=customer, name="D", email="d@x.example", role="Owner"
    )
    Interaction.objects.create(
        id="int_d", customer=customer, contact=contact, type="call",
        occurred_at=TODAY - timedelta(days=4), notes="x",
    )
    assert ranking.days_since(customer, TODAY) == 4
    assert ranking.days_since(make_customer("cust_none"), TODAY) is None


def test_payload_json_roundtrip():
    make_run(["cust_001"])
    run = RankingRun.objects.first()
    assert json.loads(json.dumps(run.payload))["ranked"][0]["customer_id"] == "cust_001"
