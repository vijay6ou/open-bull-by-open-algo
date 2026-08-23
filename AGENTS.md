# AGENTS.md

## Cursor Cloud specific instructions

OpenBull is a FastAPI (Python 3.12 / `uv`) backend plus a React 19 + Vite
frontend. Source of truth is the repo root (`backend/`, `frontend/`,
`alembic/`), not `openbull-main.zip`.

### Windows VPS is the production host

The owner runs this product on a **Windows VPS**. Do not ask for Jainam /
broker API keys again. Those keys live only in:

- `C:\openbull\.env` on the VPS (written once, never overwritten)
- this agent's gitignored `install/windows/.secrets.env` for the first seed

Future deploys use Cursor environment secrets:

- `WINDOWS_VPS_HOST`
- `WINDOWS_VPS_USER`
- `WINDOWS_VPS_PASSWORD`
- `WINDOWS_VPS_SSH_PORT` (optional)
- `WINDOWS_VPS_PUBLIC_HOST` (optional)

If those secrets are present, deploy with:

```bash
bash install/windows/remote-deploy.sh
```

If they are missing, request them once via environment setup actions and stop.
Do not invent hosts or ask the user to paste passwords into chat.

`Update-OpenBull.ps1` / `remote-deploy.sh` must never replace an existing
`.env` on the VPS.

On the Windows VPS the whole stack is controlled with:

```
openbull start
openbull stop
openbull restart
openbull status
```

### Local Cloud Agent services (Linux)

- PostgreSQL: `sudo pg_ctlcluster 16 main start` when available
- Redis: `sudo service redis-server start` when available
- Backend: `uv run uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload`
- Frontend: `cd frontend && npm run dev`

Copy `.env.example` to `.env` for local work. Do not commit `.env`.

### Lint / test / build

- Frontend lint: `cd frontend && npm run lint` (pre-existing compiler rule noise).
- `npm run build` may fail TypeScript; production Windows scripts fall back to `npx vite build`.
- Prefer `npm run dev` for local UI checks.
