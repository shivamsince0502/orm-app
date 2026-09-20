from rest_framework import serializers

from crm.models import Contact, Customer, Interaction

VALID_ACTIONS = ["done", "undo", "snooze", "pin", "unpin", "keep_open", "release"]
VALID_TONES = ["friendly", "professional", "warm", "direct"]


class InteractionCreateSerializer(serializers.Serializer):
    type = serializers.ChoiceField(choices=["email", "call", "meeting", "note"])
    contact_id = serializers.CharField(max_length=20)
    occurred_at = serializers.DateField()
    notes = serializers.CharField(trim_whitespace=False, max_length=2000)

    def validate_notes(self, value):
        if not value.strip():
            raise serializers.ValidationError("Notes must not be empty.")
        return value


class ActionSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=VALID_ACTIONS)
    snooze_until = serializers.DateField(required=False, allow_null=True)

    def validate(self, attrs):
        action = attrs["action"]
        if action == "snooze" and attrs.get("snooze_until") is None:
            raise serializers.ValidationError({"snooze_until": "Required when action is snooze."})
        if action != "snooze" and attrs.get("snooze_until") is not None:
            raise serializers.ValidationError({"snooze_until": "Only valid when action is snooze."})
        return attrs


class DraftSerializer(serializers.Serializer):
    tone = serializers.ChoiceField(choices=VALID_TONES, required=False, default="professional")
    prompt = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=500,
        help_text="Free-text instructions from the rep, injected into the draft prompt.",
    )


def contact_brief(contact: Contact) -> dict:
    return {"id": contact.id, "name": contact.name, "role": contact.role}


def interaction_brief(interaction: Interaction) -> dict:
    return {
        "id": interaction.id,
        "type": interaction.type,
        "occurred_at": interaction.occurred_at.isoformat(),
        "notes": interaction.notes,
        "contact": contact_brief(interaction.contact),
    }


def customer_brief(customer: Customer) -> dict:
    return {
        "id": customer.id,
        "name": customer.name,
        "status": customer.status,
        "created_at": customer.created_at.isoformat(),
    }
