# Data model: embedded vs referenced

A short guide to *why* the MongoDB documents look the way they do. The long version, with all 18
relationships, patterns and trade-offs, is [DESIGN_DECISIONS.md](DESIGN_DECISIONS.md). The query evidence is in
[AGGREGATION_SHOWCASE.md](AGGREGATION_SHOWCASE.md).

**Rule of thumb.** Model for the read path. *Embed* what is read together, is bounded and is never queried alone.
*Reference* what grows without bound, has its own lifecycle or is queried from both sides. *Copy a small snapshot*
of a referenced document where it saves a join on a hot read, and pay for keeping it fresh on the write path.

## Collections at a glance

| Collection | One document is… | Embeds | References |
|---|---|---|---|
| `events` | an event of any type | `schedule`, `venue`, `fee`, `team`, `registration`, `contact`, `details`, `stats`, `featured`, `club_snapshot`, `tags`, a capped `change_log` | `club_id`, `creator_id`, `poster_file_id` (GridFS) |
| `clubs` | a student club | `admin_ids` (array of user ids) | `requested_by`, `verified_by` |
| `users` | a person | `interests`, `preferred_categories`, `followed_club_ids` | n/a |
| `saved_events` | one user saving one event | a denormalised `event_start` | `user_id`, `event_id` |
| `event_interactions` | one view / save / registration click | n/a | `event_id`, `user_id` (nullable) |
| `posts` | a community post | `author_snapshot`, `scope`, counters, `recent_comments` (last 3) | `author_id`, `scope.ref_id` |
| `comments` | one comment or reply | `author_snapshot`, counters | `post_id`, `parent_id`, `author_id` |
| `reactions` | one user's reaction to one post/comment | n/a | `user_id`, `target_id` |
| `settings` | the ranking weights (singleton) | `weights` | n/a |
| `fs.files` / `fs.chunks` | poster images (GridFS) | n/a | n/a |

## The three choices that matter most

**1. The club is embedded in the event card.** An event stores `club_id` (the club exists independently: it is
verified, has admins, followers and many events) *and* `club_snapshot: {name, slug}`. Every event card shows the
club, and cards are the hottest read, so the snapshot removes a `$lookup` from every list. The cost: a club rename
must update the snapshots. `PATCH /clubs/{id}` does it with `update_many` in the same transaction as the club
update. (The API's card shape exposes this as `club: {id, name, slug}`; in the database the id field is `club_id`.)

**2. Comments are referenced, with a small embedded subset.** Comments are unbounded (a popular post could outgrow
the 16 MB document limit and every comment would write to one hot document), so each is its own document, indexed
by `{post_id, created_at}`. The post keeps `comment_count` and the last three comments in `recent_comments` so a
feed card renders without a second query (the *subset* pattern). Threading is capped at two levels, so a thread is
one `$lookup`, never a recursion. Removed comments stay as placeholders and the subset is rebuilt in a transaction.

**3. `details` is a polymorphic sub-document.** Workshops, competitions, hackathons, sports matches, cultural
shows, seminars and social/other events each have different fields, yet all live in the same `events` collection:
no per-type tables, no NULL columns, no migration to add a type. The API treats `details` as a free-form bag whose
keys are defined by the frontend (`eventDetails.ts`): unknown keys are kept, value shapes are tolerant, and a field
that belongs to a *different* type (a workshop carrying `prizes`) is rejected. The `$jsonSchema` validator
deliberately leaves `details` out. The relational equivalent of this one sub-document is 18 tables
([SQL_COMPARISON.md](SQL_COMPARISON.md)).

## Other embed / reference decisions

* **Stats are embedded counters** (`stats.views/saves/registration_clicks`, `comment_count`, `reaction_counts`):
  cheap `$inc` on write, instant reads. The `event_interactions` log stays the source of truth for time-windowed
  ranking. Counter and log change in the same transaction.
* **Saved events are a separate collection**, not an array on the user: unbounded, queried from both sides, needs
  a unique `{user_id, event_id}` constraint and range queries. `event_start` is a deliberate copy of
  `events.schedule.start` so the calendar is an index range scan; a reschedule refreshes it in a transaction.
* **User preferences are embedded arrays** (bounded, always read with the user). **Club admins** are an embedded
  array of references on the club, the single source of truth; the user's `managed_club_ids` in `/auth/me` is
  derived from it.
* **Posters live in GridFS**, referenced by `poster_file_id`.
* **`completed` is derived** (`schedule.end < now`), never stored, so there is no cron job and no stale flag.
* Every document carries `schema_v: 1` so a future migration can find old-shaped documents.

## Indexes

| Collection | Index | Serves |
|---|---|---|
| `events` | `{status, schedule.start}` | the catalogue, every home section, Top 10 (published + upcoming) |
| `events` | `{category, schedule.start}` | category filtering |
| `events` | `{club_id, schedule.start}` | a club's events, club analytics |
| `events` | multikey `{tags}` | tag lookups |
| `events` | partial `{featured.featured_at}` where `featured.is_featured` | the featured event |
| `events` | **text**, weighted: `title` 10, `tags` 6, `club_snapshot.name` 5, `one_liner` 3, `venue.name` 2, `description` 1 | catalogue search (title, tags and club name rank highest) |
| `saved_events` | **unique** `{user_id, event_id}` | idempotent save, even under concurrency |
| `saved_events` | `{user_id, event_start}` | saved list and calendar |
| `event_interactions` | `{event_id, type, ts}`; **TTL** `{ts}` (90 days) | Top-10 windows, funnel; automatic expiry |
| `comments` | `{post_id, created_at}`, `{parent_id}` | threads and replies |
| `posts` | `{scope.type, scope.ref_id, created_at}`; text on title+body | feeds per scope; post search |
| `reactions` | **unique** `{user_id, target_type, target_id}` | one reaction per user per target |
| `users` / `clubs` | unique `email` / `slug`; multikey `admin_ids`, `followed_club_ids` | login, club lookup, authorization, follower counts |

All of these are created idempotently at startup (`backend/app/indexes.py`) next to the `$jsonSchema` validators
(`backend/app/validators.py`).
