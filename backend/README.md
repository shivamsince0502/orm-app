# Backend — Follow-Up Queue

Django 5.2 + DRF + PostgreSQL 16 (own container) + **Ollama Cloud** hosted models via the
OpenAI-compatible `https://ollama.com/v1` endpoint. API on `:8010`. Start sequence and
frontend live in the [root README](../README.md).

## Start

From the repo root (DB container must exist — step 1 of the root README):

```bash
docker build -t followup-queue-backend backend/
docker run -d --name followup-queue-backend --network followup-queue-net -p 8010:8010 \
  --env-file backend/.env -v "$PWD":/app followup-queue-backend
```

```bash
curl http://localhost:8010/api/health/        # {"ok":true,"llm":true}
```

- **`.env` changed?** recreate (env is read only at container creation; `docker restart` does
  not re-read it):

```bash
docker rm -f followup-queue-backend && docker run -d --name followup-queue-backend \
  --network followup-queue-net -p 8010:8010 --env-file backend/.env \
  -v "$PWD":/app followup-queue-backend
```

- **Dependencies changed?** also re-run the `docker build`.
- Local-venv alternative (never the host-global Django):

```bash
cd backend && source .venv/bin/activate
python manage.py wait_for_db && python manage.py migrate && python manage.py load_demo_data
python manage.py runserver 8010    # connects to localhost:5433 by default
```

## Configuration (`backend/.env`)

Start from the template: `cp backend/.env.template backend/.env`, then fill in the
`<placeholder>` values (DB password, Ollama Cloud API key, sender email + Gmail app password).
The file is the single config source, passed via `docker run --env-file backend/.env`.
Local-venv runs don't read the file — they use the code defaults (`DB_*` →
`localhost:5433`). Keep `.env` out of version control (see `backend/.gitignore`).

| Field | Purpose |
|---|---|
| `DB_NAME` / `DB_USER` / `DB_PASSWORD` | Postgres credentials (`followup`) |
| `DB_HOST` / `DB_PORT` | Postgres peer `followup-queue-db:5432` (host port is 5433) |
| `LLM_BASE_URL` / `LLM_MODEL` | Ollama Cloud `https://ollama.com/v1` + `gpt-oss:20b` (cloud catalog: `gpt-oss:120b`, `gemma4:31b`, `nemotron-3-*` — see `ollama.com/library`) |
| `LLM_API_KEY` | required — create at `https://ollama.com/settings/keys`; sent as `Authorization: Bearer <key>` |
| `LLM_REASONING_EFFORT` *(default `low`)* | gpt-oss is a reasoning model; set empty for models that reject the parameter |
| `DEFAULT_FROM_EMAIL` | sender on every mail |
| `EMAIL_HOST` / `EMAIL_HOST_USER` / `EMAIL_HOST_PASSWORD` | real SMTP delivery (Gmail: 2FA + 16-char App Password, no spaces) |
| `EMAIL_PORT` / `EMAIL_USE_TLS` *(defaults 587 / on)* | only if your provider differs |
| `SESSION_COOKIE_SECURE` *(default 0)* | `1` only behind HTTPS |

The mail backend is derived, not a field: `EMAIL_HOST` set → SMTP, empty → console (mails
print to `docker logs`). Locally keep `SESSION_COOKIE_SECURE=0` — with `1` the login cookie is
HTTPS-only and login breaks on HTTP.

## API

| Route | Notes |
|---|---|
| `POST /api/auth/request-otp/` `{email}` | 6-digit code: 10-min expiry, 60s resend cooldown, 5 attempts max; code is stored hashed |
| `POST /api/auth/verify-otp/` `{email, code}` | sets the `fjq_session` HttpOnly cookie (7 days) |
| `POST /api/auth/logout/` · `GET /api/auth/me/` | |
| `GET /api/accounts/?status=` · `GET /api/accounts/{id}/` | ranked queue + account 360 (need cookie) |
| `POST /api/accounts/{id}/interactions/` · `/actions/` · `/draft/` | log touch / done-snooze-pin-keep-open / AI draft (`{tone?, prompt?}` — `prompt` is the rep's free-text instruction injected into the draft prompt, ≤500 chars) |
| `POST /api/accounts/{id}/send-email/` `{contact_id, subject, body, attachments?}` | emails a draft to that customer's contact; multipart form allows up to 5 attachments, 10MB total (streamed into the mail, never stored) |
| `GET /api/health/` | open (no cookie) |

All `/api/accounts/*` require the session cookie (401 otherwise). LLM endpoint down → 503 + Retry UI.

## Tests

```bash
cd backend && source .venv/bin/activate && python -m pytest -q    # 52 tests, mocked LLM
```

pytest-django creates/destroys `test_followup` in the running DB container
(localhost:5433); retarget with `DB_HOST/DB_PORT/DB_NAME/DB_USER/DB_PASSWORD`.

## Handy commands

```bash
docker logs -f followup-queue-backend                              # API + console-backend mails
docker exec -it followup-queue-db psql -U followup -d followup     # DB shell
python manage.py load_demo_data                                    # re-seed (dates re-anchor to today)
```
