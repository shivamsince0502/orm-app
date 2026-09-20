# Follow-Up Queue — AI-Powered Micro-CRM

A sales-rep micro-CRM for **Practice by Numbers** (dental SaaS) where **the LLM is the sole
prioritization authority**: one batch LLM call ranks all open cases of the current month and
returns tier, reason, suggested action, and a summary per account. No numeric scores. Pinned
accounts are locked to the top. Login is by email OTP; follow-up drafts can be emailed (with
attachments) to contacts.

Detailed docs: [`backend/README.md`](backend/README.md) · [`frontend/README.md`](frontend/README.md) ·
plan/spec: [`IMPLEMENTATION-PLAN.md`](IMPLEMENTATION-PLAN.md), [`ENGINEERING-SPEC.md`](ENGINEERING-SPEC.md).

## Start (full sequence)

Run everything from the repo root (`orm-app/`).

### 0. LLM API key (once)

The LLM runs on **Ollama Cloud** — hosted free models, OpenAI-compatible endpoint,
nothing to install. Create an API key at `https://ollama.com/settings/keys` and paste it into
`LLM_API_KEY=` in `backend/.env`. Model is swappable there too
(`gpt-oss:20b` · `gpt-oss:120b` · `gemma4:31b` · `nemotron-3-*`).

### 1. Database (once)

```bash
docker network create followup-queue-net
docker run -d --name followup-queue-db --network followup-queue-net \
  -e POSTGRES_USER=followup -e POSTGRES_PASSWORD=followup -e POSTGRES_DB=followup \
  -v followup-queue-pgdata:/var/lib/postgresql/data \
  -p 5433:5432 postgres:16-alpine
```

### 2. Backend

Config lives entirely in `backend/.env` — start from the template:
`cp backend/.env.template backend/.env` and fill in the `<placeholder>` values
(DB password, Ollama Cloud API key, sender email + Gmail app password). Then:

```bash
docker build -t followup-queue-backend backend/
docker run -d --name followup-queue-backend --network followup-queue-net -p 8010:8010 \
  --env-file backend/.env -v "$PWD":/app followup-queue-backend
```

It waits for the DB, migrates, seeds demo data (12 accounts), and serves on `:8010`.

After editing `.env`, **recreate** the container (env is read only at creation; `docker restart`
will NOT pick it up):

```bash
docker rm -f followup-queue-backend && docker run -d --name followup-queue-backend \
  --network followup-queue-net -p 8010:8010 --env-file backend/.env \
  -v "$PWD":/app followup-queue-backend
```

### 3. Frontend

```bash
cd frontend && npm install && npm run dev     # http://localhost:5173
```

## Use it

1. Open `:5173` → log in with your email: request the OTP
   (real SMTP is configured; with console email backend the code appears in
   `docker logs followup-queue-backend`) → verify.
2. Inbox shows the LLM-ranked queue (hosted model ≈ 5–10s). Log/pin/keep-open re-rank on next
   load; done/snooze hide with a 6s Undo toast; Draft generates emails with your own
   instructions, then sends them — with attachments — to contacts.

## Tests

```bash
cd backend && source .venv/bin/activate && python -m pytest -q    # 52 tests, mocked LLM
```
