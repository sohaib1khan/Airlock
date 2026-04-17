# Airlock (Project Airlock)

Self-hosted secure container workspace platform inspired by Kasm Workspaces.

## Highlights

- FastAPI backend + React/Vite frontend.
- Session lifecycle management for workspace containers on the local Docker daemon.
- Admin UI for users, settings, audit logs, and container template management.
- 2FA support (TOTP, WebAuthn, backup codes, optional YubiKey OTP).
- PWA support for static assets.

## Database migrations

- **Docker:** the backend image runs `alembic upgrade head` before starting Uvicorn.
- **Local:** from `backend/` with a venv and `DATABASE_URL` set (or `.env` present):
  - `alembic upgrade head`
- **From repo root:** `python scripts/init_db.py` (runs Alembic in `backend/`).

## Quick Start

### From this repo (build images locally)

Use this mode when building backend and frontend images from source.

1. **Prerequisites:** Docker Engine + Docker Compose v2, and a Linux host (or Docker Desktop) with **`/var/run/docker.sock`** available. Airlock starts **workspace containers** on the same daemon via that socket.
2. **Environment:**
   - `cp .env.example .env`
   - Set strong random values for **`JWT_SECRET`** and **`SESSION_SECRET`** (see comments in `.env.example`).
   - For local dev, keep `FRONTEND_URL`, `WEBAUTHN_ORIGIN`, and `ALLOWED_ORIGINS` aligned with the URL you use (default UI port **32770**).
3. **Data directory:** `./data` is mounted for SQLite and audit logs (created on first run).
4. **Start:**
   ```bash
   docker compose up --build -d
   ```
5. **Optional — Bastion desktop template image** (not on Docker Hub; build once on this host):
   ```bash
   docker compose build bastion-desktop
   ```
6. **Open:**
   - UI: `http://localhost:32770` (or `http://<host>:32770`)
   - API docs: `http://localhost:8000/docs`

### Like a “Docker Hub app” (pre-built images)

When using pre-built images, operators only need:

1. Clone or copy **`docker-compose.hub.yml`**, **`.env.example`**, and (optionally) the **`Bastion_templates/`** folder if you want live edits to built-in YAML templates.
2. `cp .env.example .env` and set secrets + URLs as above.
3. In `.env`, set:
   - `AIRLOCK_BACKEND_IMAGE=your-registry/airlock-backend:tag`
   - `AIRLOCK_FRONTEND_IMAGE=your-registry/airlock-frontend:tag`
4. Run:
   ```bash
   docker compose -f docker-compose.hub.yml pull
   docker compose -f docker-compose.hub.yml up -d
   ```

The backend image should run **`alembic upgrade head`** before starting Uvicorn. The hub compose file still bind-mounts **`./data`**, **`docker.sock`**, and **`./Bastion_templates`**.

## First Launch Guide

1. Open `http://localhost:32770` and complete setup at `/setup`.
2. Create the first admin account (strong password required).
3. Sign in at `/login`.
4. Enroll 2FA in `/mfa/enroll` (recommended before any production use).
5. Open `/admin/settings` to access:
   - User management (`/admin/users`)
   - Audit logs (`/admin/audit-logs`)
   - Container template management (`/admin/containers`)
6. Create at least one container template, then launch from dashboard.

## PWA + Security Notes

- PWA manifest + service worker are enabled via `vite-plugin-pwa`.
- Service worker is static-asset oriented; API routes are not used as SPA fallback/cache targets.
- Reverse-proxy security header reference is provided at `deploy/nginx/airlock.conf`.
- See `SECURITY.md` for threat model and vulnerability reporting guidance.

## Notes

- Never commit `.env`.
- Secrets should come from environment variables only.
