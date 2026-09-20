"""Ranking lifecycle: eligibility (open-case rule), freshness, persistence, order."""

import threading

from django.core.exceptions import ObjectDoesNotExist
from django.utils import timezone

from crm.models import AccountAction, Customer, RankingRun
from crm.services import ai

_lock = threading.Lock()

HISTORY_LIMIT = 8


def month_start(today):
    return today.replace(day=1)


def is_open_case(kept_open, interactions, created_at, today) -> bool:
    """D8: kept_open OR any interaction this calendar month OR created_at this month.
    Pure predicate — testable without a DB (interactions: iterable with .occurred_at)."""
    start = month_start(today)
    if kept_open:
        return True
    if start <= created_at <= today:
        return True
    return any(start <= i.occurred_at <= today for i in interactions)


def open_case_customers(today) -> list:
    """All customers satisfying the open-case rule (D8), in stable id order."""
    kept_open_map = dict(AccountAction.objects.values_list("customer_id", "kept_open"))
    result = []
    for customer in Customer.objects.order_by("id"):
        if is_open_case(
            kept_open_map.get(customer.id, False),
            customer.interactions.all(),
            customer.created_at,
            today,
        ):
            result.append(customer)
    return result


def days_since(customer, today):
    """(today - latest occurred_at).days; None if the account has no interactions."""
    latest = customer.interactions.order_by("-occurred_at").values_list("occurred_at", flat=True).first()
    if latest is None:
        return None
    return (today - latest).days


def build_rank_inputs(customers, today) -> list[dict]:
    """Facts fed to the LLM: identity, pinned/kept_open flags, days since, last 8 interactions."""
    inputs = []
    for customer in customers:
        action = _safe_action(customer)
        history = list(
            customer.interactions.select_related("contact").order_by("-occurred_at", "-id")[:HISTORY_LIMIT]
        )
        inputs.append(
            {
                "customer_id": customer.id,
                "name": customer.name,
                "status": customer.status,
                "created_at": customer.created_at.isoformat(),
                "days_since_last_interaction": days_since(customer, today),
                "pinned": action.pinned if action else False,
                "kept_open": action.kept_open if action else False,
                "interactions": [
                    {
                        "occurred_at": i.occurred_at.isoformat(),
                        "type": i.type,
                        "contact_name": i.contact.name,
                        "role": i.contact.role,
                        "notes": i.notes,
                    }
                    for i in history
                ],
            }
        )
    return inputs


def run_ranking(today) -> RankingRun:
    """One batch LLM call over all open cases; persists a fresh (stale=False) run."""
    customers = list(open_case_customers(today))
    inputs = build_rank_inputs(customers, today)
    ranked = ai.rank_accounts(inputs, today)
    return RankingRun.objects.create(
        payload={"open_case_ids": [c.id for c in customers], "ranked": ranked},
        stale=False,
    )


def ensure_fresh_rank() -> RankingRun:
    """Return the latest run, recomputing once if stale/absent (blocking)."""
    latest = RankingRun.objects.order_by("-created_at").first()
    if latest and not latest.stale:
        return latest
    with _lock:
        latest = RankingRun.objects.order_by("-created_at").first()
        if latest and not latest.stale:
            return latest
        return run_ranking(timezone.localdate())


def mark_stale():
    """Flag the latest run stale (no-op if none exists)."""
    latest = RankingRun.objects.order_by("-created_at").first()
    if latest:
        latest.stale = True
        latest.save(update_fields=["stale"])


def ordered_queue(run) -> list[tuple[Customer, dict]]:
    """Enforced order (D7): pinned group first, then unpinned; each in payload order.
    Pinned state is read from the DB at render time — the LLM is told to rank pinned
    first, but Python enforces it regardless."""
    ranked = run.payload.get("ranked", [])
    by_id = {entry["customer_id"]: entry for entry in ranked}
    customers = Customer.objects.filter(id__in=by_id.keys()).in_bulk()
    pinned_ids = set(
        Customer.objects.filter(
            id__in=by_id.keys(), action__pinned=True
        ).values_list("id", flat=True)
    )
    ordered = []
    for wanted in (True, False):
        for entry in ranked:
            cid = entry["customer_id"]
            if (cid in pinned_ids) == wanted:
                customer = customers.get(cid)
                if customer is not None:
                    enriched = dict(entry)
                    enriched["pinned"] = wanted
                    ordered.append((customer, enriched))
    return ordered


def is_hidden(customer, today) -> bool:
    """done OR (snoozed_until AND today < snoozed_until) — visible again ON the expiry day."""
    try:
        action = customer.action
    except ObjectDoesNotExist:
        return False
    if action.done:
        return True
    return bool(action.snoozed_until and today < action.snoozed_until)


def _safe_action(customer):
    try:
        return customer.action
    except ObjectDoesNotExist:
        return None
