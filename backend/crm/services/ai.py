"""All LLM concerns: prompts, HTTP transport, JSON extraction, validation, error types.

Errors:
  - AIServiceUnavailable  -> HTTP 503 (LLM API down / network)
  - AIUnparseableResponse -> HTTP 502 (bad JSON after one stricter re-prompt)
"""

import json
import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

TIMEOUT_RANK = (90, 180)     # D14 amended: measured ~13.5 tok/s on this machine —
                             # a schema-conform batch answer needs ~110-140s
TIMEOUT_DRAFT = (30, 60)
TEMPERATURE_RANK = 0.2
TEMPERATURE_DRAFT = 0.7
MAX_TOKENS_RANK = 2200       # safety valve: schema-conform answers are ~1100-1500 tokens
MAX_TOKENS_DRAFT = 1500

TIER_LIMITS = {"reason": 220, "suggested_action": 180, "summary": 600}
VALID_TIERS = {"high", "medium", "low"}
VALID_TONES = {"friendly", "professional", "warm", "direct"}

HOLD_PHRASES = ("do not push", "wait for")


class AIServiceUnavailable(Exception):
    pass


class AIUnparseableResponse(Exception):
    pass


# ---------------------------------------------------------------- transport


def _headers():
    headers = {}
    if settings.LLM_API_KEY:
        headers["Authorization"] = f"Bearer {settings.LLM_API_KEY}"
    return headers


def _post_chat(messages, temperature, timeout, max_tokens):
    """One transport attempt; returns message content (may be None if body is malformed)."""
    payload = {
        "model": settings.LLM_MODEL,
        "messages": messages,
        "temperature": temperature,
        "response_format": {"type": "json_object"},
        "max_tokens": max_tokens,
    }
    if settings.LLM_REASONING_EFFORT:
        # gpt-oss is a reasoning model: without this it burns 1500+ hidden
        # reasoning tokens before the answer and blows every timeout budget.
        payload["reasoning_effort"] = settings.LLM_REASONING_EFFORT
    response = requests.post(
        f"{settings.LLM_BASE_URL}/chat/completions",
        json=payload,
        headers=_headers(),
        timeout=timeout,
    )
    response.raise_for_status()
    data = response.json()
    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        return None


def _chat(messages, temperature, timeouts, max_tokens):
    """Transport with one retry (D14). Any RequestException -> AIServiceUnavailable."""
    last_exc = None
    for timeout in timeouts:
        try:
            return _post_chat(messages, temperature, timeout, max_tokens)
        except requests.RequestException as exc:
            last_exc = exc
            # Surface the provider's own error (401 bad key, 404 bad model, 400 bad
            # request…) in container logs — the API response stays the generic 503.
            provider_error = getattr(exc, "response", None)
            logger.warning(
                "LLM call failed: %s %s",
                type(exc).__name__,
                (provider_error.text[:300] if provider_error is not None and provider_error.text else ""),
            )
    raise AIServiceUnavailable() from last_exc


def _extract_json(content):
    """First '{' ... last '}' substring -> json.loads; None on failure."""
    if not content:
        return None
    start, end = content.find("{"), content.rfind("}")
    if start == -1 or end == -1 or end < start:
        return None
    try:
        parsed = json.loads(content[start : end + 1])
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _chat_json(messages, temperature, timeouts, max_tokens, validator):
    """Chat -> parsed+validated JSON dict. One stricter re-prompt, then AIUnparseableResponse."""
    conversation = list(messages)
    for _ in range(2):
        content = _chat(conversation, temperature, timeouts, max_tokens)
        parsed = _extract_json(content)
        error = None
        if parsed is None:
            error = "Your previous reply was not valid JSON."
        else:
            error = validator(parsed)
        if error is None:
            return parsed
        conversation = conversation + [
            {"role": "assistant", "content": content or ""},
            {
                "role": "user",
                "content": (
                    f"That output was invalid: {error} "
                    "Respond again with ONLY the JSON object requested earlier — "
                    "no markdown fences, no commentary, no trailing text."
                ),
            },
        ]
    raise AIUnparseableResponse()


# ---------------------------------------------------------------- ranking


RANK_SYSTEM_PROMPT = (
    "You are the prioritization engine for a sales rep at Practice by Numbers, a dental SaaS "
    "company. Rank accounts that need attention. Judging rubric, in order of weight: "
    "(1) unresolved commitments — proposals/pricing/contract sent awaiting reply, questions the "
    "account asked that were never answered, follow-ups they requested; "
    "(2) deal momentum — recent positive engagement outranks stalled silence; "
    "(3) staleness relative to stage — silence after a demo or proposal is more urgent than "
    "routine quiet; "
    "(4) explicit expansion intent (second location, second account, multi-location); "
    "(5) explicit hold notes (\"do not push\", \"wait for\") must rank at the bottom and be "
    "respected. RULE: accounts marked `pinned=true` MUST occupy the top of the ranking and have "
    "tier \"high\". Output ONLY valid JSON, no markdown, no extra text. "
    "Reasoning: low"
)


def _rank_user_prompt(today, inputs):
    blocks = []
    for item in inputs:
        days = item["days_since_last_interaction"]
        lines = [
            f"### {item['customer_id']} — {item['name']}",
            (
                f"pinned={str(item['pinned']).lower()} "
                f"kept_open={str(item['kept_open']).lower()} "
                f"status={item['status']} customer_since={item['created_at']} "
                f"days_since_last_interaction={days if days is not None else 'none'}"
            ),
            "History (most recent first, last 8):",
        ]
        for i in item["interactions"]:
            lines.append(
                f"- [{i['occurred_at']}] {i['type']} with {i['contact_name']} ({i['role']}): {i['notes']}"
            )
        if not item["interactions"]:
            lines.append("- (no interactions)")
        blocks.append("\n".join(lines))
    return (
        f"Today is {today.isoformat()} (IST). Rank these open cases from highest to lowest "
        f"priority.\n\n"
        + "\n\n".join(blocks)
        + "\n\nReturn JSON exactly: {\"ranked\": [{\"customer_id\": str, \"tier\": "
        "\"high\"|\"medium\"|\"low\", \"reason\": str (<=25 words, why now), \"suggested_action\": "
        "str (<=20 words, concrete next step), \"summary\": str (2-3 sentences: stage, sentiment, "
        "open asks)}]}\n"
        "\"ranked\" must contain every customer_id exactly once, best first."
    )


def _make_rank_validator(expected_ids):
    expected = set(expected_ids)

    def validate(parsed):
        ranked = parsed.get("ranked")
        if not isinstance(ranked, list) or not ranked:
            return "top-level \"ranked\" must be a non-empty list."
        seen = set()
        for entry in ranked:
            if not isinstance(entry, dict):
                return "each ranked entry must be an object."
            cid = entry.get("customer_id")
            if cid not in expected:
                return f"unknown customer_id {cid!r}."
            if cid in seen:
                return f"duplicate customer_id {cid!r}."
            seen.add(cid)
            if entry.get("tier") not in VALID_TIERS:
                return f"tier for {cid!r} must be high, medium, or low."
            for field, limit in TIER_LIMITS.items():
                value = entry.get(field)
                if not isinstance(value, str) or not value.strip():
                    return f"{field} for {cid!r} must be a non-empty string."
                if len(value) > limit:
                    return f"{field} for {cid!r} exceeds {limit} characters."
        if seen != expected:
            missing = ", ".join(sorted(expected - seen))
            return f"missing customer_id(s): {missing}."
        return None

    return validate


def rank_accounts(inputs, today) -> list[dict]:
    """Single batch rank call over open cases. Zero inputs -> [] without an LLM call."""
    if not inputs:
        return []
    messages = [
        {"role": "system", "content": RANK_SYSTEM_PROMPT},
        {"role": "user", "content": _rank_user_prompt(today, inputs)},
    ]
    parsed = _chat_json(
        messages, TEMPERATURE_RANK, TIMEOUT_RANK, MAX_TOKENS_RANK,
        _make_rank_validator([item["customer_id"] for item in inputs]),
    )
    return parsed["ranked"]


# ---------------------------------------------------------------- drafting


DRAFT_SYSTEM_PROMPT = (
    "You are a sales rep for Practice by Numbers, a dental SaaS company. Write follow-up emails "
    "grounded in the interaction history you are given. Never mention prices, discounts, or "
    "contract terms, and never make clinical claims. Output ONLY valid JSON, no markdown, "
    "no extra text. "
    "Reasoning: low"
)


def _draft_user_prompt(today, customer, contact, interactions, tone, extra_instructions=None):
    notes_text = " ".join(i.notes.lower() for i in interactions)
    if any(phrase in notes_text for phrase in HOLD_PHRASES):
        hold_instruction = "Account is on hold — keep the email gentle, low-pressure."
    else:
        hold_instruction = "none"
    history_lines = [
        f"- [{i.occurred_at.isoformat()}] {i.type} with {i.contact.name} ({i.contact.role}): {i.notes}"
        for i in interactions
    ] or ["- (no interactions)"]
    extra_line = (
        f"\nExtra instructions from the rep (follow these): {extra_instructions}\n"
        if extra_instructions
        else ""
    )
    return (
        f"Today is {today.isoformat()} (IST).\n"
        f"Recipient: {contact.name} ({contact.role}) at {customer.name}, a {customer.status} of "
        "Practice by Numbers.\n"
        f"Tone: {tone}.\n"
        f"Hold note: {hold_instruction}\n"
        "Recent interaction history (most recent first, last 8):\n"
        + "\n".join(history_lines)
        + extra_line
        + "\n\nReturn JSON exactly: {\"subject\": str (<=60 chars), \"body\": str (120-200 words, "
        "grounded in the history above, clear low-pressure call to action, sign off "
        "\"Sarah Jenkins, Practice by Numbers\")}"
    )


def _validate_draft(parsed):
    subject = parsed.get("subject")
    body = parsed.get("body")
    if not isinstance(subject, str) or not subject.strip():
        return "subject must be a non-empty string."
    if len(subject) > 60:
        return "subject exceeds 60 characters."
    if not isinstance(body, str) or not body.strip():
        return "body must be a non-empty string."
    return None


def draft_follow_up(customer, contact, interactions, tone, today, extra_instructions=None) -> dict:
    """Per-click draft. Returns {subject, body}. extra_instructions: rep's free-text prompt."""
    if tone not in VALID_TONES:
        raise ValueError(f"tone must be one of {sorted(VALID_TONES)}")
    extra = (extra_instructions or "").strip() or None
    if extra and len(extra) > 500:
        raise ValueError("extra_instructions must be at most 500 characters.")
    messages = [
        {"role": "system", "content": DRAFT_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": _draft_user_prompt(today, customer, contact, interactions, tone, extra),
        },
    ]
    return _chat_json(
        messages, TEMPERATURE_DRAFT, TIMEOUT_DRAFT, MAX_TOKENS_DRAFT, _validate_draft
    )


# ---------------------------------------------------------------- health


def ping() -> bool:
    try:
        response = requests.get(
            f"{settings.LLM_BASE_URL}/models", headers=_headers(), timeout=2
        )
        return response.status_code == 200
    except requests.RequestException:
        return False
