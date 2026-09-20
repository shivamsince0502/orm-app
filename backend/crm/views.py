"""Endpoint wiring. Feature logic lives in services/; auth endpoints in auth_views.py."""

import mimetypes as _mimetypes
import os

from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    parser_classes,
    permission_classes,
)
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from crm.authentication import CookieSessionAuthentication
from crm.models import Contact, Customer, Interaction
from crm.serializers import (
    ActionSerializer,
    DraftSerializer,
    InteractionCreateSerializer,
    contact_brief,
    customer_brief,
    interaction_brief,
)
from crm.services import actions, ai, emailer, ranking
from crm.services.ranking import HISTORY_LIMIT


def _get_customer(customer_id) -> Customer:
    return get_object_or_404(Customer, id=customer_id)


def _action_state(customer):
    row = actions.get_action(customer)
    return {
        "pinned": row.pinned,
        "kept_open": row.kept_open,
        "done": row.done,
        "snoozed_until": row.snoozed_until.isoformat() if row.snoozed_until else None,
    }


@api_view(["GET"])
@authentication_classes([CookieSessionAuthentication])
@permission_classes([IsAuthenticated])
def accounts_list(request):
    status_filter = request.query_params.get("status")
    today = timezone.localdate()
    run = ranking.ensure_fresh_rank()

    queue = []
    for rank, (customer, entry) in enumerate(ranking.ordered_queue(run), start=1):
        if status_filter and customer.status != status_filter:
            continue
        row = actions.get_action(customer)
        queue.append(
            {
                "id": customer.id,
                "name": customer.name,
                "status": customer.status,
                "rank": rank,
                "tier": entry["tier"],
                "reason": entry["reason"],
                "suggested_action": entry["suggested_action"],
                "days_since_contact": ranking.days_since(customer, today),
                "hidden": ranking.is_hidden(customer, today),
                "pinned": row.pinned,
                "kept_open": row.kept_open,
                "contact_names": list(customer.contacts.values_list("name", flat=True)),
            }
        )

    open_ids = set(run.payload.get("open_case_ids", []))
    out_ids = set(Customer.objects.values_list("id", flat=True)) - open_ids
    out_of_queue = []
    for customer in Customer.objects.filter(id__in=out_ids).order_by("name"):
        if status_filter and customer.status != status_filter:
            continue
        row = actions.get_action(customer)
        out_of_queue.append(
            {
                "id": customer.id,
                "name": customer.name,
                "status": customer.status,
                "days_since_contact": ranking.days_since(customer, today),
                "kept_open": row.kept_open,
            }
        )

    return Response(
        {
            "as_of": run.created_at.isoformat(),
            "queue": queue,
            "out_of_queue": out_of_queue,
        }
    )


@api_view(["GET"])
@authentication_classes([CookieSessionAuthentication])
@permission_classes([IsAuthenticated])
def account_detail(request, customer_id):
    customer = _get_customer(customer_id)
    today = timezone.localdate()
    run = ranking.ensure_fresh_rank()

    ordered = ranking.ordered_queue(run)
    entry = next((e for _, e in ordered if e["customer_id"] == customer.id), None)
    rank = next((i for i, (_, e) in enumerate(ordered, start=1)
                 if e["customer_id"] == customer.id), None)

    contacts = [
        {"id": c.id, "name": c.name, "email": c.email, "role": c.role}
        for c in customer.contacts.order_by("name")
    ]
    interactions = [
        interaction_brief(i)
        for i in customer.interactions.select_related("contact").order_by("-occurred_at", "-id")
    ]

    state = _action_state(customer)
    return Response(
        {
            "customer": customer_brief(customer),
            "in_queue": entry is not None,
            "rank": rank,
            "tier": entry["tier"] if entry else None,
            "reason": entry["reason"] if entry else None,
            "suggested_action": entry["suggested_action"] if entry else None,
            "summary": entry["summary"] if entry else None,
            "days_since_contact": ranking.days_since(customer, today),
            **state,
            "contacts": contacts,
            "interactions": interactions,
        }
    )


@api_view(["POST"])
@authentication_classes([CookieSessionAuthentication])
@permission_classes([IsAuthenticated])
def interaction_create(request, customer_id):
    customer = _get_customer(customer_id)
    serializer = InteractionCreateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data
    today = timezone.localdate()

    try:
        contact = customer.contacts.get(id=data["contact_id"])
    except customer.contacts.model.DoesNotExist:
        raise ValidationError({"contact_id": ["Contact does not belong to this customer."]})
    if data["occurred_at"] > today:
        raise ValidationError({"occurred_at": ["Date cannot be in the future."]})

    max_num = 0
    for iid in Interaction.objects.values_list("id", flat=True):
        try:
            max_num = max(max_num, int(iid.split("_")[1]))
        except (IndexError, ValueError):
            continue
    interaction = Interaction.objects.create(
        id=f"int_{max_num + 1:03d}",
        customer=customer,
        contact=contact,
        type=data["type"],
        occurred_at=data["occurred_at"],
        notes=data["notes"],
    )

    ranking.mark_stale()
    return Response(
        {
            "interaction": {
                **interaction_brief(interaction),
                "contact": contact_brief(contact),
            },
            "days_since_contact": ranking.days_since(customer, today),
            "rerank_pending": True,
        },
        status=status.HTTP_201_CREATED,
    )


@api_view(["POST"])
@authentication_classes([CookieSessionAuthentication])
@permission_classes([IsAuthenticated])
def draft(request, customer_id):
    customer = _get_customer(customer_id)
    serializer = DraftSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    interactions = list(
        customer.interactions.select_related("contact", "customer").order_by(
            "-occurred_at", "-id"
        )[:HISTORY_LIMIT]
    )
    if interactions:
        recipient = interactions[0].contact
    else:
        recipient = customer.contacts.order_by("id").first()
        if recipient is None:
            raise ValidationError({"detail": ["Customer has no contacts to draft for."]})

    result = ai.draft_follow_up(
        customer, recipient, interactions, serializer.validated_data.get("tone", "professional"),
        timezone.localdate(),
        extra_instructions=serializer.validated_data.get("prompt"),
    )
    grounded_sources = [
        {
            "id": i.id,
            "type": i.type,
            "occurred_at": i.occurred_at.isoformat(),
            "excerpt": i.notes[:80],
        }
        for i in interactions
    ]
    return Response(
        {"subject": result["subject"], "body": result["body"], "grounded_sources": grounded_sources}
    )


@api_view(["POST"])
@authentication_classes([CookieSessionAuthentication])
@permission_classes([IsAuthenticated])
def action_apply(request, customer_id):
    customer = _get_customer(customer_id)
    serializer = ActionSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data
    today = timezone.localdate()

    try:
        row = actions.apply(customer, data["action"], snooze_until=data.get("snooze_until"), today=today)
    except ValueError as exc:
        raise ValidationError({"detail": [str(exc)]})

    return Response(
        {
            "done": row.done,
            "snoozed_until": row.snoozed_until.isoformat() if row.snoozed_until else None,
            "pinned": row.pinned,
            "kept_open": row.kept_open,
        }
    )


class SendEmailSerializer(serializers.Serializer):
    contact_id = serializers.CharField(max_length=20)
    subject = serializers.CharField(max_length=200)
    body = serializers.CharField(trim_whitespace=False, max_length=10000)


MAX_ATTACHMENTS = 5
MAX_TOTAL_ATTACHMENT_BYTES = 10 * 1024 * 1024  # 10MB


@api_view(["POST"])
@authentication_classes([CookieSessionAuthentication])
@permission_classes([IsAuthenticated])
@parser_classes([JSONParser, MultiPartParser])
def send_email(request, customer_id):
    """Send an approved follow-up draft to one of this customer's contacts.

    Accepts JSON (no attachments) or multipart/form-data with optional
    `attachments` files (max 5, 10MB total). Files are streamed straight into
    the outgoing email — never persisted on disk.
    """
    customer = _get_customer(customer_id)
    data = {
        "contact_id": request.data.get("contact_id"),
        "subject": request.data.get("subject"),
        "body": request.data.get("body"),
    }
    serializer = SendEmailSerializer(data=data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data

    try:
        contact = Contact.objects.get(id=data["contact_id"], customer=customer)
    except Contact.DoesNotExist:
        raise ValidationError({"contact_id": ["Contact does not belong to this customer."]})

    files = request.FILES.getlist("attachments")
    if len(files) > MAX_ATTACHMENTS:
        raise ValidationError({"attachments": [f"At most {MAX_ATTACHMENTS} files allowed."]})
    if sum(f.size for f in files) > MAX_TOTAL_ATTACHMENT_BYTES:
        raise ValidationError({"attachments": ["Attachments exceed 10 MB total."]})

    attachments = []
    for f in files:
        mimetype = _mimetypes.guess_type(f.name)[0] or "application/octet-stream"
        attachments.append((os.path.basename(f.name), f.read(), mimetype))

    try:
        emailer.send_email(
            contact.email,
            data["subject"].strip(),
            data["body"].strip(),
            attachments=attachments,
        )
    except emailer.EmailDeliveryError as exc:
        return Response({"detail": f"Email send failed: {exc}"}, status=502)

    return Response(
        {"sent": True, "to": contact.email, "attachments": [a[0] for a in attachments]}
    )


@api_view(["GET"])
def health(request):
    return Response({"ok": True, "llm": ai.ping()})
