"""Action state transitions (done/snooze/pin/keep_open) + stale marking (D6)."""

from django.db import transaction

from crm.models import AccountAction
from crm.services import ranking

VALID_ACTIONS = {"done", "undo", "snooze", "pin", "unpin", "keep_open", "release"}


def get_action(customer) -> AccountAction:
    """Lazily get-or-create the action row; never blocks reads."""
    action, _ = AccountAction.objects.get_or_create(customer=customer)
    return action


def apply(customer, action, snooze_until=None, today=None) -> AccountAction:
    if action not in VALID_ACTIONS:
        raise ValueError(f"Unknown action {action!r}")
    with transaction.atomic():
        row = get_action(customer)
        if action == "done":
            row.done = True
        elif action == "undo":
            row.done = False
            row.snoozed_until = None
        elif action == "snooze":
            if snooze_until is None or snooze_until <= today:
                raise ValueError("snooze_until must be a date strictly after today")
            row.snoozed_until = snooze_until
        elif action == "pin":
            row.pinned = True
        elif action == "unpin":
            row.pinned = False
        elif action == "keep_open":
            row.kept_open = True
        elif action == "release":
            row.kept_open = False
        row.save()
        if action in {"pin", "unpin", "keep_open", "release"}:
            # These change LLM inputs → ranking goes stale (D6).
            # Same-transaction write: rolls back with the action if it fails.
            ranking.mark_stale()
    return row
