"""ai.py validation & transport behavior with mocked requests.post (no real LLM needed)."""

import json
from datetime import date
from types import SimpleNamespace

import pytest
import requests

from crm.services import ai

TODAY = date(2026, 9, 15)

INPUTS = [
    {"customer_id": "cust_001", "name": "A", "status": "prospect", "created_at": "2026-08-01",
     "days_since_last_interaction": 3, "pinned": False, "kept_open": False, "interactions": []},
    {"customer_id": "cust_002", "name": "B", "status": "customer", "created_at": "2026-08-02",
     "days_since_last_interaction": 5, "pinned": False, "kept_open": False, "interactions": []},
]

VALID_RANKED = {
    "ranked": [
        {"customer_id": "cust_001", "tier": "high", "reason": "Proposal awaiting reply",
         "suggested_action": "Follow up on proposal", "summary": "Hot prospect. Waiting."},
        {"customer_id": "cust_002", "tier": "low", "reason": "Satisfied customer",
         "suggested_action": "Send check-in email", "summary": "Healthy account."},
    ]
}


class FakeResponses:
    """Sequence-aware requests.post fake. Items: str body | Exception."""

    def __init__(self, items):
        self.items = list(items)
        self.calls = []

    def __call__(self, url, json=None, timeout=None, headers=None, **kwargs):
        self.calls.append({"url": url, "json": json, "timeout": timeout, "headers": headers or {}})
        item = self.items.pop(0)
        if isinstance(item, Exception):
            raise item
        return SimpleNamespace(
            status_code=200,
            raise_for_status=lambda: None,
            json=lambda: {"choices": [{"message": {"content": item}}]},
        )


def _body(ranked):
    return json.dumps({"ranked": ranked})


def _entry(cid, **overrides):
    entry = {
        "customer_id": cid, "tier": "medium", "reason": "r" * 10,
        "suggested_action": "s" * 10, "summary": "m" * 30,
    }
    entry.update(overrides)
    return entry


def test_valid_payload_passes(monkeypatch):
    fake = FakeResponses([json.dumps(VALID_RANKED)])
    monkeypatch.setattr(requests, "post", fake)
    result = ai.rank_accounts(INPUTS, TODAY)
    assert [e["customer_id"] for e in result] == ["cust_001", "cust_002"]
    assert len(fake.calls) == 1
    assert fake.calls[0]["json"]["response_format"] == {"type": "json_object"}
    assert fake.calls[0]["json"]["temperature"] == 0.2
    assert "reasoning_effort" not in fake.calls[0]["json"]  # default: omitted (hosted models)
    assert fake.calls[0]["timeout"] == ai.TIMEOUT_RANK[0]


def test_wrapped_in_prose_json_still_parses(monkeypatch):
    body = "Here you go:\n```json\n" + json.dumps(VALID_RANKED) + "\n```"
    fake = FakeResponses([body])
    monkeypatch.setattr(requests, "post", fake)
    result = ai.rank_accounts(INPUTS, TODAY)
    assert len(result) == 2


@pytest.mark.parametrize(
    "ranked",
    [
        # unknown id
        [_entry("cust_001"), _entry("cust_999")],
        # duplicate id
        [_entry("cust_001"), _entry("cust_001")],
        # missing id
        [_entry("cust_001")],
        # bad tier
        [_entry("cust_001", tier="urgent"), _entry("cust_002")],
        # empty string field
        [_entry("cust_001", reason=""), _entry("cust_002")],
        # over-long reason (220 limit)
        [_entry("cust_001", reason="r" * 221), _entry("cust_002")],
    ],
    ids=["unknown-id", "duplicate-id", "missing-id", "bad-tier", "empty-string", "too-long"],
)
def test_invalid_payload_reprompts_once_then_502(monkeypatch, ranked):
    fake = FakeResponses([_body(ranked), _body(ranked)])
    monkeypatch.setattr(requests, "post", fake)
    with pytest.raises(ai.AIUnparseableResponse):
        ai.rank_accounts(INPUTS, TODAY)
    assert len(fake.calls) == 2  # exactly one stricter re-prompt
    second_messages = fake.calls[1]["json"]["messages"]
    assert second_messages[-1]["role"] == "user"
    assert "ONLY the JSON" in second_messages[-1]["content"]


def test_second_chance_valid_rescues(monkeypatch):
    bad = _body([_entry("cust_001")])  # missing cust_002
    fake = FakeResponses([bad, json.dumps(VALID_RANKED)])
    monkeypatch.setattr(requests, "post", fake)
    result = ai.rank_accounts(INPUTS, TODAY)
    assert len(result) == 2


def test_connection_error_twice_raises_unavailable(monkeypatch):
    fake = FakeResponses(
        [requests.ConnectionError("down"), requests.ConnectionError("still down")]
    )
    monkeypatch.setattr(requests, "post", fake)
    with pytest.raises(ai.AIServiceUnavailable):
        ai.rank_accounts(INPUTS, TODAY)
    assert len(fake.calls) == 2
    assert fake.calls[0]["timeout"] == ai.TIMEOUT_RANK[0]   # first attempt
    assert fake.calls[1]["timeout"] == ai.TIMEOUT_RANK[1]   # retry (D14)


def test_api_key_sent_as_bearer_header(monkeypatch, settings):
    settings.LLM_API_KEY = "sk-test-123"
    fake = FakeResponses([json.dumps(VALID_RANKED)])
    monkeypatch.setattr(requests, "post", fake)
    ai.rank_accounts(INPUTS, TODAY)
    assert fake.calls[0]["headers"]["Authorization"] == "Bearer sk-test-123"


def test_no_api_key_no_auth_header(monkeypatch, settings):
    settings.LLM_API_KEY = ""
    fake = FakeResponses([json.dumps(VALID_RANKED)])
    monkeypatch.setattr(requests, "post", fake)
    ai.rank_accounts(INPUTS, TODAY)
    assert "Authorization" not in fake.calls[0]["headers"]


def test_reasoning_effort_included_when_set(monkeypatch, settings):
    settings.LLM_REASONING_EFFORT = "low"
    fake = FakeResponses([json.dumps(VALID_RANKED)])
    monkeypatch.setattr(requests, "post", fake)
    ai.rank_accounts(INPUTS, TODAY)
    assert fake.calls[0]["json"]["reasoning_effort"] == "low"


def test_reasoning_effort_disabled_when_env_empty(monkeypatch, settings):
    settings.LLM_REASONING_EFFORT = ""
    fake = FakeResponses([json.dumps(VALID_RANKED)])
    monkeypatch.setattr(requests, "post", fake)
    ai.rank_accounts(INPUTS, TODAY)
    assert "reasoning_effort" not in fake.calls[0]["json"]


def test_empty_inputs_skip_llm():
    assert ai.rank_accounts([], TODAY) == []


def test_draft_includes_rep_prompt(monkeypatch):
    fake = FakeResponses([json.dumps({"subject": "Quick check-in", "body": "Hi there."})])
    monkeypatch.setattr(requests, "post", fake)
    result = ai.draft_follow_up(
        customer := SimpleNamespace(name="A", status="prospect"),
        contact := SimpleNamespace(name="Alex", role="Owner"),
        interactions=[],
        tone="warm",
        today=TODAY,
        extra_instructions="  Mention the free trial. ",
    )
    assert result == {"subject": "Quick check-in", "body": "Hi there."}
    user_content = fake.calls[0]["json"]["messages"][1]["content"]
    assert "Extra instructions from the rep (follow these): Mention the free trial." in user_content


def test_draft_blank_prompt_is_dropped(monkeypatch):
    fake = FakeResponses([json.dumps({"subject": "s", "body": "b"})])
    monkeypatch.setattr(requests, "post", fake)
    ai.draft_follow_up(
        SimpleNamespace(name="A", status="prospect"),
        SimpleNamespace(name="Alex", role="Owner"),
        [],
        "professional",
        TODAY,
        extra_instructions="   ",
    )
    assert "Extra instructions" not in fake.calls[0]["json"]["messages"][1]["content"]
