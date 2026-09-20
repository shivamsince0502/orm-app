# Follow-Up Queue — Feature Specification (Frontend + Backend)

> **Superseded:** this feature list predates the LLM-prioritization decision. The implemented product follows [`IMPLEMENTATION-PLAN.md`](IMPLEMENTATION-PLAN.md) (LLM-ranked queue, tier pills, pinned accounts, out-of-queue section, event-driven re-ranking). Kept for historical context.

An AI-powered micro-CRM for a sales rep at a dental SaaS company (Practice by Numbers) managing 12 practice accounts. The rep sees who needs attention, why, and what to do next — with minimal manual effort.

---

## 1. Frontend Features

### F1. Priority Inbox (Home Screen)
- Ranked list of all accounts sorted by urgency score (highest first)
- Each card shows:
  - Account name + status badge (prospect / customer)
  - Days since last contact (e.g., "7d since last contact")
  - AI/heuristic one-liner: **why it needs attention + suggested next action**
  - Urgency indicator (high / medium / low color coding)
- Empty state when all actions are cleared ("All caught up")

### F2. Account 360 View (Detail Screen)
- Opens on clicking an inbox card
- **AI relationship summary** (2-3 sentences: current stage, sentiment, open asks)
- Full **interaction timeline** (reverse chronological) with type icons (email / call / meeting / note), date, contact name, and notes
- **Contacts panel** — name, role, email for the account
- **Suggested next step** card with "why" reasoning
- Quick actions: Log interaction, Draft follow-up, Mark done, Snooze

### F3. Filters & Search
- Toggle tabs: All / Prospects / Customers
- Text search across account names and contact names
- Sort control: by urgency (default) or days-since-contact

### F4. Mark Done / Snooze
- Mark a suggested action as done → removed from queue, score recalculated
- Snooze (tomorrow / 3 days / 1 week) → hidden until snooze expires, then re-queued
- Optimistic UI update with undo toast

### F5. Log Interaction
- Modal form: type (email / call / meeting / note), contact, date, notes
- Instantly appears in account timeline and resets days-since-contact
- Updates urgency score and AI summary

### F6. AI Follow-Up Draft (Wow Feature)
- One click on an account → generates a ready-to-send follow-up email
- Grounded in that account's actual interaction history (references their proposal, demo, open questions, stated timeline)
- Shown in an editable composer with Copy-to-clipboard
- Tone-aware: respects account-specific cues (e.g., "do not push aggressively" notes)

### F7. UI/UX Polish (Non-Functional)
- Loads in <2s; skeleton loaders while AI generates
- Clean, minimal dental-SaaS aesthetic (white, soft blues/greens)
- Responsive layout (desktop + tablet)
- No login required — demo mode
- Graceful degradation: if AI/API key unavailable, heuristic text is shown instead of AI text

---

## 2. Backend Features

### B1. REST API (Node/Express or Next.js API routes)
| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/accounts` | All accounts with urgency scores + reasons (inbox feed) |
| GET | `/api/accounts/:id` | Full detail: contacts, timeline, AI summary, next step |
| POST | `/api/accounts/:id/interactions` | Log a new interaction |
| POST | `/api/accounts/:id/draft` | Generate AI follow-up email draft |
| POST | `/api/accounts/:id/actions` | Mark done / snooze |
| GET | `/api/health` | Health check |

### B2. Urgency Scoring Engine (Heuristic)
- Deterministic scoring, no LLM needed:
  - Days since last interaction (staleness) — primary signal
  - Deal stage signals (proposal sent & awaiting reply, demo done & no follow-up, explicit "high-intent" notes)
  - Status weight (prospects slightly boosted vs. satisfied customers)
  - Negative cues respected (e.g., "do not push before September meeting" lowers score)
- Outputs: score (0-100), tier (high/medium/low), human-readable reason

### B3. AI Service Layer (LLM)
- Provider-agnostic wrapper (OpenAI / Anthropic), reads key from env
- Three functions:
  - `summarizeAccount(interactions)` → 2-3 sentence relationship summary
  - `suggestNextAction(account, interactions)` → next step + why
  - `draftFollowUp(account, interactions)` → email subject + body grounded in history
- Prompt includes only that account's data (context-focused, cheap calls)
- **Fallback:** if no API key or call fails → return heuristic-generated text (app never breaks)
- Response caching (in-memory) to avoid repeat token spend

### B4. Data Layer
- Loads `sample-data.json` (12 customers, 15 contacts, 56 interactions) at startup
- In-memory store; runtime mutations (logged interactions, done/snooze) persist for the session
- Optional: write-through to a local JSON file so restarts keep changes
- Referential integrity validated on load (interaction → contact → customer)

### B5. Non-Functional (Backend)
- Zero-config run: `npm install && npm run dev` starts server + frontend
- No database, no auth, no external services required (beyond optional LLM key)
- P95 API response < 200ms for non-AI endpoints
- AI endpoints stream/timeout-capped (8s) with heuristic fallback
- CORS enabled for local dev; input validation on POST bodies

---

## 3. Out of Scope (Deliberate Simplifications)
- Authentication / multi-user
- Real email sending or calendar integration
- Database (Postgres etc.) — JSON/in-memory only
- CRUD on customers/contacts (read-only + interaction logging only)
- Mobile-specific layouts
