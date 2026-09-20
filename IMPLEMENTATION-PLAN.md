# Implementation Plan — Follow-Up Queue (Frontend + Backend)

**Status:** Approved, build-ready · **Supersedes:** `ENGINEERING-SPEC.md` §5/§6/§7 where they conflict (see §7 amendment checklist) · **Source of truth for implementation.**

---

## 0. Objective & End State

**What:** A sales-rep micro-CRM (Practice by Numbers, dental SaaS) where **the LLM is the sole prioritization authority**. One batch LLM call ranks all *open cases of the current month* and returns, per account: tier (high/medium/low), reason, suggested action, and a relationship summary. **No numeric scores exist anywhere.**

**Why:** The rep needs to know who needs attention, why, and what to do next. The original hybrid design (deterministic formula + LLM narrative) was replaced by owner decision: prioritization itself is LLM-driven, event-refreshed, with user-pinned accounts locked to the top.

**End state:** `runserver` + `vite` + `ollama serve` running. Seeded SQLite (12/15/56 rows, dates re-anchored). Inbox shows the LLM-ranked queue (rank badges + tier pills, pinned accounts on top), a collapsed "Out of queue" section for accounts with no activity this month, Log/Draft modals, done/snooze with undo. No AI fallback: AI-dependent endpoints 503 with a Retry UI when Ollama is down.

---

## 1. Final Decision Log (all resolved — implementer makes no decisions)

| # | Decision | Resolution |
|---|---|---|
| D1 | Stale seed dates (newest interaction Aug 31 vs run date) | **Re-anchor at seed:** `load_demo_data` shifts every date by `today − 2026-09-01`. `sample-data.json` untouched. Keeps LLM narratives coherent ("decision in September") and yields a mixed in/out-of-queue set. |
| D2 | Ollama runtime | **Local, required, no fallback.** Install via `brew install ollama`; model `gpt-oss:20b` (`OLLAMA_MODEL` env-swappable). OpenAI-compatible endpoint at `OLLAMA_BASE_URL` (default `http://localhost:11434/v1`). |
| D3 | AI outage behavior | **HTTP 503 `{"detail": "AI service unavailable"}` + Retry UI. Never heuristic/degraded text.** Last good `RankingRun` stays persisted so Retry is cheap. |
| D4 | Prioritization | **Single batch LLM rank call** over open cases only. LLM returns ordered `ranked[]` + tier + texts. No scoring engine, no keyword tables, no numeric score. |
| D5 | Display | **Ordered list + LLM tier pill** (high/med/low). Rank badge `#n`. No scores. |
| D6 | Refresh trigger | **Event-driven, no scheduler.** Mutations that change LLM inputs (interaction create, pin/unpin, keep_open/release) mark the ranking stale; next `GET /accounts` (or detail) recomputes once (blocking, skeletons). Done/snooze/undo do **not** invalidate. |
| D7 | Pinned accounts | `pinned` flag persists in DB; prompt tells the LLM pinned must be top+high; **Python enforces final order regardless** (pinned group first, each group in LLM order). Sticky until unpin. |
| D8 | Open-case rule | Account enters the rank call iff `kept_open` **OR** any interaction this calendar month **OR** `created_at` this month. Month/timezone = **Asia/Kolkata** (`TIME_ZONE`). |
| D9 | Out-of-queue accounts | Shown in a **collapsed "Out of queue (N)" section** with a **Keep open** button (sets `kept_open`, re-admits on next re-rank). Detail page works with `in_queue: false` + banner. |
| D10 | Log interaction flow | POST never calls the LLM, never 503s. Marks stale; returns interaction + `days_since_contact`. Frontend toasts "Logged — re-ranking queue" and refetches. |
| D11 | Django runtime | **venv `backend/.venv`** (host global Django 4.2 must never be used). `Django~=5.2`, `djangorestframework~=3.16`. |
| D12 | `grounded_sources` (draft) | Computed in Python = the exact interactions fed to the prompt (`{id, type, occurred_at, excerpt: notes[:80]}`). Not LLM-cited. |
| D13 | Draft recipient & tone | Recipient = contact of most recent interaction, else first contact. Tones: `friendly | professional | warm | direct`, default `professional`. |
| D14 | Timeouts/retries | Batch rank: 60s timeout, one retry at 120s. Draft: 30s, one retry at 60s. JSON failure: one stricter re-prompt → **502** `{"detail": "AI returned unparseable output"}`. |
| D15 | Frontend stack | React 18.3 (pinned; Vite template ships 19 — downgrade), react-router-dom 6, Vite 6, TypeScript, Tailwind 4 via `@tailwindcss/vite`. `publicDir: "../public"` serves existing root assets. No state/query libraries — plain fetch hooks. |
| D16 | Sort/search data | Search needs contact names → endpoint 1 returns `contact_names[]` per account. Sort control: rank (default) | days-since (client-side re-sort). |

---

## 2. Architecture

```
React 18 + Vite (TS) :5173                Ollama (required)
/            InboxPage                     gpt-oss:20b @ localhost:11434/v1
/accounts/:id AccountPage                  OpenAI-compatible chat completions
modals: Draft · Log                        503/502 on failure — no fallback
        │  /api proxy → :8000
        ▼
Django 5.2 + DRF :8000  (backend/, venv)
views ─► serializers
  ├─► services/ranking.py   open-case rule · ensure_fresh_rank() · enforced order · staleness
  ├─► services/ai.py        rank_accounts() · draft_follow_up() · ping() · prompts · validation
  └─► services/actions.py   done/snooze/pin/keep_open transitions (+ stale marking)
        ▼
SQLite: Customer · Contact · Interaction · AccountAction(done, snoozed_until, pinned, kept_open)
        RankingRun(payload JSON, stale)          ← persisted LLM ranking, latest wins
```

Ownership: **all LLM concerns live in `services/ai.py`** (prompts, HTTP, parsing, error classes). **All ranking lifecycle logic lives in `services/ranking.py`** (eligibility, freshness, persistence, ordering). **All action state in `services/actions.py`.** Views stay thin wiring; zero feature logic elsewhere.

---

## 3. Backend Plan

### 3.1 Scaffold & pins

```
backend/
├── manage.py · requirements.txt · pytest.ini
├── config/            __init__ · settings · urls · wsgi · asgi
└── crm/
    ├── models.py · serializers.py · views.py · urls.py · apps.py
    ├── services/      ai.py · ranking.py · actions.py
    ├── management/commands/load_demo_data.py
    └── tests/         test_open_cases.py · test_ai_validation.py
                       test_ranking.py · test_seed.py
```

**Commands:** `python3 -m venv .venv` → `source .venv/bin/activate` → `pip install -r requirements.txt` → `django-admin startproject config .` → `python manage.py startapp crm`.

**requirements.txt:**
```
Django~=5.2
djangorestframework~=3.16
django-cors-headers~=6.0
requests~=2.32
pytest~=9.0
pytest-django~=4.1
```

**pytest.ini:** `DJANGO_SETTINGS_MODULE = config.settings`

### 3.2 `config/settings.py` (exact)

- `INSTALLED_APPS`: `django.contrib.contenttypes`, `django.contrib.auth`, `rest_framework`, `corsheaders`, `crm` (no admin/sessions).
- `MIDDLEWARE`: `SecurityMiddleware`, `CorsMiddleware`, `CommonMiddleware`.
- `REST_FRAMEWORK`: `DEFAULT_AUTHENTICATION_CLASSES: []`, `DEFAULT_PERMISSION_CLASSES: [AllowAny]`, `DEFAULT_RENDERER_CLASSES: [JSONRenderer]`, `DEFAULT_PARSER_CLASSES: [JSONParser]`.
- `CORS_ALLOWED_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]`.
- `TIME_ZONE = "Asia/Kolkata"`, `USE_TZ = True`. **Every "today" uses `django.utils.timezone.localdate()`** (IST).
- `OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434/v1")`; `OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "gpt-oss:20b")`.
- `SAMPLE_DATA_PATH = BASE_DIR.parent / "sample-data.json"` (root file stays canonical).
- `config/urls.py`: `path("api/", include("crm.urls"))` only.

### 3.3 `crm/models.py` (exact)

```python
class Customer(models.Model):
    id  = CharField(max_length=20, primary_key=True)          # "cust_001"
    name = CharField(max_length=200)
    status = CharField(max_length=20, choices=[("prospect", "Prospect"), ("customer", "Customer")])
    created_at = DateField()

class Contact(models.Model):
    id = CharField(max_length=20, primary_key=True)           # "contact_001"
    customer = ForeignKey(Customer, on_delete=CASCADE, related_name="contacts")
    name = CharField(max_length=200); email = CharField(max_length=200); role = CharField(max_length=100)

class Interaction(models.Model):
    id = CharField(max_length=20, primary_key=True)           # "int_001"
    customer = ForeignKey(Customer, on_delete=CASCADE, related_name="interactions")
    contact = ForeignKey(Contact, on_delete=CASCADE, related_name="interactions")
    type = CharField(max_length=20, choices=[("email","Email"),("call","Call"),("meeting","Meeting"),("note","Note")])
    occurred_at = DateField()
    notes = TextField()

class AccountAction(models.Model):
    customer = OneToOneField(Customer, on_delete=CASCADE, related_name="action")
    done = BooleanField(default=False)
    snoozed_until = DateField(null=True, blank=True)
    pinned = BooleanField(default=False)
    kept_open = BooleanField(default=False)
    updated_at = DateTimeField(auto_now=True)

class RankingRun(models.Model):
    created_at = DateTimeField(auto_now_add=True)
    payload = JSONField()            # {"open_case_ids": [...], "ranked": [{customer_id, tier, reason, suggested_action, summary}]}
    stale = BooleanField(default=True)
```

Generate initial migration once; keep it committed. `db.sqlite3` gitignored. `AccountAction` row is get-or-created lazily (never blocks reads; defaults False/None via `customer.action` guarded by `ObjectDoesNotExist` → helper `get_action(customer)` in `services/actions.py`).

### 3.4 `load_demo_data.py` (seed + re-anchor)

1. Read `SAMPLE_DATA_PATH`. **Validate referential integrity first** (every interaction's contact belongs to its customer; FKs exist) — raise `CommandError` on violation before touching the DB.
2. `shift = (localdate() − date(2026, 9, 1)).days` (may be negative — fine).
3. Truncate `Customer` (cascades contacts/interactions/actions), then bulk-create customers, contacts, interactions with `created_at`/`occurred_at` shifted by `shift` days.
4. Print `Seeded 12 customers / 15 contacts / 56 interactions (re-anchored +N days)`.

Idempotent by truncate+reload. Expected post-seed open-case split (D8): **7 in queue** (cust_001, 002, 005, 006, 009, 011, 012 — activity this month after re-anchor) / **5 out of queue** (cust_003, 004, 007, 008, 010).

### 3.5 `services/ai.py` — LLM client, prompts, validation

**Errors:** `AIServiceUnavailable` (→503), `AIUnparseableResponse` (→502).

**Transport:** `requests.post(f"{OLLAMA_BASE_URL}/chat/completions", json=payload, timeout=t)`. Payload: `{"model": OLLAMA_MODEL, "messages": [...], "temperature": t, "response_format": {"type": "json_object"}}`. Any `requests.RequestException` → retry per D14 → `AIServiceUnavailable`.

**JSON extraction:** first `{` … last `}` substring → `json.loads`. Failure → one re-prompt (append assistant error + stricter user instruction) → failure → `AIUnparseableResponse`.

**`rank_accounts(inputs) -> list[dict]`** — single call, temp 0.2, timeout 60s, one retry at 120s.

*System prompt (exact):*
> You are the prioritization engine for a sales rep at Practice by Numbers, a dental SaaS company. Rank accounts that need attention. Judging rubric, in order of weight: (1) unresolved commitments — proposals/pricing/contract sent awaiting reply, questions the account asked that were never answered, follow-ups they requested; (2) deal momentum — recent positive engagement outranks stalled silence; (3) staleness relative to stage — silence after a demo or proposal is more urgent than routine quiet; (4) explicit expansion intent (second location, second account, multi-location); (5) explicit hold notes ("do not push", "wait for") must rank at the bottom and be respected. RULE: accounts marked `pinned=true` MUST occupy the top of the ranking and have tier "high". Output ONLY valid JSON, no markdown, no extra text.

*User template (exact):*
```
Today is {today} (IST). Rank these open cases from highest to lowest priority.

{per account:}
### {customer_id} — {name}
pinned={pinned} kept_open={kept_open} status={status} customer_since={created_at} days_since_last_interaction={days | "none"}
History (most recent first, last 8):
- [{occurred_at}] {type} with {contact_name} ({role}): {notes}

Return JSON exactly: {"ranked": [{"customer_id": str, "tier": "high"|"medium"|"low", "reason": str (<=25 words, why now), "suggested_action": str (<=20 words, concrete next step), "summary": str (2-3 sentences: stage, sentiment, open asks)}]}
"ranked" must contain every customer_id exactly once, best first.
```

*Validation (raise → re-prompt once → 502):* top-level `ranked` list; customer_id set **exactly equals** input ids (no missing/duplicate/unknown); `tier ∈ {high, medium, low}`; `reason ≤ 220` chars, `suggested_action ≤ 180`, `summary ≤ 600`; all non-empty strings.

*Zero open cases:* skip the LLM entirely, return `[]` (not an error).

**`draft_follow_up(customer, contact, interactions, tone) -> {subject, body}`** — temp 0.7, timeout 30s, one retry at 60s. System: sales rep for Practice by Numbers; never mention prices/discounts or make clinical claims; output only JSON. User: today, recipient (`{contact.name} ({role})` at `{customer.name}`, a `{status}`), tone, pinned/hold note handling ("Account is on hold — keep the email gentle, low-pressure" if any hold phrase "do not push"/"wait for" appears in notes, else "none"), last 8 interactions, request `{"subject": <=60 chars, "body": 120–200 words, grounded in history, clear low-pressure CTA, sign off "Sarah Jenkins, Practice by Numbers"}`.

**`ping() -> bool`** — `GET {OLLAMA_BASE_URL}/models`, timeout 2s.

### 3.6 `services/ranking.py` — eligibility, freshness, order

```python
def open_case_customers(today) -> QuerySet[Customer]:
    # kept_open OR interaction occurred_at in [first_of_month(today), today] OR created_at in same month
def build_rank_inputs(customers, today) -> list[dict]        # facts: name, status, created_at, days_since (computed), pinned, kept_open, last 8 interactions
def run_ranking(today) -> RankingRun                         # ai.rank_accounts -> validate -> RankingRun.objects.create(payload, stale=False)
def ensure_fresh_rank() -> RankingRun:
    latest = RankingRun.objects.order_by("-created_at").first()
    if latest and not latest.stale: return latest
    with _lock:                                               # double-checked; module-level threading.Lock
        latest = ...recheck...; if fresh: return latest
        return run_ranking(localdate())
def mark_stale():                                            # latest run -> stale=True (no-op if none)
def ordered_queue(run) -> list[(Customer, entry)]:
    # pinned group first, then unpinned; each group in payload "ranked" order
def is_hidden(customer, today) -> bool:
    # action.done OR (snoozed_until AND today < snoozed_until)   [visible again ON snoozed_until day]
def days_since(customer, today) -> int | None                # (today - latest occurred_at).days; None if no interactions
```

`days_since` is a **fact** (arithmetic), computed in Python and shown on cards — not a heuristic.

### 3.7 `services/actions.py`

```python
def apply(customer, action, snooze_until=None, today) -> AccountAction
    # done: done=True | undo: done=False, snoozed_until=None
    # snooze: snoozed_until (validated > today) | pin: pinned=True | unpin: pinned=False
    # keep_open: kept_open=True | release: kept_open=False
    # pin/unpin/keep_open/release additionally call ranking.mark_stale()  (D6)
```

### 3.8 Endpoints (`crm/urls.py` + `views.py`, function-based `@api_view`)

| # | Route | Behavior | Success response (exact fields) | Errors |
|---|---|---|---|---|
| 1 | `GET /api/accounts/?status=prospect\|customer` | `ensure_fresh_rank()` → open cases (filtered by status) in enforced order; hidden kept but flagged | `{as_of, queue: [{id, name, status, rank, tier, reason, suggested_action, days_since_contact, hidden, pinned, kept_open, contact_names[]}], out_of_queue: [{id, name, status, days_since_contact, kept_open}]}` | 503 |
| 2 | `GET /api/accounts/{id}/` | `ensure_fresh_rank()`; per-account entry from latest run; contacts + interactions (desc, with contact `{id,name,role}`) | `{customer{id,name,status,created_at}, in_queue, rank, tier, reason, suggested_action, summary, days_since_contact, pinned, kept_open, done, snoozed_until, contacts[], interactions[]}` — out-of-queue: `in_queue:false`, AI fields `null` | 404, 503 |
| 3 | `POST /api/accounts/{id}/interactions/` | Validate: `type ∈ 4`, `contact_id` belongs to customer, `occurred_at` ISO date **not in future (IST)**, `notes` 1–2000 chars. id = `int_{max+1:03d}`. `ranking.mark_stale()` | 201 `{interaction{id,type,occurred_at,notes,contact{id,name,role}}, days_since_contact, rerank_pending: true}` | 400, 404 |
| 4 | `POST /api/accounts/{id}/draft/` | `{tone?}` (D13); recipient = latest interaction's contact else first; grounded_sources computed in Python (D12) | `{subject, body, grounded_sources: [{id, type, occurred_at, excerpt}]}` | 400, 404, 502, 503 |
| 5 | `POST /api/accounts/{id}/actions/` | `{action: done\|undo\|snooze\|pin\|unpin\|keep_open\|release, snooze_until?}` (`snooze_until` required iff snooze, must be > today) | `{done, snoozed_until, pinned, kept_open}` | 400, 404 |
| 6 | `GET /api/health/` | `ai.ping()` | 200 `{ok: true, ollama: bool}` (always 200) | — |

Validation errors return DRF's `{"field": ["msg"]}` (400). `AIServiceUnavailable` → 503 `{"detail": "AI service unavailable"}`; `AIUnparseableResponse` → 502 `{"detail": "AI returned unparseable output"}` — mapped in one small exception handler in `views.py`.

**Concurrency:** `ensure_fresh_rank` under `threading.Lock` (dev server is threaded) so concurrent stale GETs fire **one** LLM call. Worst-case blocking: ~120s (retry) before 503.

### 3.9 Tests (`crm/tests/`, mocked LLM — no Ollama needed)

- **test_open_cases.py** — `@pytest.mark.parametrize` with `SimpleNamespace` customers/interactions + injected `today`: interaction-this-month ✓; previous-month-only ✗; created-this-month ✓; kept_open carryover ✓; exact month-boundary day (1st).
- **test_ai_validation.py** — monkeypatch `requests.post` sequences: valid payload passes; unknown id / duplicate / missing id / bad tier / empty string → one re-prompt then `AIUnparseableResponse`; connection error ×2 → `AIServiceUnavailable`.
- **test_ranking.py** — pinned-first ordering overrides payload order; hidden rule (done hidden; snoozed visible on expiry day); stale lifecycle: fresh run → `apply(keep_open)` marks stale → `ensure_fresh_rank` calls mocked `rank_accounts` exactly once and clears stale; zero open cases → empty ranking without LLM call.
- **test_seed.py** (`django_db`) — `call_command("load_demo_data")` with `SAMPLE_DATA_PATH` override: counts 12/15/56; dates shifted by expected offset; crafted bad-JSON fixture raises `CommandError`.

---

## 4. Frontend Plan

### 4.1 Scaffold & config

`npm create vite@latest frontend -- --template react-ts`, then **pin** `react@^18.3.1 react-dom@^18.3.1 @types/react@^18 @types/react-dom@^18`, add `react-router-dom@^6.30`, `tailwindcss@^4 @tailwindcss/vite@^4`; keep `vite@^6`, `@vitejs/plugin-react@^4`.

**vite.config.ts:** `plugins: [react(), tailwindcss()]`, `publicDir: "../public"` (serves existing root assets at `/assets/...`), `server: { proxy: { "/api": "http://localhost:8000" } }`.

**src/index.css:** `@import "tailwindcss";` + `@theme { --color-brand: #0D9488; --color-brand-dark: #0F766E; }`.

### 4.2 File map

```
src/
├── main.tsx · App.tsx (router, brand header, toast provider) · index.css
├── types.ts                 # mirrors §3.8 responses exactly
├── api/client.ts            # getAccounts/getAccount/logInteraction/draftFollowUp/postAction/getHealth
│                            # generic req<T>: fetch /api/*, throws ApiError{status, detail}
├── pages/InboxPage.tsx      # KPI banner, tabs, search, sort, queue list, out-of-queue section, empty state
├── pages/AccountPage.tsx    # hero, summary/next-step cards, timeline, contacts, quick actions
└── components/
    ├── AccountCard.tsx      # rank badge, tier pill, status chip, days since, reason, action bar
    ├── DraftModal.tsx · LogModal.tsx · TimelineItem.tsx
    ├── TierPill.tsx · ErrorBanner.tsx · Skeleton.tsx · Toast.tsx
```

### 4.3 Component behavior (exact)

**InboxPage** — fetch on mount + Retry. KPI banner: `"{n} high · {m} medium · {k} out of queue · ranked {as_of time ago}"`. Tabs All/Prospects/Customers (status filter, refetch). Search (client-side, name + contact_names). Sort toggle: Rank (default) | Days since (client re-sort). Queue cards in server order; hidden cards excluded visually. Collapsed `Out of queue (N)` section below: rows with name, status chip, days since, **Keep open** button → `postAction(keep_open)` → optimistic badge → refetch (re-rank skeletons). Empty state "All caught up" when zero visible.

**AccountCard** — `#rank` badge; TierPill (high `red-600` / medium `amber-600` / low `slate-500`; adjust to mockups); status chip (prospect teal outline / customer slate); `"{n}d since last contact"` ("Never contacted" if null); LLM reason + suggested action; action bar: **Pin** ★ (optimistic toggle → `postAction` → refetch), **Done** ✓, **Snooze** (Tomorrow/3 days/1 week), **Draft** ✉️, card click → detail.

**Done/Snooze** — POST immediately, optimistic hide, toast with **Undo (6s)** → `postAction(undo)` → unhide. Server is source of truth.

**AccountPage** — hero (`/assets/practices/apex-dental-exterior.jpg`), name/status/days/rank badge + TierPill. If `in_queue=false`: banner "Not in this month's queue — [Keep open]". Summary card (LLM summary), Next-step card (suggested_action + reason; pinned shows ★). Contacts panel. Timeline (TimelineItem: type icon badge email/call/meeting/note, date, contact name, notes). Quick actions: Log, Draft, Done, Snooze, Pin.

**LogModal** — type select, contact select (from detail), date (default today, `max=today`), notes textarea. Submit → POST → toast "Logged — re-ranking queue" → close → refetch (skeletons during the one re-rank).

**DraftModal** — tone chips (Friendly/Professional/Warm/Direct, default Professional) → Generate (spinner) → editable subject + body → **Copy** (`navigator.clipboard`) → grounded sources list ("Grounded in N interactions"). 503/502 → ErrorBanner + Retry.

**ErrorBanner** — `ApiError` → message ("AI service unavailable — is Ollama running?" for 503; "AI returned unparseable output" for 502) + Retry button (re-invokes the fetch).

**Skeleton** — pulse placeholders shaped as cards (inbox) / sections (detail) while fetching, including the long re-rank window.

**Toast** — single-slot, 6s auto-dismiss, optional action button (Undo). Provided via context in `App.tsx`; no library.

**App.tsx** — `BrowserRouter`; header: `/assets/brand/practice-by-numbers-logo.svg`, "Follow-Up Queue", rep avatar `/assets/avatars/sarah-jenkins.jpg`. Routes `/` and `/accounts/:id`. Visual target: `mockups/*.jpg` (view manually).

---

## 5. Data & Control Flow (post-implementation)

- **Cold start / stale load:** `GET /accounts` → fresh run exists? → serve instantly : one batch LLM call (skeletons ~15–40s) → persist `RankingRun` → response. Ollama down → 503 + Retry; last-good run retained.
- **Log interaction:** modal → POST (AI-free, always works) → row created, ranking flagged stale → refetch triggers exactly one re-rank → new order/tier/reason appear.
- **Pin:** ★ → POST pin (stale) → refetch; pinned account locked to top by Python sort regardless of LLM behavior.
- **Keep open:** adds an out-of-queue account back into the next rank call's input set.
- **Draft:** per-click LLM call, Python-computed grounded sources, 30s/60s retry, 502/503 semantics.
- **Restart:** all DB state (customers, interactions, pins, done/snooze, last ranking) survives; a stale/absent run simply recomputes on first load.

---

## 6. Build Order & Verification

| # | Milestone | Exit criteria / verify |
|---|---|---|
| M1 | Backend scaffold, models + migration, seed command, `open_case_customers`, tests (§3.9 minus AI ones) | `.venv` active (`python -c "import django; print(django.__version__)"` → 5.2.x); `manage.py migrate && manage.py load_demo_data` prints 12/15/56 re-anchored; `pytest` green |
| M2 | `brew install ollama && ollama pull gpt-oss:20b`; `services/ai.py` complete + validation tests | `pytest` green; quick `manage.py shell` snippet: `rank_accounts` over seeded open cases returns 7 valid ordered entries |
| M3 | serializers/views/urls/CORS + `ensure_fresh_rank` wiring | `curl :8000/api/accounts/` → ranked queue + out_of_queue; `curl :8000/api/health/`; stop Ollama → endpoints 1/2 return 503, 3/5/6 still work; `pytest` green |
| M4 | Vite scaffold + config + types/client + Inbox + Account 360 | browse full flow at :5173 |
| M5 | Draft/Log modals, done/snooze/undo, pin, out-of-queue, polish vs mockups; amend `ENGINEERING-SPEC.md` (§7); write `README.md` | assignment-demo-complete |

**Runbook (goes in README):** `brew install ollama && ollama pull gpt-oss:20b` (once) → `ollama serve` → `backend/: source .venv/bin/activate && python manage.py migrate && python manage.py load_demo_data && python manage.py runserver` → `frontend/: npm install && npm run dev` → open :5173.

---

## 7. Spec Amendment Checklist (apply in M5)

`ENGINEERING-SPEC.md`: §2 (tests row → "parser/order/eligibility tests with mocked LLM"), §3 diagram (ranking service, `RankingRun`, no scoring), §5 (endpoint 1/2/3/5 fields + new actions per §3.8; remove score/tier-from-score, add rank/tier/pinned/kept_open/out_of_queue/as_of), §6 → "LLM Prioritization Engine" (batch call, rubric, open-case rule D8, pin invariant D7, event-driven staleness D6, IST), §7 (`rank_accounts` replaces `enrich_account`; timeouts D14; persisted run replaces in-memory cache), §9.3 (new test list), §10 M1/M3 exit criteria, Decision Log (#3 replaced; add D1–D16 of this plan). `FEATURES.md`: add supersession banner pointing here.

---

## 8. Risks & Edge Cases

- **Batch JSON is the main failure surface** (12-account structured output from gpt-oss:20b): schema-strict prompt + `response_format` + validation + one re-prompt → 502; persisted last-good run keeps Retry cheap.
- **Non-deterministic ranks across sessions** — accepted (temp 0.2, persisted "as of" timestamp displayed).
- **Long re-rank window (~15–40s, worst 120s)** after every interaction log / pin / keep-open — accepted (D6); skeletons + toasts set expectations.
- **Pinned disobedience:** if the LLM ignores pins, Python order still guarantees placement; only reasons may lag until next re-rank.
- **Ollama concurrency:** single batch call — no parallelism concerns (ThreadPool design was removed with D4).
- **Out-of-queue accounts have no fresh AI text** until kept open (by definition of the call's input set) — detail page degrades to facts + banner, not to fake AI text.
- **IST boundaries:** all date logic via `timezone.localdate()`; month boundary tested at the 1st.
- **runserver autoreload** spawns two processes — harmless now (no scheduler thread; `ensure_fresh` lock is per-process and dev-server requests hit one process).
- **Global Django 4.2 vs venv 5.2** — README warns to always activate `backend/.venv`.
- **Date re-anchoring shifts seed dates daily if re-seeded** — scores/ranks recompute naturally; document in README.

---

## 9. Implementation Addendum (post-build deviations)

The plan stayed the source of truth; these deviations were forced by environment/physics and are documented in `README.md`:

1. **Port/Docker (user instruction):** host port 8000 was occupied by unrelated services → backend runs in its own Docker container (`followup-queue-backend`) on **:8010** (Vite proxy + README updated). The venv at `backend/.venv` remains for tests/dev per D11.
2. **`django-cors-headers~=4.9`:** plan's `~=6.0` doesn't exist on PyPI.
3. **D14 rank timeouts 90s/180s (was 60/120):** measured ~13.5 tok/s for gpt-oss:20b on this machine; a schema-conform batch answer needs ~30–40s warm but can exceed 60s. Drafts keep 30/60.
4. **Ollama service tuning:** `OLLAMA_CONTEXT_LENGTH=8192` (default 4096 truncated the ~3.4k-token rank prompt mid-generation → empty responses), plus `OLLAMA_FLASH_ATTENTION=1`, `OLLAMA_KV_CACHE_TYPE=q8_0`. Every LLM call also sends OpenAI-standard `reasoning_effort: "low"` and a `max_tokens` cap — gpt-oss's hidden reasoning channel otherwise burns 1500+ tokens before answering and blows every timeout.
5. **Exception handler location:** lives in `crm/exceptions.py` (leaf module), not `views.py` — a dotted `EXCEPTION_HANDLER` pointing into `views.py` gets burned by an import-order cycle (views imports DRF decorators, which resolve `api_settings` mid-import and cache the DRF default). Relatedly, `config/settings.py`'s `REST_FRAMEWORK` block is **string-only**: importing rest-framework classes there silently voids the whole block during Django bootstrap.
6. **Pinned-first enforcement** reads the pinned flag from the DB at render time (not from the LLM payload), so pin/unpin applies on the next response even before a re-rank.
7. **PostgreSQL replaces SQLite (owner decision, supersedes §2/§3 architecture sketches):** DB runs in its own container (`followup-queue-db` on `followup-queue-net`, volume `followup-queue-pgdata`, published on host :5433 since :5432 is taken); backend container migrates/seeds/serves via `wait_for_db`. `DATABASES` is `DB_*` env-driven (`django.db.backends.postgresql`, psycopg 3). `db.sqlite3` removed entirely.
8. **Local Ollama removed (owner decision, supersedes D2):** the LLM now runs exclusively on a hosted OpenAI-compatible API (`LLM_BASE_URL`/`LLM_MODEL`/`LLM_API_KEY` in `backend/.env`; default OpenAI `gpt-4o-mini`). The client was already OpenAI-compatible, so only env/headers changed (Bearer auth added, `reasoning_effort` now optional via `LLM_REASONING_EFFORT`, default omitted).
7. **PostgreSQL replaces SQLite (owner decision, supersedes §2/§3 architecture sketches):** DB runs in its own container (`followup-queue-db` on `followup-queue-net`, volume `followup-queue-pgdata`, published on host :5433 since :5432 is taken); backend container migrates/seeds/serves via `wait_for_db`. `DATABASES` is `DB_*` env-driven (`django.db.backends.postgresql`, psycopg 3). `db.sqlite3` removed entirely.
