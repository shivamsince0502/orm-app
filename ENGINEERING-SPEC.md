# Engineering Spec — Follow-Up Queue (AI-Powered Micro-CRM)

**Version:** 2.0 (amended) · **Status:** Superseded in part by [`IMPLEMENTATION-PLAN.md`](IMPLEMENTATION-PLAN.md) · **Owner:** Take-home candidate

> **Amendment (v2.0):** The hybrid design below (deterministic scoring engine + LLM narrative) was **replaced by LLM-driven prioritization**. Where this spec conflicts with `IMPLEMENTATION-PLAN.md`, the plan wins. Amended sections: §2, §3, §5, §6, §7, §9.3, §10, §11 (see the plan's §7 checklist).

---

## 1. Overview

An internal sales-rep-facing micro-CRM for a dental SaaS company (Practice by Numbers). It loads a book of 12 practice accounts (prospects + customers); **the LLM is the sole prioritization authority** — one batch call ranks all open cases of the current month and returns tier, reason, suggested action, and a relationship summary per account. It also drafts context-grounded follow-up emails — powered by a **hosted OpenAI-compatible LLM API** (default OpenAI `gpt-4o-mini`). No numeric scores exist anywhere.

**Not in scope:** auth, multi-user, external DB, email sending, customer/contact CRUD.

---

## 2. Stack (Locked)

| Layer | Choice | Notes |
|---|---|---|
| Backend | **Django 5 + Django REST Framework** | Python 3.12; venv `backend/.venv` (host global Django must never be used); runs in its own Docker container on `:8010` on this machine (port 8000 was taken by unrelated services) |
| Database | **PostgreSQL 16** (own Docker container `followup-queue-db`; host port 5433) | `DB_*` env config; data volume persists across restarts |
| AI runtime | **Hosted OpenAI-compatible API** (`LLM_BASE_URL`/`LLM_MODEL`/`LLM_API_KEY` in `backend/.env`; default OpenAI `gpt-4o-mini`). **Required — no fallback.** |
| Frontend | **React 18 + Vite + TypeScript** | Tailwind CSS 4, React Router |
| Styling | Tailwind, teal `#0D9488` brand | Per PRD design tokens |
| Tests | pytest-django — parser/order/eligibility/staleness tests with **mocked LLM** (no real API needed) | Highest value-per-hour |
| Dev run | `runserver` (:8010 or Docker `followup-queue-backend`) + `vite` (:5173) | Vite proxies `/api` → backend |

**Why no LangChain/LangGraph:** total LLM usage is ~1 batch rank call (on cold start / staleness) + 1 per draft click. No chains, loops, or tool-use — a plain HTTP client in `services/ai.py` is sufficient.

---

## 3. Architecture

```
┌──────────────────────────────────────────────────────┐
│  React + Vite (TS)  :5173                            │
│  /            InboxPage (LLM-ranked queue)           │
│  /accounts/:id  AccountPage                          │
│  modals: Draft · Log Interaction                     │
└───────────────┬──────────────── /api proxy ──────────┘
                ▼
┌──────────────────────────────────────────────────────┐
│  Django + DRF  :8010                                 │
│  views ──► serializers                               │
│    ├── services/ranking.py   (open-case rule,        │
│    │      ensure_fresh_rank, enforced order,         │
│    │      staleness — no scoring engine)             │
│    ├── services/ai.py        (LLM API, required)     │
│    └── services/actions.py   (done/snooze/pin/       │
│           keep_open + stale marking)                 │
└───────┬──────────────────────────┬───────────────────┘
        ▼                          ▼
   PostgreSQL 16 (seeded)    Hosted LLM API (required)
   crm_Customer             gpt-oss:20b default
   crm_Interaction          503 on outage — no fallback
   crm_AccountAction        RankingRun (persisted batch
   crm_RankingRun           ranking, latest wins)
```

---

## 4. Data Models (`crm/models.py`)

```python
class Customer(models.Model):
    id = CharField(max_length=20, primary_key=True)      # "cust_001"
    name = CharField(max_length=200)
    status = CharField(max_length=20, choices=[("prospect",)*2, ("customer",)*2])
    created_at = DateField()

class Contact(models.Model):
    id = CharField(max_length=20, primary_key=True)      # "contact_001"
    customer = ForeignKey(Customer, on_delete=CASCADE, related_name="contacts")
    name, email, role = CharFields()

class Interaction(models.Model):
    id = CharField(max_length=20, primary_key=True)      # "int_001"
    customer = ForeignKey(Customer, on_delete=CASCADE, related_name="interactions")
    contact = ForeignKey(Contact, on_delete=CASCADE, related_name="interactions")
    type = CharField(choices=["email","call","meeting","note"])
    occurred_at = DateField()
    notes = TextField()

class AccountAction(models.Model):
    """Runtime queue state; at most one row per customer."""
    customer = OneToOneField(Customer, on_delete=CASCADE)
    done = BooleanField(default=False)
    snoozed_until = DateField(null=True, blank=True)
    pinned = BooleanField(default=False)          # D7 sticky-to-top
    kept_open = BooleanField(default=False)       # D9 re-admit to queue
    updated_at = DateTimeField(auto_now=True)

class RankingRun(models.Model):
    """Persisted batch LLM ranking — latest wins."""
    created_at = DateTimeField(auto_now_add=True)
    payload = JSONField()   # {"open_case_ids": [...], "ranked": [{customer_id, tier, reason, suggested_action, summary}]}
    stale = BooleanField(default=True)
```

**Seed:** management command `python manage.py load_demo_data` reads `sample-data.json` (12 / 15 / 56 rows), idempotent (truncate + reload). Referential integrity (interaction → contact → customer) validated on load. **Dates are re-anchored at seed time** (D1): every date shifts by `(today − 2026-09-01).days`; the source file is never modified.

---

## 5. API Contract

Base: `/api` · CORS: allow `localhost:5173`

| # | Method & Path | Purpose | Request | Response (key fields) |
|---|---|---|---|---|
| 1 | `GET /api/accounts/` | Inbox feed | `?status=prospect\|customer` | `{as_of, queue: [{id, name, status, rank, tier, reason, suggested_action, days_since_contact, hidden, pinned, kept_open, contact_names[]}], out_of_queue: [{id, name, status, days_since_contact, kept_open}]}` |
| 2 | `GET /api/accounts/{id}/` | Account 360 dossier | — | `{customer, in_queue, rank, tier, reason, suggested_action, summary, days_since_contact, pinned, kept_open, done, snoozed_until, contacts[], interactions[] (desc)}`; out-of-queue → `in_queue: false`, AI fields `null` |
| 3 | `POST /api/accounts/{id}/interactions/` | Log touch (never calls LLM) | `{type, contact_id, occurred_at, notes}` | `201 {interaction, days_since_contact, rerank_pending: true}` |
| 4 | `POST /api/accounts/{id}/draft/` | AI email draft | `{tone?}` | `{subject, body, grounded_sources[]}` (sources computed in Python, D12) |
| 5 | `POST /api/accounts/{id}/actions/` | Queue actions | `{action: "done"\|"undo"\|"snooze"\|"pin"\|"unpin"\|"keep_open"\|"release", snooze_until?}` | `{done, snoozed_until, pinned, kept_open}` |
| 6 | `GET /api/health/` | Health | — | `{ok, llm: bool}` (always 200) |

Rules: done/snoozed accounts stay in list (flag `hidden: true`) so undo is trivial — visible again ON the `snoozed_until` day; POST bodies validated via DRF serializer; `snooze_until` required iff `snooze`, must be > today (IST). **AI-dependent endpoints (1, 2, 4) return HTTP 503 `{"detail": "AI service unavailable"}` if the LLM API is unreachable and HTTP 502 `{"detail": "AI returned unparseable output"}` after a failed stricter re-prompt — no silent degradation.** The last good `RankingRun` stays persisted so Retry is cheap.

---

## 6. LLM Prioritization Engine (`services/ai.py` + `services/ranking.py`)

**The LLM is the sole prioritization authority (D4). One batch call** ranks all *open cases of the current month*; no scoring engine, no keyword tables, no numeric scores exist anywhere.

- **Open-case rule (D8):** an account enters the rank call iff `kept_open` OR any interaction this calendar month OR `created_at` this month. Month/timezone = Asia/Kolkata (`TIME_ZONE`); every "today" is `timezone.localdate()`.
- **Batch call:** temp 0.2, system prompt carries the judging rubric (unresolved commitments > momentum > stage-relative staleness > expansion intent > hold notes at bottom). Returns ordered `ranked[]` with `{customer_id, tier, reason, suggested_action, summary}` — validated (exact id set, valid tier, length caps), one stricter re-prompt on failure, then 502.
- **Pin invariant (D7):** the prompt tells the LLM pinned accounts must be top + high tier, but **Python enforces the final order regardless** — pinned group first, each group in LLM order.
- **Event-driven staleness (D6):** no scheduler. Interaction create, pin/unpin, keep_open/release mark the ranking stale; the next `GET /accounts` (or detail) recomputes once, blocking (skeletons). Done/snooze/undo never invalidate.
- **Display (D5):** ordered list + tier pill (high/med/low) + rank badge `#n`. `days_since_contact` is a Python-computed fact shown on cards, not a heuristic.

---

## 7. AI Service Layer (`services/ai.py`)

**Client:** OpenAI-compatible chat completions against `LLM_BASE_URL` (default `https://api.openai.com/v1`), model from `LLM_MODEL` (default `gpt-4o-mini`), key from `LLM_API_KEY` (sent as `Authorization: Bearer` when set).

**Functions:**

| Function | Prompt shape | Temp | Output |
|---|---|---|---|
| `rank_accounts(inputs, today)` | system: prioritization engine + rubric + pinned rule; user: today (IST) + per-account facts + last 8 interactions → request exact JSON shape | 0.2 | `[{customer_id, tier, reason (≤25 words), suggested_action (≤20 words), summary (2–3 sentences)}]` best-first; zero open cases → `[]` without calling the LLM |
| `draft_follow_up(customer, contact, interactions, tone, today)` | system: sales rep, no pricing/clinical claims; user: recipient, tone (friendly/professional/warm/direct), hold-note handling, last 8 interactions | 0.7 | `{subject (≤60 chars), body (120–200 words)}` signed "Sarah Jenkins, Practice by Numbers" |

**Timeouts (D14, amended — see plan §9):** rank — 90s, one retry at 180s (budget sized for the earlier local model; hosted APIs typically finish a rank in seconds); draft — 30s, one retry at 60s. `reasoning_effort` is optional (`LLM_REASONING_EFFORT`, empty default) + `max_tokens` cap sent with every call. JSON parse/validation failure → one stricter re-prompt → **502**. `ping()` checks `GET /models` (2s) for health.

**Failure semantics (no fallbacks):**
- LLM API unreachable / timeout → endpoints 1, 2, 4 return **HTTP 503** `{"detail": "AI service unavailable"}`; the UI surfaces an error banner with a Retry button
- Malformed/invalid JSON after one re-prompt retry → HTTP 502 `{"detail": "AI returned unparseable output"}`

**Robustness:** strict JSON output requested via `response_format`; parsing tolerates surrounding prose (brace extraction) but any failure escalates to 502 — never silently substituted.

**Persistence:** the batch result is stored as a `RankingRun` row (`payload`, `stale`) — replaces the v1 in-memory cache. Latest run wins; staleness is event-driven (§6); `ensure_fresh_rank()` under a `threading.Lock` recomputes at most once per stale window.

---

## 8. Frontend Spec

```
frontend/src/
├── api/client.ts            # typed fetch wrappers for the 6 endpoints
├── types.ts                 # Account, Interaction, Contact, Draft...
├── pages/InboxPage.tsx      # KPI banner, tabs (All/Prospects/Customers), search, card list
├── pages/AccountPage.tsx    # AI summary, next-step card, timeline, contacts, snapshot
├── components/
│   ├── AccountCard.tsx      # urgency pill, status chip, reason, actions bar
│   ├── DraftModal.tsx       # tone chips → generate → editable body → copy
│   ├── LogModal.tsx         # type/contact/date/notes form
│   └── TimelineItem.tsx     # type badge + meta + note
└── App.tsx                  # routes + layout (brand header, rep avatar)
```

- **States:** skeleton loaders while fetching (incl. the long re-rank window); AI endpoint 503 → inline error banner with Retry button (no degraded/offline mode)
- **Interactions:** optimistic Done/Snooze with undo toast (6s); Log modal toasts "Logged — re-ranking queue" and refetches; pin toggles optimistically then refetches (re-rank skeletons); out-of-queue rows offer Keep open
- **Assets:** `public/assets/` (brand SVG, avatars, clinic image) already generated — served via Vite `publicDir: "../public"`

---

## 9. Non-Functional Requirements

1. **Prerequisites:** an `LLM_API_KEY` in `backend/.env` (OpenAI by default, any OpenAI-compatible provider) — the app does not function without it (by design; no fallback)
2. `npm run dev` + `python manage.py runserver` (after one-time seed) = working demo
3. Unit tests (mocked LLM — no real API needed): open-case eligibility parametrized cases (month boundary, kept_open carryover, created-this-month); `ai.py` validation (unknown/duplicate/missing ids, bad tier, empty/too-long fields → one re-prompt → 502; connection error ×2 → 503); ranking lifecycle (pinned-first order, hidden rule incl. visible-on-expiry-day, stale lifecycle with exactly one re-rank, zero open cases skip the LLM); seed (12/15/56 counts, re-anchor offset, bad fixtures raise `CommandError`)
4. CORS restricted to Vite dev origin; POST input validation; no secrets in repo
5. README covers: what/why, decisions, assumptions, run steps (incl. LLM API key), what's next (per assignment)

---

## 10. Build Order (Milestones)

| # | Milestone | Exit criteria |
|---|---|---|
| M1 | Django project, models, seed command (re-anchoring), open-case rule + tests | venv Django 5.2 active; `migrate` + `load_demo_data` prints 12/15/56 re-anchored (7 in / 5 out of queue); pytest green |
| M2 | Hosted LLM API configured + `services/ai.py`: prompts, transport, validation + tests | pytest green; `rank_accounts` over seeded open cases returns 7 valid ordered entries |
| M3 | DRF endpoints 1–6 + `ensure_fresh_rank` wiring | curl returns ranked queue + out_of_queue; health ok; LLM API down → endpoints 1/2 → 503, 3/5/6 still work; pytest green |
| M4 | React inbox + Account 360 | Full UX flow works end-to-end at :5173 |
| M5 | Draft/Log modals, done/snooze/undo, pin, out-of-queue, polish, README, spec amendments | Assignment-demo-complete |

Time budget ≈ 4–6h total; M1–M2 are the safe core (≈2.5h), M3–M5 the product.

---

## 11. Key Decisions Log

1. React + Django per candidate preference; **PostgreSQL** by owner decision (replaced the original SQLite choice — own container, `DB_*` env config)
2. LLM via hosted API (default OpenAI `gpt-4o-mini`); local Ollama removed by owner decision (was `gpt-oss:20b` locally); any OpenAI-compatible provider env-swappable
3. **Replaced:** hybrid scoring (deterministic rank + LLM narrative) → **LLM-driven prioritization** — one batch call, event-refreshed, user-pinned accounts locked on top. Full rationale: `IMPLEMENTATION-PLAN.md` §1 D1–D16 (date re-anchoring, no-fallback AI outage behavior, single batch rank call, event-driven staleness, pinned invariant, open-case rule, out-of-queue handling, IST timezone, timeouts/retries, React 18.3 pin, contact search data, grounded sources computed in Python)
4. No LangChain/LangGraph — one batch call + one per draft click don't justify orchestration deps
5. Snooze stored server-side (PostgreSQL) not client-side — survives refresh, enables undo
6. **No fallbacks (explicit decision):** the hosted LLM API is a hard requirement; outages surface as 503 + retry UI, never silently degraded text
7. Backend runs in its own Docker container on :8010 on this machine (host port 8000 occupied by unrelated services); Postgres in its own container on `followup-queue-net`
