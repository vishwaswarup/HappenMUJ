# HappenMUJ backend (CLAUDE.md)

Campus event discovery for Manipal University Jaipur. **College NoSQL project: the point is to showcase MongoDB**
(flexible schemas, embedding vs referencing, aggregation, text search, TTL/partial/multikey indexes, GridFS,
transactions, `$jsonSchema`). Backend only; **no frontend code** until the API is done. Spec = the build prompt;
where it differs from `docs/PRD*.md`, the prompt wins.

## Stack
Python 3.12, FastAPI, Pydantic v2, `pymongo.AsyncMongoClient` (NOT Motor), MongoDB 7 single-node replica set
(needed for transactions), argon2-cffi, PyJWT, pytest + pytest-asyncio + httpx, ruff. Managed with `uv`.

## Commands (run from `backend/` unless noted)
- Mongo (Docker): `docker compose up -d` (repo root). No Docker: `./scripts/local_mongo.sh` (port 27018).
- Install: `uv sync --python 3.12`
- Run: `.venv/bin/uvicorn app.main:app --reload` -> http://localhost:8000/docs
- Test: `.venv/bin/pytest -q` (real MongoDB, DB `happenmuj_test`, `MONGO_URI` env overrides, default :27018)
- Lint/format: `.venv/bin/ruff check . --fix && .venv/bin/ruff format .`
- Seed (M6): `python -m app.seed --reset`
- Config: `backend/.env` (see `.env.example`). Empty `ALLOWED_EMAIL_DOMAINS` = allow any email (dev).

## Layout
`app/{main,config,db,indexes,validators,seed}.py`, `app/core/{security,deps,errors,timeutil}.py`,
`app/models/` (Pydantic), `app/services/` (all logic + DB access), `app/routers/` (thin), `tests/`.

## Rules that matter every session
- Tests hit a **real MongoDB**; never mongomock (we use `$text`, `$setWindowFields`, transactions).
- Routers thin; logic in `services/`. Full type hints. Every endpoint has a response model + examples.
- Errors: `{"error": {"code", "message"}}` via `AppError` helpers in `core/errors.py`.
- Pagination: `page` + `page_size` (max 50) -> `{items, total, page, page_size}`.
- All routes under `/api/v1`; `/health` and `/docs` at root.
- **Time**: store UTC BSON Dates (client uses `tz_aware=True`); reject naive datetimes; "day" logic uses
  `Asia/Kolkata` boundaries via `core/timeutil.py`; "now" ALWAYS from `timeutil.now()` (freezable in tests).
- **Public visibility**: one shared filter (`status=="published"`, not cancelled) for every public endpoint.
- `registration_open = required AND (deadline null or > now) AND start > now`. Never claim "registered".
- Roles: student / club_admin / platform_admin. Club admins act only on clubs whose `admin_ids` contain them
  AND that are verified. Use `require_role`, `require_club_admin_for`. Test cross-club denial.
- `fee.type == "not_specified"` is the default and is NEVER free.
- Tags/interests normalized to lowercase on write. Every document carries `schema_v: 1`.
- "Completed" events are derived (`end < now`), never stored. Edits append `change_log` with `$slice: -20`.
- Indexes + `$jsonSchema` validators applied at startup (`prepare_database` in `main.py`), idempotent.
- Phase 2 items (notifications, conflict detection, email OTP, payments, reports, etc.) are NOT built; leave
  `# PHASE2:` comments only.
- Ambiguities: choose sensibly, add one line to `docs/DECISIONS_LOG.md`.

## Milestones
M0 scaffold ✅ · M1 auth/clubs ✅ · M2 events+GridFS ✅ · M3 discovery/ranking · M4 saved/calendar/transactions ·
M5 community · M6 seed+analytics · M7 docs. Commit after each; summarize at the end of each.
