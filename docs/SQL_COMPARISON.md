# SQL comparison: the same data as relational tables vs MongoDB documents

This compares two designs of the **same** application data: the MongoDB design this project uses, and a
strict third-normal-form PostgreSQL design (no arrays, no JSON columns). The relational design is a real file,
[`sql/relational_schema.sql`](sql/relational_schema.sql); the queries are in [`sql/queries.sql`](sql/queries.sql).
Both were **executed on PostgreSQL 16** with sample data to confirm they work (the Top-10 score was also checked
by hand: `0.30·1 + 0.20·1 + 0.20·0 + 0.20·e^(−3.146/7) + 0.10·0.5 = 0.6776`, which is what the query returned).

> **Read this fairly.** A strict 3NF design is the *worst case* for the relational side, chosen to show what the
> document model absorbs. PostgreSQL's `jsonb` and array columns would shrink it a lot (see [section 7](#7-the-fair-middle-postgresql-with-jsonb-and-arrays)).
> Section 6 lists where relational is simply better.

## 1. By the numbers

| | MongoDB (this project) | Relational, strict 3NF |
|---|---|---|
| Stores for the same data | **11** (9 collections + GridFS `fs.files`, `fs.chunks`) | **36 tables** |
| Tables/collections for per-type event `details` | **0** extra (one embedded sub-document) | **18** |
| Tables/collections touched to render one workshop's detail page | **1** (a single `findOne`) | **8** (events, clubs, workshop_details, event_tags, workshop_topics, workshop_prerequisites, event_change_log, event_change_log_fields) |
| Foreign keys enforced by the database | **0** (application-enforced) | **47** |
| Secondary indexes (hand-made) | 20 (incl. 2 text, 1 partial, 1 TTL, 3 multikey) | 12 mirrors in the file + the implicit PK/UNIQUE ones |
| Declarative rules in the database | `$jsonSchema` on common fields only | `CHECK`s for enums, fee/team rules, URL scheme, `end > start`, scope target |
| Adding a 9th event type | add one Pydantic class; no migration | 1-4 new tables + migration + a new `LEFT JOIN` in every read path that lists events |
| Auto-expiring interactions | `expireAfterSeconds` on an index | none built in: needs `pg_cron` or an external job |
| Poster binaries | GridFS, same database and backup | `bytea` table (or an external object store) |
| Top-10 ranking | 12-stage pipeline, ~85 lines of Python to build it | 1 statement, 5 CTEs, 42 lines of SQL |

## 2. The per-type `details` problem (the central argument)

An event is a workshop, competition, hackathon, sports match, cultural show, seminar, social or other, and each
type has different fields. The table shows how many relational tables each needs once lists become child tables:

| event_type | Header table | Child tables (lists) | Tables |
|---|---|---|---|
| workshop | `workshop_details` | `workshop_topics`, `workshop_prerequisites` | 3 |
| competition | `competition_details` | `competition_prizes`, `competition_rounds`, `competition_judging_criteria` | 4 |
| hackathon | `hackathon_details` | `hackathon_themes`, `hackathon_tracks`, `hackathon_prizes` | 4 |
| sports_match | `sports_details` | `sports_teams` | 2 |
| cultural_show | `cultural_details` | `cultural_performances`, `cultural_artists` | 3 |
| seminar | `seminar_details` | (none) | 1 |
| social / other | (none) | `event_extra` (key/value) | 1 |
| | | **Total** | **18** |

For comparison, the MongoDB document for a workshop (the same data, one `findOne`):

```json
{
  "title": "Intro to Generative AI", "club_snapshot": {"name": "ACM", "slug": "acm"},
  "event_type": "workshop", "tags": ["ai", "genai"],
  "schedule": {"start": "...", "end": "..."}, "fee": {"type": "fixed", "amount": 199},
  "registration": {"required": true, "platform": "google_forms", "url": "https://..."},
  "details": {
    "speaker": {"name": "Dr. Rao", "bio": "..."}, "topics": ["LLMs", "RAG"],
    "duration_minutes": 120, "prerequisites": ["Python"], "bring_own_laptop": true
  },
  "change_log": [{"at": "...", "by": "...", "fields": ["venue", "title"]}]
}
```

Other relational options each have a price. **Single-table inheritance** (one wide `events` table with every
type's columns, mostly NULL) needs 16 nullable columns for the scalar fields alone and still cannot hold the repeating lists. **Table-per-type** is the
18-table design above. **Entity-attribute-value** (used above for the free-form `social`/`other` dict) turns every
value into untyped text and loses constraints. A **JSON column** works, but that is conceding the document model
inside the relational database (section 7).

## 3. Reading one event

MongoDB: `db.events.findOne({_id})`. The `club_snapshot` is already inside, so no join is needed for the card.

PostgreSQL (query Q1, [`sql/queries.sql`](sql/queries.sql)):

```sql
SELECT e.id, e.title, ..., c.name AS club_name, c.slug AS club_slug,
       w.speaker_name, w.speaker_bio, w.duration_minutes, w.bring_own_laptop,
       ARRAY(SELECT tag   FROM event_tags t             WHERE t.event_id = e.id)                   AS tags,
       ARRAY(SELECT topic FROM workshop_topics x        WHERE x.event_id = e.id ORDER BY position) AS topics,
       ARRAY(SELECT item  FROM workshop_prerequisites x WHERE x.event_id = e.id ORDER BY position) AS prerequisites,
       ARRAY(SELECT l.at || ' ' || string_agg(f.field, ',') FROM event_change_log l
             JOIN event_change_log_fields f ON f.change_id = l.id
             WHERE l.event_id = e.id GROUP BY l.id, l.at ORDER BY l.at DESC LIMIT 20)              AS change_log
FROM events e
JOIN clubs c                 ON c.id = e.club_id
LEFT JOIN workshop_details w ON w.event_id = e.id
WHERE e.id = :event_id;
```

It works and touches 8 tables. But two things are worse than they look:

1. **The query is type-specific.** The application must already know the event is a workshop to choose
   `workshop_details`. In practice that means a first query to read `event_type`, then a second, type-specific one
   (or a generic version that `LEFT JOIN`s all 6 header tables and aggregates all 12 child tables).
2. **Lists of mixed types are painful.** The catalogue returns workshops, hackathons and sports matches together.
   The card shape here avoids `details`, which is exactly why the MongoDB cards don't need them either; but any
   screen that shows details for a mixed list pays for the 18-table fan-out.

## 4. Top 10 events: pipeline vs SQL

Both compute the same score: windowed engagement normalised by the maximum across eligible events, plus
proximity and urgency, with weights read from configuration (a `settings` document / a `ranking_settings` row).
The SQL (Q2) is:

```sql
WITH cfg AS (SELECT * FROM ranking_settings WHERE id = 1),
eligible AS (SELECT e.* FROM events e WHERE e.status = 'published' AND e.cancelled_at IS NULL
               AND e.start_at > :now AND (NOT e.reg_required OR e.reg_deadline IS NULL OR e.reg_deadline > :now)),
windowed AS (SELECT i.event_id,
                    count(*) FILTER (WHERE i.type = 'save') AS saves,
                    count(*) FILTER (WHERE i.type = 'view') AS views,
                    count(*) FILTER (WHERE i.type = 'registration_click') AS clicks
             FROM event_interactions i JOIN eligible e ON e.id = i.event_id CROSS JOIN cfg
             WHERE i.ts >= :now - make_interval(days => cfg.window_days) GROUP BY i.event_id),
raw AS (SELECT e.*, coalesce(w.saves,0) AS saves, ...,
               max(coalesce(w.saves,0)) OVER () AS max_saves, ...   -- max-normalisation
        FROM eligible e LEFT JOIN windowed w ON w.event_id = e.id),
scored AS (SELECT r.*, CASE WHEN max_saves > 0 THEN saves::float / max_saves ELSE 0 END AS saves_n, ...,
                  exp(-extract(epoch FROM (start_at - :now)) / 86400 / 7) AS proximity,
                  CASE WHEN reg_required AND reg_deadline <= :now + interval '72 hours' THEN 1.0
                       WHEN reg_required THEN 0.5 ELSE 0 END AS urgency FROM raw r)
SELECT ... FROM scored CROSS JOIN cfg ORDER BY score DESC, start_at, id LIMIT 10;
```

The MongoDB version is a 12-stage pipeline: `$match` → `$lookup` (sub-pipeline over the last N days) → `$addFields`
→ `$setWindowFields` (max-normalisation) → `$addFields` ×3 (components, contributions, score) → `$sort` → `$limit` →
`$addFields` + `$project` (card shape) → `$project` (drop working fields). The exact JSON is in
[`AGGREGATION_SHOWCASE.md`](AGGREGATION_SHOWCASE.md) (entry 3).

**Honest assessment: SQL wins on readability here.** `count(*) FILTER (...)` and `max(...) OVER ()` are more
direct than `$map`/`$filter`/`$sum` and `$setWindowFields`, and the query is shorter (42 lines of SQL vs ~85 lines of
Python building the pipeline). Neither is faster to run at this size. What the MongoDB version offers is not
brevity but that the whole thing runs next to the data in one round trip *and* returns documents already shaped
as event cards (with the embedded club snapshot, `fee`/`team` objects), where the SQL result still has to be
joined to clubs and reshaped.

## 5. Comment threads and counters

**Thread (Q3).** SQL uses an adjacency list and `LEFT JOIN LATERAL`:

```sql
SELECT c.id, c.body, count_r.n AS reply_count, r.id AS reply_id, r.body AS reply_body
FROM comments c
LEFT JOIN LATERAL (SELECT * FROM comments r WHERE r.parent_id = c.id ORDER BY r.created_at LIMIT 3) r ON true
LEFT JOIN LATERAL (SELECT count(*) AS n FROM comments r WHERE r.parent_id = c.id AND r.status = 'active') count_r ON true
WHERE c.post_id = :post_id AND c.parent_id IS NULL
ORDER BY c.created_at, r.created_at LIMIT 20;
```

The result has **one row per reply**, so the application regroups rows into a nested structure; MongoDB's
`$lookup` returns the nested documents directly. Limiting the threading depth to two levels is a one-line rule in
the service layer in MongoDB; in SQL a `CHECK` cannot inspect another row, so it needs a trigger.

**Feed preview and counters.** To show "the last 3 comments" and counts in a feed, SQL either runs a lateral
subquery per post (and counts rows on every read) or *denormalises*, keeping `comment_count` and a copy of
recent comments in `posts`, maintained by triggers. That is the same denormalisation problem the MongoDB
design solves with the subset and computed patterns; the difference is that relational databases make you opt
into it, while in MongoDB it is the idiomatic first move.

## 6. Where relational is better (and MongoDB pays)

* **Referential integrity.** 47 foreign keys are enforced by the database. In MongoDB nothing stops an event
  pointing at a missing club except application code (and we validate on write, but a direct database edit could
  still break it).
* **Declarative constraints.** The fee and team rules are `CHECK` constraints in SQL, enforced for every writer.
  In MongoDB they live in the Pydantic models, so a client that bypasses the API bypasses them. (`$jsonSchema`
  could express some of them; this project deliberately limits it to common fields.)
* **No stale copies by construction.** A club rename is one `UPDATE`; every join sees it. In MongoDB the snapshot
  must be refreshed in a transaction (`update_club`), and user-name snapshots on posts are *not* refreshed at all.
* **Transactions everywhere, by default.** MongoDB needs a replica set and uses transactions only where needed.
* **Ad-hoc analytics.** A new cross-table question is just a new join. In MongoDB it is a new pipeline written
  against a model shaped for the existing screens.
* **Mature tooling for reporting** (BI tools, SQL knowledge in the team).

## 7. The fair middle: PostgreSQL with `jsonb` and arrays

Using `text[]` for tags/interests/admin ids and a `details jsonb` column on `events` (with a `CHECK` or a
JSON-schema extension for per-type validation) would collapse the 18 detail tables and 7 list tables (user_interests, user_preferred_categories, user_followed_clubs,
club_admins, event_tags, post_tags, event_change_log_fields) into
columns, taking the relational design from **36 tables to 11** (users, clubs, event_posters, events, event_change_log, saved_events, event_interactions, posts, comments, reactions, ranking_settings), and `GIN` indexes make the arrays and
`jsonb` searchable. At that point the two designs converge: the *document-shaped data* is stored the same way, and
what remains different is operational:

| Concern | MongoDB | PostgreSQL + jsonb |
|---|---|---|
| Polymorphic `details` | native, indexable, validated by union in the app | `jsonb` + GIN, validation in app or extension |
| TTL expiry | built in | job required |
| Binary files | GridFS in the same database | `bytea` / large objects / external store |
| Weighted full-text | `$text` with field weights | `tsvector` with `setweight` |
| `$facet` multi-result aggregation | one stage | several queries or a CTE |
| Integrity and constraints | app-enforced | database-enforced |
| Horizontal scaling | sharding built in | extensions / read replicas |

**Conclusion for this project.** The decisive argument is not "SQL can't do it". It is that this application
reads an event, a post, or a user *as a unit*, with a polymorphic shape per event type, and the document model
stores exactly that unit: 1 read instead of 8 tables, no migration to add an event type, TTL and GridFS and
text search and `$facet` built in. In exchange we accept application-enforced integrity, explicit consistency
work for denormalised copies, and a replica set for transactions (all listed in
[`DESIGN_DECISIONS.md`](DESIGN_DECISIONS.md), section 4).

## 8. Reproduce

```bash
# any PostgreSQL 14+; the scripts are plain SQL
createdb hm_compare
psql -d hm_compare -f docs/sql/relational_schema.sql          # creates the 36 tables
psql -d hm_compare -tc "SELECT count(*) FROM information_schema.tables WHERE table_schema='public'"   # 36
psql -d hm_compare -v now="'2026-10-09T06:30:00Z'" -v event_id=1 -v post_id=1 -f docs/sql/queries.sql   # after inserting sample rows
```
