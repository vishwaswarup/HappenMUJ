# Viva cheat sheet (one page)

**The story in one line:** the app reads an event or a post *as one unit*, and MongoDB stores exactly that unit.

## Opener (30 seconds)
"HappenMUJ is a campus event platform. Events come in different types with different fields, are read as a unit,
and are queried in many ways, so I used MongoDB. I embedded data that is read together, referenced data that grows
without bound, used aggregation pipelines for ranking, and tested everything against a real database."

## Numbers to know
9 collections + GridFS (11 stores) · 20 secondary indexes · 58 endpoints · 16 clubs, 40 seeded events ·
202 backend tests (real MongoDB) + 74-check end-to-end script · SQL equivalent: **36 tables**, 18 of them just for event `details`.

## The five NoSQL points

| # | Point | Say | Show |
|---|---|---|---|
| 1 | **Flexible schema** | "Workshops, hackathons, seminars have different fields, all in one `events` collection. No NULL columns, no migration to add a type." | README demo, 1:00: the `mongosh` query listing each type's `details` keys. Then try a workshop with `prizes` → rejected. |
| 2 | **Embed vs reference** | "Embed what is read together and bounded (schedule, venue, fee). Reference what grows without bound (comments, saves, interactions)." | `DESIGN_DECISIONS.md` section 1 table (18 relationships). |
| 3 | **Aggregation** | "The Top 10 is one pipeline: `$lookup` the last 7 days of interactions, `$setWindowFields` to normalise, weighted score. The catalogue returns page + total + filter counts in one `$facet`." | `GET /home/top-events` (see `score_breakdown`), `/home/top-events/config` (weights are public). |
| 4 | **Indexes + proof** | "Compound, weighted text, multikey, partial, TTL, unique. I verified use with `explain`." | `AGGREGATION_SHOWCASE.md`: Featured = 1 key examined; Busiest-days = 0 documents read (covered query). |
| 5 | **Transactions, GridFS, validation** | "Saving an event writes 3 collections atomically. Posters live in GridFS. The database itself rejects bad data." | `cd backend && .venv/bin/pytest -k "rolls_back or without_transaction" -v`; in `mongosh`: `db.events.insertOne({title:"bad", status:"bogus"})` → "Document failed validation". |

**Transactions here mean database atomicity, not payments.** Registration is external; the app only records a click.

## Patterns to name
Extended reference (`club_snapshot`) · Subset (`recent_comments`, last 3) · Computed (`stats.*`, `comment_count`) ·
Polymorphic (`details`) · Capped array (`change_log`, last 20) · Schema versioning (`schema_v`) · Append-only log with TTL (90 days).
*Bucket pattern: considered, not used* (each interaction must be queryable alone; the volume is small).

## The rest of the system, one sentence each
API: FastAPI, thin routers, logic in services. · Auth: argon2 password hashes, signed token, 3 roles enforced on the server. ·
Time: stored in UTC, "tomorrow" computed on India-time boundaries. · Frontend: React, same API. · Tests: real MongoDB, because mocks cannot do `$text` or transactions.

## Likely questions
- **Why not SQL?** "SQL can do it. But an event is one unit with a type-specific shape, and documents store that directly: 1 read instead of 8 tables, no migration for a new type." Then give SQL's wins (below). → `SQL_COMPARISON.md`
- **Why is the club name copied into every event?** "To avoid a join on every card. The price: a rename must update all events, so I do it in a transaction."
- **Why aren't comments inside the post?** "Unbounded growth: documents cap at 16 MB. So comments are separate and the post keeps the last 3."
- **Why a replica set?** "Transactions need one. A single plain `mongod` can't do them."
- **Why isn't the Top 10 just most-viewed?** "It counts only the last 7 days, so old popular events can't dominate."
- **Why is "completed" not stored?** "It's derived (`end < now`): no cron job, no stale flag."
- **How do you know an index is used?** "`explain("executionStats")`: keys and documents examined."

## Say these weak spots yourself
- No foreign keys: the app enforces integrity (SQL does it declaratively, 47 FKs).
- Counters can drift if someone edits the database by hand (transactions prevent it from app failures).
- A renamed user keeps their old name on old posts (club renames *are* propagated).
- Authentication has no email verification, rate limiting or password reset yet.
- One index (`category_start`) was required by the brief but the planner doesn't use it.
- `docker-compose.yml` was never run; development used a local `mongod`. The seed has no sports events (no sports club in the list).

## Practice
1. Run the README's **10-minute demo script** aloud once. 2. Read `DESIGN_DECISIONS.md` section 5.
3. Draw one event document and the post → comments link on paper.
