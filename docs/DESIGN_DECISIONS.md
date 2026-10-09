# Design decisions: embed vs reference

How HappenMUJ's data is modelled in MongoDB, why, and what each choice costs. Written for the viva: every
relationship in the system is listed, with the decision and a one-paragraph justification. File and test names
point at where the choice is implemented and verified.

**The rule used throughout.** Model for the *read path*. Embed what is read together, bounded, and not queried
on its own. Reference what grows without bound, is queried from both sides, or has its own lifecycle. Copy a
small, rarely-changing slice of a referenced document (a *snapshot*) when it saves a join on a hot read path,
and pay for it explicitly on the write path.

## 1. Summary table

| # | Relationship | Decision | Cardinality | Implemented in |
|---|---|---|---|---|
| 1 | event → schedule, venue, fee, team, registration, contact, `details` | **Embed** | 1:1 | `models/events.py`, `events` collection |
| 2 | event → tags | **Embed** (array) | 1:few | multikey index `tags_multikey` |
| 3 | event → club | **Reference + embedded snapshot** (`club_id` + `club_snapshot`) | N:1 | `services/events.py`, `services/clubs.py::update_club` |
| 4 | event → creator | **Reference only** | N:1 | `creator_id` |
| 5 | event → poster | **Reference to GridFS** (`poster_file_id`) | 1:0..1 | `services/files.py` |
| 6 | event → stats counters | **Embed** (computed pattern) | 1:1 | `stats.{views,saves,registration_clicks}` |
| 7 | event → change log | **Embed**, capped (`$push` + `$slice: -20`) | 1:≤20 | `services/events.py::update_event` |
| 8 | user → interests, preferred categories, followed clubs | **Embed** (arrays) | 1:few | `users` |
| 9 | club → admin ids | **Embed** (array of refs) | 1:few | `clubs.admin_ids` |
| 10 | club → requester / verifier | **Reference only** | N:1 | `requested_by`, `verified_by` |
| 11 | user ↔ event (saved) | **Separate collection** | M:N, unbounded | `saved_events` |
| 12 | user / event → interactions | **Separate collection** with TTL | 1:many, unbounded | `event_interactions` |
| 13 | post → author | **Reference + embedded snapshot** (`author_snapshot.name`) | N:1 | `services/community.py` |
| 14 | post → comments | **Reference + subset embed** (`recent_comments`, last 3) | 1:many, unbounded | `comments`, `posts.recent_comments` |
| 15 | comment → parent comment | **Reference**, depth capped at 2 | tree (2 levels) | `comments.parent_id` |
| 16 | post / comment → reactions | **Separate collection + denormalised counters** | 1:many, unbounded | `reactions`, `reaction_counts` |
| 17 | post → scope (global / event / club) | **Polymorphic reference** (`scope.type` + `scope.ref_id`) | N:1 (3 targets) | `posts.scope` |
| 18 | ranking weights | **Singleton settings document** | 1 | `settings` (`_id: "ranking"`) |

## 2. The decisions, one paragraph each

### 1. Event → schedule, venue, fee, team, registration, contact, details: embed
These are 1:1 with the event, are read every time the event is read, are never queried on their own, and are
updated atomically with the event (a single-document write is atomic in MongoDB with no transaction). A card or
detail page is therefore one `find`, not a join across venue/fee/registration tables. `details` is the strongest
case: it is a **polymorphic** sub-document whose shape depends on `event_type` (a workshop has a speaker and
prerequisites, a hackathon has tracks and `max_teams`, a sports match has teams, `social`/`other` carry a free-form
`extra`). All eight shapes live in one collection with no NULL columns and no per-type tables. Pydantic validates
`details` with a discriminated union and rejects unknown fields (a workshop carrying competition prizes is a 422);
the `$jsonSchema` validator deliberately leaves `details` open. The seed contains all eight shapes side by side
(`docs/AGGREGATION_SHOWCASE.md`, "Flexible schema"). Measured on the seed: a stored event averages **1,295 bytes**
(max 1,539), nowhere near the 16 MB document limit.

### 2. Event → tags: embed an array
Tags are a handful of short strings, read with the event, and need to be searchable. A multikey index
(`tags_multikey`) gives one index entry per tag, and the weighted text index covers them for search. Tags (and user
interests) are lower-cased on write so matching in `$setIntersection` (Suggested) is a plain equality with no
case folding at query time.

### 3. Event → club: reference plus an embedded snapshot
A club exists independently of its events: it has its own verification workflow, admins, followers and many
events. So events hold `club_id`. But every event card shows the club's name and slug, and cards are the hottest
read in the system. Instead of a `$lookup` on every card, the event stores `club_snapshot: {name, slug}` (the
**extended reference** pattern). *The price:* a club rename must update every event's snapshot.
`services/clubs.py::update_club` does that with `update_many` **in the same transaction** as the club update
(`tests/test_events.py::test_club_rename_updates_event_snapshots`). The slug is deliberately stable on rename so
URLs and the snapshot slug do not churn.

### 4. Event → creator: reference only
`creator_id` is needed only for audit ("who created this"), is never displayed on cards, and so earns no snapshot.

### 5. Event → poster: GridFS
Posters are binary files (up to 5 MB) and belong *beside* the data, not inside the event document (that would
bloat every event read and approach the 16 MB limit for no benefit). GridFS stores them in the same database as
`fs.files` (metadata) and `fs.chunks` (binary, 255 KB chunks), keeping the project self-contained and backed up
with the data. The event stores only `poster_file_id`. Uploads are validated by **magic bytes**, not just the
client's header; a replaced poster is uploaded first and the old one deleted afterwards, so a failed upload never
loses the existing poster. `GET /files/{id}` streams with `ETag` and `immutable` caching, which is safe because a
replacement gets a new id.

### 6. Event → stats counters: embed (computed pattern)
`stats.views/saves/registration_clicks` are cheap `$inc`s on write and make popularity sorting and analytics
roll-ups a simple field read instead of counting rows in `event_interactions`. The interaction log remains the
source of truth for anything *time-windowed* (the Top 10 and the funnel). Counters and log are updated in the same
transaction so they do not drift on a partial failure (see trade-offs).

### 7. Event → change log: embed, capped
An edit appends `{at, by, fields}` with `$push` and `$slice: -20`. History is useful but bounded; capping it keeps
the document from growing without limit and is a one-operator solution (no separate audit collection needed for
this course scope). Older history is intentionally dropped.

### 8. User → interests, preferred categories, followed clubs: embed
All three are bounded lists (interests are capped at 20, categories at 13, follows are a few clubs), always read
with the user (the Suggested pipeline needs all three at once), and not queried independently. The one reverse
query we do need, "how many followers does this club have?", is served by a multikey index on `followed_club_ids`
and only used by club analytics.

### 9. Club → admin ids: embed an array of references
Membership is a handful of users, needed for every authorization check ("is this user an admin of this club?"),
so it lives on the club and is served by a multikey index on `admin_ids`. It is the **single source of truth**: the
user's `role` is derived (a user is promoted to `club_admin` when added and demoted when they no longer administer
any club). No duplicate `club_ids` array on the user.

### 10. Club → requester / verifier: reference only
Audit fields, never rendered in lists.

### 11. User ↔ event (saved): a separate collection
Saves are M:N and unbounded in both directions (a user can save many events; a popular event can be saved by
hundreds), so neither an array on the user nor one on the event is safe. They are queried from both sides (a user's
list; per-event save counts), need a **unique** `{user_id, event_id}` constraint (that index is what makes saving
idempotent under concurrency) and need **range queries** for the calendar. Hence `event_start` is a deliberate
*denormalised copy* of `events.schedule.start`: the calendar and "upcoming saved" are an index range scan on
`{user_id, event_start}` with no `$lookup`. *The price:* when an event is rescheduled, `update_many` refreshes the
copies, in the same transaction as the event update.

### 12. Interactions: a separate append-only collection with a TTL
Views, saves and registration clicks are high-volume and unbounded: they cannot live in a document. A TTL index on
`ts` (90 days) lets MongoDB expire them itself, so no cron job exists in this project. The log feeds the windowed
ranking and the funnel analytics. Repeat views by the same signed-in user within 30 minutes are ignored.

### 13. Post → author: reference plus snapshot
Feeds and comment threads show author names constantly, so `author_snapshot.name` is stored on posts and comments
(and inside `recent_comments`). Unlike club renames, **user renames are not propagated** (see trade-offs): name
changes are rare, and a stale display name on old posts is acceptable for this scope.

### 14. Post → comments: reference with a subset embed
Comments are unbounded (a viral post could exceed the 16 MB limit and would make every comment a write to one
hot document), so they are a separate collection indexed by `{post_id, created_at}`. But a feed wants a preview
without a second query, so the post embeds the **last 3** comment snapshots (the **subset** pattern, maintained
with `$push` + `$slice: -3`) and a `comment_count` counter. Insert + counter + push run in one transaction
(`test_comment_rolls_back_on_midway_failure`). *The price:* removing a comment must rebuild the subset, which
`remove_comment` does in a transaction.

### 15. Comment → parent: reference, depth capped at 2
A thread is a tree, but the product only needs two levels. A reply to a reply attaches to the top-level parent,
so a single `$lookup` level renders any thread and recursion (`$graphLookup` or a recursive CTE) is never needed.
Removed comments stay as tombstones so replies keep their context.

### 16. Reactions: a separate collection plus denormalised counters
A reaction must be unique per user per target (a unique compound index enforces it) and unbounded per post, so it
cannot be an array on the post. The post/comment carries `reaction_counts` so a feed read does not count rows.
The toggle (insert/switch/delete plus the counter change) is one transaction.

### 17. Post → scope: a polymorphic reference
One mechanism, three scopes: `{type: "global"|"event"|"club", ref_id}`. This avoids three parallel collections
(global posts, event discussions, club spaces) with identical shapes. `ref_id` is validated against the right
collection on write. There is no database-level foreign key, which is the usual cost of references in MongoDB
(see trade-offs).

### 18. Ranking weights: a singleton document
The Top 10 weights and window live in `settings` as `{_id: "ranking", weights, window_days}`. They are configurable
without a deploy and exposed (read-only) at `GET /home/top-events/config`, so the ranking is transparent.

## 3. Patterns used

| Pattern | Where | Note |
|---|---|---|
| **Polymorphic** | `events.details` keyed by `event_type`; `posts.scope` | One collection, several shapes |
| **Extended reference** | `club_snapshot`, `author_snapshot` | Avoids `$lookup` on hot reads |
| **Subset** | `posts.recent_comments` (last 3) | Preview without a second query |
| **Computed** | `events.stats.*`, `comment_count`, `reaction_counts` | Cheap read, `$inc` on write |
| **Schema versioning** | `schema_v: 1` on **every** document (all nine collections; asserted in `tests/test_seed.py`) | Lets a future migration find old-shape documents |
| **Capped array** | `change_log` with `$push` + `$slice: -20` | Bound the array instead of letting it grow |
| **Append-only log with TTL** | `event_interactions` | Auto-expiry, no cron job |
| **Partial index** | `featured_partial` | Indexes only the featured events |
| **Schema validation** | `$jsonSchema` on `events`, `users`, `clubs` (`moderate` / `error`) | Common fields only; `details` left open |

**Bucket pattern: considered and not used.** Bucketing groups many small time-ordered records into one document
(typically sensor or metric data) to cut index size and document count. `event_interactions` looks like a
candidate, but each interaction must be individually queryable by `event_id`, `type` and `ts` windows, the TTL
expires one interaction at a time (a bucket would expire as a unit and lose the partial window), and the volume
here (thousands, not millions) gives no index-size problem to solve. The cost of bucketing (harder windowed
counts, harder per-user de-duplication) outweighs the benefit at this scale.

## 4. Trade-offs, stated honestly

* **Denormalisation costs consistency work.** Snapshots and copies can go stale. We propagate the two that
  matter most (club rename → `club_snapshot`, reschedule → `saved_events.event_start`) inside transactions. We do
  **not** propagate user renames into `author_snapshot`, so an old post may show a previous display name. In SQL
  this would be a join and could never be stale; here it is a conscious choice.
* **Counter drift is possible.** `stats.*`, `comment_count` and `reaction_counts` duplicate information held in
  other collections. Transactions prevent drift from partial failures (rollback tests prove it, and a control test
  shows the same writes *without* a transaction do leave counters and logs disagreeing), but they do not protect
  against someone editing the database by hand, and `stats.*` are all-time while the interaction log is
  TTL-limited to 90 days, so after expiry the log no longer reconciles with the counters. The end-to-end seed test
  (`tests/test_seed.py::test_seed_end_to_end`) verifies that every event's counters equal its interaction log and that
  every post's `comment_count` and `reaction_counts` match the underlying documents for freshly generated data.
* **No referential integrity.** There are no foreign keys. Deleting or hiding a parent cannot cascade by itself;
  the application enforces it (events can only be hard-deleted while still drafts and are otherwise cancelled, never
  removed; posts and comments are soft-removed via `status`; scope targets are validated on write). A SQL database would enforce this declaratively.
* **Transactions need a replica set** (hence the single-node replica set in `docker-compose.yml` and
  `scripts/local_mongo.sh`) and carry overhead; we use them only where several documents must change together
  (save/unsave, comment, reaction, club rename, reschedule, view/click).
* **Ad-hoc relational analytics are less natural.** The analytics endpoints are aggregation pipelines written for
  known questions. Arbitrary new cross-collection questions would need new pipelines or `$lookup`s, where SQL
  would just add a join.
* **Validation lives in two places.** Pydantic (rich, per-type rules) and `$jsonSchema` (common fields, a safety
  net against bad writes that bypass the API). That is intentional, but it is two things to keep in step.
* **Subset maintenance.** `recent_comments` makes the feed fast and makes comment removal more complex.
* **Small-data caveat.** With about 40 events the planner's timings are ~1 ms with or without an index; the evidence for
  index use is the keys/docs-examined numbers in `docs/AGGREGATION_SHOWCASE.md`, not wall-clock time. One index
  (`category_start`) is required by the spec but the planner currently prefers `status_start` for the catalogue;
  it is a candidate to drop if write cost mattered.

## 5. Quick answers for the viva

* **Why not one document per user containing their saved events?** Unbounded growth, written from the event side
  too, needs a uniqueness constraint and range queries; see #11.
* **Why embed `recent_comments` but not all comments?** The 16 MB limit and write contention on a hot post; the
  preview is bounded, the thread is not; see #14.
* **Why is `completed` not a field?** It is derived (`schedule.end < now`), so no cron job and no stale flag.
* **Where is the schema flexibility visible?** `events.details`: eight shapes, one collection, no migrations.
* **Where is schema validation visible?** Insert `{title: "bad", status: "bogus"}` into `events` from `mongosh`;
  the server rejects it (code 121) even though the API is bypassed.
* **How do you know a query uses an index?** `docs/AGGREGATION_SHOWCASE.md` has `explain("executionStats")` for
  each main query, captured by a script from the live database.
* **What breaks if the replica set is a single node?** Nothing for this project; it is the *minimum* needed for
  transactions, not a high-availability setup.
