"""Seed demo data from sample-data.json, re-anchoring dates to today.

Re-anchor rule (D1): every date in the sample is shifted by
(localdate() - 2026-09-01).days so narratives stay coherent relative to
"today". The source file is never modified.
"""

import json
from datetime import date, timedelta

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from django.conf import settings

from crm.models import Contact, Customer, Interaction, RankingRun

ANCHOR = date(2026, 9, 1)


class Command(BaseCommand):
    help = "Load demo data from sample-data.json with dates re-anchored to today."

    def handle(self, *args, **options):
        path = settings.SAMPLE_DATA_PATH
        try:
            with open(path) as f:
                data = json.load(f)
        except FileNotFoundError:
            raise CommandError(f"Sample data not found at {path}")

        self._validate(data)

        today = timezone.localdate()
        shift = (today - ANCHOR).days

        Customer.objects.all().delete()  # cascades contacts/interactions/actions
        RankingRun.objects.all().delete()

        Customer.objects.bulk_create(
            [
                Customer(
                    id=c["id"],
                    name=c["name"],
                    status=c["status"],
                    created_at=date.fromisoformat(c["created_at"]) + timedelta(days=shift),
                )
                for c in data["customers"]
            ]
        )
        Contact.objects.bulk_create(
            [
                Contact(
                    id=c["id"],
                    customer_id=c["customer_id"],
                    name=c["name"],
                    email=c["email"],
                    role=c["role"],
                )
                for c in data["contacts"]
            ]
        )
        Interaction.objects.bulk_create(
            [
                Interaction(
                    id=i["id"],
                    customer_id=i["customer_id"],
                    contact_id=i["contact_id"],
                    type=i["type"],
                    occurred_at=date.fromisoformat(i["occurred_at"]) + timedelta(days=shift),
                    notes=i["notes"],
                )
                for i in data["interactions"]
            ]
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded {len(data['customers'])} customers / "
                f"{len(data['contacts'])} contacts / "
                f"{len(data['interactions'])} interactions "
                f"(re-anchored {'+' if shift >= 0 else ''}{shift} days)"
            )
        )

    @staticmethod
    def _validate(data):
        """Referential integrity checks before touching the DB."""
        customer_ids = {c["id"] for c in data.get("customers", [])}
        contact_customer = {}
        for c in data.get("contacts", []):
            if c["customer_id"] not in customer_ids:
                raise CommandError(f"Contact {c['id']} references unknown customer {c['customer_id']}")
            contact_customer[c["id"]] = c["customer_id"]

        valid_types = {"email", "call", "meeting", "note"}
        seen_interaction_ids = set()
        for i in data.get("interactions", []):
            if i["customer_id"] not in customer_ids:
                raise CommandError(
                    f"Interaction {i['id']} references unknown customer {i['customer_id']}"
                )
            if i["contact_id"] not in contact_customer:
                raise CommandError(
                    f"Interaction {i['id']} references unknown contact {i['contact_id']}"
                )
            if contact_customer[i["contact_id"]] != i["customer_id"]:
                raise CommandError(
                    f"Interaction {i['id']}: contact {i['contact_id']} does not belong to "
                    f"customer {i['customer_id']}"
                )
            if i["type"] not in valid_types:
                raise CommandError(f"Interaction {i['id']} has invalid type {i['type']!r}")
            if i["id"] in seen_interaction_ids:
                raise CommandError(f"Duplicate interaction id {i['id']}")
            seen_interaction_ids.add(i["id"])
