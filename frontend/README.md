# Frontend — Follow-Up Queue

React 18.3 + Vite 6 + TypeScript + Tailwind 4 + react-router 6. No state/query libraries —
plain fetch hooks.

## Start

```bash
cd frontend
npm install     # once
npm run dev     # http://localhost:5173
```

Backend, DB, and the LLM endpoint must be running first — see [root README](../README.md) and
[backend README](../backend/README.md).

## Use it

Log in at `/login` (email → OTP code → 7-day session cookie; dev mode prints the code to the
backend's `docker logs`). The inbox is the LLM-ranked queue; `/accounts/{id}` is the account
360 view. Draft modal can copy or email the generated follow-up.

## Other commands

```bash
npm run build     # typecheck + production build (dist/)
npm run lint      # oxlint
npm run preview   # serve the production build
```

## How it connects

- `vite.config.ts` proxies `/api/*` → `http://localhost:8010`, so the browser only ever talks
  to :5173 (no CORS in dev); the session cookie flows through the proxy.
- `publicDir: "../public"` serves the repo-root `public/assets/` (logo, avatar, practice photo)
  at `/assets/...`.

## Map

```
src/
├── App.tsx (routes + providers) · types.ts · api/client.ts (fetch + 401 → /login)
├── pages/LoginPage.tsx · InboxPage.tsx · AccountPage.tsx
└── components/
    ├── Auth.tsx (session guard + header identity) · Toast.tsx · ErrorBanner.tsx · Skeleton.tsx
    ├── AccountCard.tsx · TierPill.tsx · TimelineItem.tsx
    └── DraftModal.tsx · LogModal.tsx · Modal.tsx
```
