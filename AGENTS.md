# AGENTS.md

## Cursor Cloud specific instructions

OpenBull is a single product: a FastAPI (Python 3.12 / `uv`) backend plus a
React 19 + Vite (TypeScript) frontend. The full source lives at the repo root
(`backend/`, `frontend/`, `alembic/`, `migrate_all.py`, ...). It was originally
committed only as `openbull-main.zip`; that archive has been unpacked into the
repo, so treat the checked-in files as the source of truth.

### Services and how to run them

System services are provided by the environment snapshot (not the update
script). systemd is not running in the container, so start them directly:

- PostgreSQL 16: `sudo pg_ctlcluster 16 main start` (DB `openbull`, role
  `postgres` / password `123456`, port 5432).
- Redis 7: `sudo service redis-server start` (port 6379).

App processes (run each in its own tmux session so logs stay inspectable):

- Backend: `uv run uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload`
  — this one process also starts the WebSocket proxy (`:8765`) and the internal
  ZeroMQ bus (`:5555`).
- Frontend: `cd frontend && npm run dev` — Vite dev server on
  `http://127.0.0.1:5173` (binds IPv4 loopback only).

`uv` installs to `~/.local/bin` (added to `~/.bashrc`). Run `migrate_all.py`
(`uv run migrate_all.py`) after dependency updates that touch models; it is
idempotent (create tables + in-place migrations + `alembic upgrade head`).

### Environment / secrets

Copy `.env.example` to `.env` (git-ignored) and set `APP_SECRET_KEY` and
`ENCRYPTION_PEPPER` (each `python -c "import secrets; print(secrets.token_hex(32))"`).
The default `DATABASE_URL` and `REDIS_URL` already match the local Postgres/Redis
above, so no other edits are needed for local dev.

### Lint / test / build

- Lint: `cd frontend && npm run lint`. Runs, but the committed source currently
  has pre-existing lint errors (mostly React Compiler memoization rules) — not an
  environment problem.
- Backend tests are standalone scripts (no pytest suite): e.g.
  `uv run python backend/test/test_redis_cache.py`, and `uv run sandbox_e2e_test.py`
  (the sandbox e2e runner needs an existing user AND broker master-contract data).
- Build: `cd frontend && npm run build` currently FAILS on pre-existing
  TypeScript type errors in the committed source. Development uses `npm run dev`
  (esbuild, no type-check), which works. Prefer dev mode.

### Non-obvious caveats

- After login the app redirects to `/broker/select`; the main dashboard needs a
  configured broker + OAuth. To reach the app UI without a broker, go straight to
  `/sandbox` (Sandbox config page loads with the full app layout and the
  Live↔Sandbox toggle).
- Live market data and real order placement require broker OAuth credentials.
  Sandbox order placement also requires a broker master-contract download
  (symbols are validated against the symtoken table), so orders cannot be placed
  without first configuring a broker. Sandbox mode toggling and config, account
  creation, and API-key management all work without a broker.
- The frontend has no committed lockfile originally; `frontend/package-lock.json`
  is now committed to pin the working dependency set.
