# HappenMUJ

Campus event discovery and community platform for **Manipal University Jaipur**, built as a **NoSQL databases course
project**. The backend is a FastAPI REST API on **MongoDB**, designed to show *why* MongoDB fits: flexible
schemas, embedded documents vs references, aggregation pipelines, text search, TTL / partial / multikey indexes,
GridFS, multi-document transactions and `$jsonSchema` validation.

* **Backend: complete** (58 endpoints, tests against a real MongoDB, demo seed data).
* **Frontend: done and wired to this API**: `happenmuj-frontend/` (Vite + React + TypeScript). See
  [Run the whole stack](#run-the-whole-stack-backend--frontend).

## Contents

1. [Quick start](#quick-start) · [Run the whole stack](#run-the-whole-stack-backend--frontend)
2. [Where each MongoDB feature lives](#where-each-mongodb-feature-lives)
3. [10-minute viva demo script](#10-minute-viva-demo-script)
4. [Documentation map](#documentation-map)
5. [Project layout](#project-layout) · [Configuration](#configuration) · [Tests](#tests) · [Scope and limitations](#scope-and-limitations)

## Quick start

Requirements: Python 3.12, [`uv`](https://docs.astral.sh/uv/), and either Docker or a local `mongod`.

```bash
# 1) MongoDB as a single-node replica set (transactions require a replica set)
docker compose up -d                  # Docker route (see the note below)
# or, without Docker (needs `brew install mongodb-community`; uses port 27018):
./scripts/local_mongo.sh

# 2) Python environment and config
cd backend
uv sync --python 3.12
cp ../.env.example .env               # if you used local_mongo.sh, set MONGO_URI=mongodb://localhost:27018/?replicaSet=rs0

# 3) Demo data, then the API
.venv/bin/python -m app.seed --reset  # ~10 s; WIPES the configured database; prints demo logins
.venv/bin/uvicorn app.main:app --reload    # http://localhost:8000/docs  (Swagger UI); if port 8000 is busy add --port 8001
```

> **Docker note.** `docker-compose.yml` (mongo:7 + a `mongo-init` step that runs `rs.initiate()`) was written
> but **could not be run during development** because the Docker daemon was unavailable. Everything else was
> developed and tested against a local `mongod` replica set started by `scripts/local_mongo.sh`. If compose
> misbehaves, use the script.

`.env` leaves `ALLOWED_EMAIL_DOMAINS` empty in development (any email may register). Set it to
`jaipur.manipal.edu` to restrict sign-ups.

**Demo logins** (created by the seed; password `demo1234` for every seeded user):

| Role | Email |
|---|---|
| Student | `student@muj-demo.edu` |
| Club admin (ACM) | `acm@muj-demo.edu` (every club has one: `<club-slug>@muj-demo.edu`, e.g. `ieee-sb@muj-demo.edu`) |
| Platform admin | `admin@muj-demo.edu` (the `.env` defaults for `PLATFORM_ADMIN_EMAIL` / `PLATFORM_ADMIN_PASSWORD`) |

The seed creates the 16 MUJ clubs (all verified), ~40 events spread over them (today, tomorrow, this week, later,
past, plus cancelled, pending review, draft and rejected ones, and exactly one featured event), a demo student
who has saved an *overlapping* pair of events, and a handful of posts, comments and reactions.

## Run the whole stack (backend + frontend)

Four terminals, or `make` targets (`make help`). Ports: API `8000`, frontend `5173`.

```bash
# 1) MongoDB (single-node replica set)
docker compose up -d                 # or: ./scripts/local_mongo.sh   (no Docker; port 27018, set MONGO_URI to match)

# 2) API + demo data
cd backend && uv sync --python 3.12 && cp ../.env.example .env     # first time only
.venv/bin/python -m app.seed --reset                                # 16 clubs, 40 events, demo logins
.venv/bin/uvicorn app.main:app --reload --port 8000                 # http://localhost:8000/docs

# 3) Frontend (a separate terminal)
cd happenmuj-frontend && npm install                               # first time only
npm run dev                                                         # http://localhost:5173
```

`happenmuj-frontend/.env` must contain `VITE_API_BASE_URL=/api` to use this API (empty = the frontend's built-in
sample data). The Vite dev server proxies `/api` to `VITE_PROXY_TARGET` (default `http://localhost:8000`), so the
browser needs no CORS in development. The backend serves the same routes at `/api` (what the frontend calls) and
`/api/v1` (Swagger UI, tests, docs). If port 8000 is busy, start uvicorn on another port and run the frontend with
`VITE_PROXY_TARGET=http://localhost:8001 npm run dev`. To call the API directly instead of through the proxy, set
`VITE_API_BASE_URL=http://localhost:8000/api` and make sure the backend's `CORS_ORIGINS` includes
`http://localhost:5173` (it does by default).

Make shortcuts: `make mongo`, `make seed`, `make api`, `make web` (override with `API_PORT=8001`), `make test`.

**Verify the wiring** (with the API running on a seeded database):

```bash
python3 scripts/smoke_test.py http://localhost:8000/api         # 74 checks through the same /api paths the frontend uses
python3 scripts/smoke_test.py http://localhost:5173/api         # ...and through the Vite dev proxy
cd happenmuj-frontend && LIVE_API=http://localhost:8000/api npm run test:live   # real React UI (jsdom) against the real API
cd happenmuj-frontend && npm run typecheck && npm test && npm run build         # the frontend's own checks (sample data)
```

Both the smoke test and `test:live` create data (an event, a comment), so run `make seed` again afterwards for a
pristine demo. The "Try a demo account" buttons on the sign-in page appear only in the frontend's sample-data
mode; with the real API, type the demo credentials above.

## Where each MongoDB feature lives

| Feature | Where | Evidence |
|---|---|---|
| Flexible / polymorphic schema | `events.details`: 8 shapes in one collection, validated by a Pydantic discriminated union ([models/events.py](backend/app/models/events.py)) | `tests/test_events.py` (per-type validation), [AGGREGATION_SHOWCASE](docs/AGGREGATION_SHOWCASE.md) "Flexible schema" |
| `$jsonSchema` validation | [validators.py](backend/app/validators.py): `events`, `users`, `clubs` (`moderate` / `error`; `details` left open) | `tests/test_health_and_infra.py`; insert a bad event from `mongosh` and the server rejects it |
| Embed vs reference | [DESIGN_DECISIONS.md](docs/DESIGN_DECISIONS.md): all 18 relationships | n/a |
| Aggregation pipelines | [services/discovery.py](backend/app/services/discovery.py), [analytics.py](backend/app/services/analytics.py), [saved.py](backend/app/services/saved.py): `$facet`, `$lookup` (correlated sub-pipelines), `$setWindowFields`, `$setIntersection`, `$dateToString` | [AGGREGATION_SHOWCASE](docs/AGGREGATION_SHOWCASE.md): 20 pipelines and queries with `explain` output |
| Weighted full-text search | text index on `events` (title 10, tags 6, club 5, one-liner 3, venue 2, description 1) | `tests/test_catalogue.py::test_text_search_ranks_by_field_weights` |
| Multikey / partial / TTL / compound / unique indexes | [indexes.py](backend/app/indexes.py) | `explain` evidence in [AGGREGATION_SHOWCASE](docs/AGGREGATION_SHOWCASE.md) |
| GridFS | poster upload and streaming ([services/files.py](backend/app/services/files.py)) | `tests/test_posters.py` |
| Multi-document transactions | save/unsave, comments, reactions, club rename, reschedule, view/click | forced-failure rollback tests in `tests/test_saved.py` and `tests/test_community.py` |
| Computed / subset / extended-reference patterns | `stats.*`, `comment_count`, `recent_comments`, `club_snapshot` | [DESIGN_DECISIONS.md](docs/DESIGN_DECISIONS.md) section 3 |
| SQL contrast | 36-table relational design, executed on PostgreSQL | [SQL_COMPARISON.md](docs/SQL_COMPARISON.md), [docs/sql/](docs/sql/) |

## 10-minute viva demo script

Prerequisites: MongoDB running, database seeded, API running on `:8000` (if you used another port, change `B` below). Open Swagger UI at
<http://localhost:8000/docs> in one window and a terminal in another. The `curl` snippets use `jq`
(`brew install jq`). Every command below was run against the seed while writing this README.
Adjust `mongosh --port 27018` to your Mongo port (27017 for Docker).

```bash
B=http://localhost:8000/api/v1
login() { curl -s -X POST $B/auth/login -H 'content-type: application/json' \
          -d "{\"email\":\"$1\",\"password\":\"$2\"}" | jq -r .access_token; }
ADMIN=$(login acm@muj-demo.edu demo1234)         # club admin (ACM)
STUDENT=$(login student@muj-demo.edu demo1234)   # student
PLATFORM=$(login admin@muj-demo.edu demo1234)    # platform admin
```

### 0:00 The data model (1 min)
In `mongosh --port 27018 happenmuj`: `show collections`, then
`db.events.findOne()`. Point at the embedded `schedule`, `venue`, `fee`, `registration`, the `club_snapshot`
(extended reference), `stats` (computed pattern), `change_log` (capped array), `schema_v`, and `details`.
Mention: 9 collections + GridFS, 20 secondary indexes ([DESIGN_DECISIONS](docs/DESIGN_DECISIONS.md)).

### 1:00 Flexible schema: one collection, many shapes (2 min)
```js
db.events.aggregate([{$group:{_id:"$event_type", n:{$sum:1},
  detailsKeys:{$first:{$map:{input:{$objectToArray:"$details"},in:"$$this.k"}}}}},{$sort:{_id:1}}])
```
Seven `event_type`s are in the seed (the model supports eight; there is no sports club, so no sports match), each with
different `details` keys, no NULL columns, no per-type tables (the relational equivalent is 18 tables:
[SQL_COMPARISON](docs/SQL_COMPARISON.md) section 2).

Now show the guardrail. Try to create a **workshop that carries competition fields** (`prizes`):
```bash
CID=$(curl -s $B/clubs/acm | jq -r .id)
curl -s -X POST $B/events -H "Authorization: Bearer $ADMIN" -H 'content-type: application/json' -d "{
 \"club_id\":\"$CID\",\"title\":\"Bad\",\"one_liner\":\"x\",\"category\":\"technical\",\"event_type\":\"workshop\",
 \"schedule\":{\"start\":\"2030-01-01T10:00:00+05:30\",\"end\":\"2030-01-01T12:00:00+05:30\"},
 \"venue\":{\"name\":\"AB3\"},\"details\":{\"prizes\":[{\"rank\":1,\"reward\":\"x\"}]}}" | jq -c .error
# -> validation_error: Extra inputs are not permitted
```
And the *database-level* guardrail, bypassing the API entirely:
```js
db.events.insertOne({title:"bad", status:"bogus"})   // -> "Document failed validation" ($jsonSchema, code 121)
```

### 3:00 Roles and the event lifecycle (1.5 min)
Swagger UI: authorize as the ACM club admin (the lock icon, paste the token from `login`), `POST /events` (use the example body, but replace `club_id` with the id from `GET /clubs/acm` and move the dates into the future; it creates a **draft**),
`POST /events/{id}/submit` (-> `pending_review`), then authorize as the platform admin and
`POST /admin/events/{id}/approve` (-> `published`). Show that a draft is invisible publicly
(`GET /events/{id}` without a token -> 404).

Cross-club denial:
```bash
IEEE_EV=$(curl -s "$B/events?club=ieee-sb&page_size=1" | jq -r '.items[0].id')
curl -s -X PATCH $B/events/$IEEE_EV -H "Authorization: Bearer $ADMIN" -H 'content-type: application/json' -d '{"title":"hijack"}' | jq -c .
# -> {"error":{"code":"forbidden","message":"You are not an admin of this club"}}
```

### 4:30 Discovery: filters, facets, weighted search (1.5 min)
```bash
# (technical OR hackathon) AND (acm OR ieee): OR within a group, AND between groups, with facet counts
curl -s "$B/events?category=technical&category=hackathon&club=acm&club=ieee-sb" \
  | jq -c '{total, titles:[.items[].title], categories:[.facets.categories[]|"\(.value)=\(.count)"]}'
curl -s "$B/events?q=generative" | jq -c '[.items[].title]'    # weighted $text search
```
Explain: one `$facet` pipeline returns the page, the total and both facets in a single round trip.

### 6:00 Homepage and the transparent Top 10 (1.5 min)
```bash
curl -s $B/home/top-events | jq '.items[0] | {rank, title, score, score_breakdown}'
curl -s $B/home/top-events/config | jq '{weights, window_days}'   # the weights are in the open
curl -s $B/home/tomorrow | jq '.items | length'                     # IST day boundaries
curl -s $B/home/suggested -H "Authorization: Bearer $STUDENT" | jq '{personalised, first:.items[0].title}'
```
Explain: one aggregation (`$lookup` over the last 7 days of interactions, `$setWindowFields` for
max-normalisation); it is deliberately *not* ranked by all-time views, so old events cannot dominate. "Tomorrow" is
`[00:00 IST, 00:00 IST next day)` converted to UTC.

### 7:30 Transactions (1 min)
```bash
EV=$(curl -s "$B/events?page_size=50" -H "Authorization: Bearer $STUDENT" | jq -r '[.items[]|select(.is_saved==false)][0].id')
SHOW="const id=ObjectId('$EV'); print('stats.saves',db.events.findOne({_id:id}).stats.saves,
 '| saved_events',db.saved_events.countDocuments({event_id:id}),
 '| save interactions',db.event_interactions.countDocuments({event_id:id,type:'save'}))"
mongosh --quiet --port 27018 happenmuj --eval "$SHOW"
curl -s -o /dev/null -w "save: %{http_code}\n" -X POST $B/saved-events -H "Authorization: Bearer $STUDENT" \
  -H 'content-type: application/json' -d "{\"event_id\":\"$EV\"}"        # 201; a repeat returns 200 (idempotent)
mongosh --quiet --port 27018 happenmuj --eval "$SHOW"                    # all three numbers moved together
```
Then prove atomicity: `cd backend && .venv/bin/pytest -k "rolls_back or without_transaction" -v` forces a failure
after two of three writes and asserts **nothing** was written; the control test shows the same writes without a
transaction *do* leave counters and logs disagreeing.

### 8:30 GridFS, TTL and the partial index (0.5 min)
```js
db.fs.files.findOne({}, {filename:1,length:1,chunkSize:1})              // posters live in MongoDB
db.event_interactions.getIndexes().filter(i=>i.expireAfterSeconds)      // TTL: 90 days, no cron job
db.events.getIndexes().filter(i=>i.partialFilterExpression)             // partial: only featured events
```

### 9:00 Proof of index use and the SQL contrast (1 min)
Open [AGGREGATION_SHOWCASE.md](docs/AGGREGATION_SHOWCASE.md): pick entry 3 (Top 10), 8 (Featured: partial index,
1 key examined) or 19 (a *covered* query, 0 documents fetched) and read the `executionStats` table. Close with
[SQL_COMPARISON.md](docs/SQL_COMPARISON.md) section 1: 11 stores vs 36 tables, 1 read vs 8 tables, and the
honest "where relational wins" list.

## Documentation map

| File | What it is |
|---|---|
| [docs/DESIGN_DECISIONS.md](docs/DESIGN_DECISIONS.md) | Embed vs reference for all 18 relationships, patterns used, honest trade-offs, viva Q&A |
| [docs/AGGREGATION_SHOWCASE.md](docs/AGGREGATION_SHOWCASE.md) | 20 pipelines and queries: purpose, exact JSON, `explain("executionStats")`; TTL, validation, GridFS, transactions. **Generated** from the live code and database |
| [docs/SQL_COMPARISON.md](docs/SQL_COMPARISON.md) | The same schema as 36 relational tables; the type-specific `details` problem; Top 10 and comment thread in SQL; where SQL wins |
| [docs/sql/](docs/sql/) | `relational_schema.sql` and `queries.sql` (executed on PostgreSQL 16) |
| [docs/API.md](docs/API.md) | All 58 endpoints with auth requirements and parameters. **Generated** from the app |
| [docs/DECISIONS_LOG.md](docs/DECISIONS_LOG.md) | Every judgment call made while building, one line each |
| [CLAUDE.md](CLAUDE.md) | Conventions and commands for working in this repo |

Regenerate the generated docs after changing routes, pipelines or the seed:
```bash
cd backend
.venv/bin/python scripts/gen_api_docs.py
.venv/bin/python -m app.seed --reset && .venv/bin/python scripts/gen_aggregation_showcase.py
```

## Project layout

```
docker-compose.yml  .env.example  scripts/local_mongo.sh
backend/
  app/
    main.py config.py db.py indexes.py validators.py seed.py
    core/      security.py deps.py errors.py timeutil.py     auth, role guards, error body, IST time helpers + injectable clock
    models/    Pydantic schemas per domain
    services/  business logic and pipeline builders (routers stay thin)
    routers/   auth users clubs events home saved community files admin analytics meta
  scripts/     gen_api_docs.py gen_aggregation_showcase.py
  tests/       real-MongoDB tests (database happenmuj_test, dropped between sessions)
docs/          design docs, generated docs, docs/sql/
happenmuj-frontend/   the React app (Vite + TypeScript); src/lib/api/http.ts is its adapter for this API
frontend/      unused placeholder
Makefile       make help
```

## Configuration

`backend/.env` (template in `.env.example`):

| Variable | Meaning |
|---|---|
| `MONGO_URI`, `DB_NAME` | Connection (must be a replica set) and database name |
| `JWT_SECRET`, `JWT_EXPIRE_MINUTES` | Access-token signing key and lifetime (change the secret outside development) |
| `ALLOWED_EMAIL_DOMAINS` | Comma-separated sign-up allow-list; empty = any email (development) |
| `PLATFORM_ADMIN_EMAIL`, `PLATFORM_ADMIN_PASSWORD` | The platform admin is created at startup if missing (an existing password is never overwritten) |
| `APP_TIMEZONE` | `Asia/Kolkata`: day boundaries for Today/Tomorrow/Next 7 Days/calendar |
| `CORS_ORIGINS` | Comma-separated allowed origins for the future frontend |

## Tests

```bash
cd backend
.venv/bin/pytest -q          # 202 tests, ~45 s (the seed test alone is ~15 s)
.venv/bin/ruff check . && .venv/bin/ruff format --check .
```

Tests run against a **real MongoDB replica set**, never mocks: `$text`, `$setWindowFields` and transactions are
exactly the features being demonstrated and `mongomock` supports none of them. They use a separate
`happenmuj_test` database that is dropped between sessions, and the app clock is frozen where time matters.
Highlights: role and cross-club authorization, per-type validation, lifecycle transitions, public visibility,
`(A OR B) AND (C OR D)` filtering, weighted search ranking, IST boundary cases (23:30 IST, 00:30 IST, exact
midnight, the 18:30 UTC rollover), Top 10 eligibility / no padding / old views not dominating, Suggested scoring,
save idempotency and concurrency, transaction rollbacks, comment-depth cap, reaction toggling, poster validation
(wrong type, too large, spoofed content), moderation, analytics numbers, and a seed end-to-end test.

## Scope and limitations

* The API is also demoable on its own through Swagger UI.
* **Deliberately not built (Phase 2):** notifications and reminders, event-conflict detection, push, content
  reports/flagging, email verification/OTP, real Google Calendar integration, payments, attendance, certificates.
  Extension points are marked `# PHASE2:` in the code.
* **Known trade-offs** (all in [DESIGN_DECISIONS.md](docs/DESIGN_DECISIONS.md) section 4): user renames are not
  propagated to old post/comment author snapshots; counters can drift if the database is edited by hand; there are
  no database-level foreign keys; anonymous views cannot be de-duplicated.
* **Seed content is fictional.** Club descriptions and event copy are placeholders, not real MUJ information.
* `docker-compose.yml` is untested (see the note under Quick start).
* The PRD files (`docs/PRD.md`, `docs/PRD_homepage.md`) were not in the repository; the build followed the written
  build prompt.
