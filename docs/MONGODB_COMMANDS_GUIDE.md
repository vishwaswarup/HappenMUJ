# HappenMUJ: every MongoDB command we use, where, and why

**How this was made.** The lists below come from scanning `backend/app/` for every driver call and every `$operator`
(counts are exact as of 2026-10-20), then checking the interesting ones in `mongosh` against the real database.
Files are under `backend/app/`. Line numbers can drift as code changes; function names are the stable pointer.

**One idea to hold on to.** The code is Python (PyMongo), so you see `find_one_and_update(...)`. In `mongosh` the same
thing is `findOneAndUpdate(...)`. Python `snake_case` = mongosh `camelCase`; the filter/update/pipeline documents
(`{"$set": ...}`) are identical JSON. So learning the commands once covers both.

Connect to your local database: `mongosh --port 27018`, then `use happenmuj`.

---

## 1. Collections (what we store)

`users, clubs, events, saved_events, event_interactions, posts, comments, reactions, settings` + GridFS (`fs.files`,
`fs.chunks`). Why each exists and why things are embedded or referenced: `docs/data-model.md`, `docs/DESIGN_DECISIONS.md`.

## 2. CRUD: the driver calls (counts exclude seed.py and tests)

| Command (mongosh name) | Count | Where used | What it does for us |
|---|---|---|---|
| `find_one` / `findOne` | 30 | `core/deps.py` (load the signed-in user on every request), all `services/*` | Fetch one document by `_id`, email, slug, etc. |
| `find` + `.sort/.skip/.limit` | 15 | `services/clubs.py`, `events.py`, `community.py`, `users.py`, `discovery.py`, `serializers.py` | Lists with pagination (club directory, my events, posts, users). `serializers.py` uses `{"_id": {"$in": [...]}}` to load many referenced docs in one query |
| `insert_one` / `insertOne` | 9 | `users.py` (register/Google), `clubs.py`, `events.py`, `community.py` (post, comment, reaction), `saved.py`, `interactions.py` | Create documents |
| `update_one` / `updateOne` | 14 | `users.py`, `clubs.py`, `community.py`, `interactions.py`, `saved.py`, `settings.py` | Targeted changes, mostly counters (`$inc`) and flags (`$set`) |
| `update_many` / `updateMany` | 2 | `events.py:146` (move `saved_events.event_start` when an event is rescheduled), `clubs.py:117` (update `club_snapshot.name` on every event when a club is renamed) | Keep **embedded copies** in sync |
| `find_one_and_update` / `findOneAndUpdate` | 13 | `events.py` (edit, submit, approve, reject, cancel, feature), `clubs.py` (verify, add/remove admin, edit), `users.py` (profile, follow, role) | Change a document **and get it back in one atomic step**. The filter often includes the expected status (`{"_id":…, "status":"draft"}`), so a wrong-state request simply matches nothing: this is how the event state machine is enforced without race conditions |
| `delete_one` / `deleteOne` | 4 | `events.py:193` (delete a draft only: filter has `status:"draft"`), `saved.py` (unsave), `community.py` (reaction removed) | Remove a document |
| `count_documents` / `countDocuments` | 13 | `analytics.py`, `clubs.py`, `events.py`, `community.py`, `saved.py`, `users.py` | Totals for pagination (`total`) and analytics; `limit=1` is used as an "exists?" check in `community.py:47,49` |
| `estimated_document_count` | 4 | `analytics.py:77-81` | Fast approximate totals from metadata (overview dashboard) |
| `aggregate` | 8 | `discovery.py`, `saved.py`, `community.py`, `analytics.py` | All the "smart" reads: see section 5 |
| `create_indexes` | 1 | `indexes.py:89` | Create all 21 indexes at startup (idempotent) |
| `create_collection` / `command({"collMod":…})` | 2 | `validators.py:130-132` | Create a collection with a `$jsonSchema` validator, or update the validator if it already exists |
| `command("hello")` | 1 | `main.py` `/health` | Is this a replica set? (needed for transactions) |

## 3. Update operators (inside `update_one` etc.)

| Operator | Where | Why |
|---|---|---|
| `$set` | users, clubs, events, interactions | Overwrite fields (profile, status, role, verified, `club_snapshot.name`) |
| `$inc` | `saved.py:44`, `interactions.py:30`, `community.py:270` | Atomic counters: `stats.saves`, `stats.views`, `stats.registration_clicks`, `comment_count`, `reaction_counts.like`. Atomic means two simultaneous users never lose a count |
| `$push` with `$each` + `$slice` | `events.py:143` (`change_log`, keep last 20), `community.py` (`recent_comments`, keep last 3) | A **capped array** inside the parent document |
| `$addToSet` | `users.py` (follow a club; add `google` to `auth_providers`), `clubs.py` (add admin) | Add to an array only if not already there (idempotent) |
| `$pull` | `users.py` (unfollow), `clubs.py` (remove admin) | Remove a value from an array |
| `$setOnInsert` | `users.py:139` (create the platform admin only if missing), `settings.py:16` (default ranking weights) | "Create if missing, never overwrite" with `upsert=True` |
| `upsert=True` (option) | same two places | Update or insert in one command |
| `return_document=AFTER` (option) | `find_one_and_update` calls | Return the updated document, not the old one |

## 4. Query (filter) operators

| Operator | Where | Why |
|---|---|---|
| `$in` / `$nin` | catalogue filters (category OR, club OR), `serializers.py` batch loads, Suggested excludes saved events | Match any / none of a list |
| `$gt $gte $lt $lte` | upcoming events (`start > now`), time windows, 30-minute view de-dup (`interactions.py`), analytics windows | Ranges |
| `$ne` | `clubs.py`, `discovery.py` | Not equal |
| `$or` / `$and` | `discovery.py`, `users.py` | Combine conditions |
| `$type` | `indexes.py` (partial index on `google_sub` string), `discovery.py` | Type check |
| `$regex` + `$options:"i"` | `clubs.py` club-name search (input escaped with `re.escape`) | Case-insensitive substring search |
| `$text` + `$search` | `discovery.py` (events), `community.py` (posts) | Full-text search using the weighted text indexes; ranked by `{$meta: "textScore"}` |
| Dot notation (`"scope.type"`, `"stats.saves"`, `"schedule.start"`) | everywhere | Reach inside embedded documents |
| Array-contains by equality (`{"followed_club_ids": club_id}`) | `analytics.py:262` | Matches if the array contains the value (uses the multikey index) |

## 5. Aggregation: the heart of the NoSQL showcase

Each pipeline is built by a pure function so docs and tests reuse it. Full output examples: `docs/AGGREGATION_SHOWCASE.md`
(note: that file is a bit stale; see dossier finding).

| Pipeline | File / function | Endpoint | Stages and operators (why) |
|---|---|---|---|
| Catalogue + facets | `discovery.py` `catalogue_pipeline` | `GET /events` | `$match` (visibility, `$text`, `$in`), `$addFields` (popularity, `$meta` textScore), **`$facet`** (items, total, and two facet counts in ONE query), `$group`, `$sort`, `$skip`, `$limit` |
| Top 10 | `top_events_pipeline` | `GET /home/top-events` | `$match` eligibility, **`$lookup` with a sub-pipeline** over `event_interactions` (last 7 days), `$map/$filter/$sum`, **`$setWindowFields`** (normalise against the max), `$exp` (decay curves for proximity and urgency), `$multiply/$add` (weighted score), `$sort`, `$limit 10` |
| Suggested | `suggested_pipeline` | `GET /home/suggested` | `$setIntersection` + `$size` (interest overlap), `$cond`, `$nin` |
| Tomorrow / next 7 days | `range_pipeline` | `GET /home/tomorrow`, `/next-7-days` | `$match` on IST-aligned UTC bounds |
| Saved list | `saved.py` | `GET /saved-events` | `$match`, `$sort`, `$lookup` into `events`, `$unwind` |
| Calendar | `saved.py` `calendar_pipeline` | `GET /calendar` | `$dateToString` **with `timezone: Asia/Kolkata`**, `$group` + `$push` |
| Comment thread | `community.py:175` | `GET /posts/{id}/comments` | Two correlated `$lookup` sub-pipelines (reply preview with `$limit`, reply count with `$count`) |
| Analytics (4) | `analytics.py` | `/analytics/*` | `$facet`, two-step `$group`, `$cond`, `$round`, `$isoDayOfWeek`, `$hour` (both with timezone) |

Counts of stage/expression use across the code: `$sum` 23, `$sort` 23, `$match` 22, `$group` 16, `$addFields` 14,
`$limit` 13, `$cond` 9, `$project` 6, `$facet` 5, `$lookup` 5, `$multiply` 5, `$first` 4, `$unwind` 2,
`$setWindowFields` 1, `$setIntersection` 1, `$dateToString` 1 (the scan counts quoted `"$name"` keys).

## 6. Indexes (21 we define; created in `indexes.py`)

| Kind | Indexes | Why |
|---|---|---|
| Unique | `users.email`, `clubs.slug`, `saved_events(user_id,event_id)`, `reactions(user_id,target_type,target_id)` | Prevent duplicates **at the database** (e.g. double-save under concurrency) |
| Unique + **partial** | `users.google_sub` only where it is a string | Many users have `null`; partial lets uniqueness apply only to real values |
| Compound | `events(status,schedule.start)`, `(club_id,schedule.start)`, `(category,schedule.start)`, `saved_events(user_id,event_start)`, `event_interactions(event_id,type,ts)`, `posts(scope.type,scope.ref_id,created_at)`, `comments(post_id,created_at)` | Filter then sort without scanning (ESR rule: equality, sort, range) |
| Multikey (array) | `users.followed_club_ids`, `clubs.admin_ids`, `events.tags` | Index each element of an array |
| **Partial** | `events.featured.featured_at` where `featured.is_featured` | Tiny index covering only featured events |
| **Weighted text** | `events` (title 10, tags 6, club name 5, one-liner 3, venue 2, description 1), `posts` (title, body) | `$text` search with relevance ranking |
| **TTL** | `event_interactions.ts`, `expireAfterSeconds: 7776000` (90 days) | MongoDB deletes old analytics rows by itself |

See them live: `db.events.getIndexes()`. Prove one is used: `db.events.find({status:"published"}).sort({"schedule.start":1}).explain("executionStats")`
and look for `IXSCAN` (not `COLLSCAN`). Captured results: dossier `07_mongodb_dossier.md` section 7.9.

## 7. Schema validation (`validators.py`)

`$jsonSchema` validators on `users`, `clubs`, `events` (`validationLevel: moderate`, `validationAction: error`) so the
**database itself** refuses bad data (wrong status, missing title…) even if someone bypasses the API. `events.details`
is deliberately left out so each event type can have different fields (flexible schema).
Try it: `db.events.insertOne({title:"bad"})` fails with code 121 "Document failed validation".

## 8. Transactions (`db.py` `run_txn` → `session.with_transaction`)

Nine service functions use them, so several collections change together or not at all:
save / unsave an event, add a comment, remove a comment, toggle a reaction, rename a club, reschedule an event,
record a view, record a registration click. Example: saving writes `saved_events` + `$inc events.stats.saves` +
`event_interactions` in one transaction, and tests force a failure in the middle to prove nothing is left half-done.
Requires a replica set (that is why we run `rs0`). Details table: dossier `07` section 7.10.

## 9. GridFS (`services/files.py`)

`upload_from_stream` stores an event poster (split into chunks in `fs.chunks`, metadata in `fs.files`);
`open_download_stream` streams it back with an ETag. Why GridFS: files over 16 MB are possible and it keeps everything in the
one database for the course demo.

## 10. Patterns the commands add up to (say these in the viva)

| Pattern | Example in our data |
|---|---|
| Embedding (one-to-few) | `events.venue`, `fee`, `team`, `schedule`, `stats` live inside the event |
| **Extended reference** (copy a few fields) | `events.club_snapshot {name, slug}` avoids a join on every card; kept in sync by `update_many` on rename |
| **Subset pattern** | `posts.recent_comments` holds only the last 3 comments; the rest live in `comments` |
| Computed counters | `stats.saves/views`, `comment_count`, `reaction_counts` updated with `$inc` instead of counting each time |
| Polymorphic documents | `events.details` has different fields for workshop / competition / hackathon… |
| Capped array | `change_log` keeps the last 20 edits via `$push` + `$slice` |
| Append-only log with TTL | `event_interactions` expires after 90 days |
| Schema versioning | every document has `schema_v: 1` |

---

## 11. Try them yourself: 12 mongosh commands, all tested on 2026-10-20 against the seeded DB

Run `mongosh --port 27018`, then `use happenmuj` and paste one at a time. Say aloud what each shows.

```js
// 1. FIND + SORT + LIMIT: the next 3 published events (what Explore does)
db.events.find({status:"published"}, {title:1, "schedule.start":1}).sort({"schedule.start":1}).limit(3)

// 2. COUNT
db.events.countDocuments({status:"published"})

// 3. TEXT SEARCH ranked by relevance (weighted text index)
db.events.find({$text:{$search:"hackathon"}}, {title:1, score:{$meta:"textScore"}}).sort({score:{$meta:"textScore"}})

// 4. AGGREGATE: events per category
db.events.aggregate([{$match:{status:"published"}},{$group:{_id:"$category",n:{$sum:1}}},{$sort:{n:-1}}])

// 5. $LOOKUP (a join): saved event with its event title
db.saved_events.aggregate([{$limit:1},{$lookup:{from:"events",localField:"event_id",foreignField:"_id",as:"e"}},{$project:{title:{$first:"$e.title"}}}])

// 6. $FACET: total and top categories in ONE query (how filters show counts)
db.events.aggregate([{$match:{status:"published"}},{$facet:{total:[{$count:"n"}],byCat:[{$group:{_id:"$category",n:{$sum:1}}},{$sort:{n:-1}},{$limit:3}]}}])

// 7. $SETWINDOWFIELDS: compare each event's saves with the maximum (Top-10 normalisation)
db.events.aggregate([{$match:{status:"published"}},{$setWindowFields:{output:{maxSaves:{$max:"$stats.saves"}}}},{$project:{title:1,saves:"$stats.saves",maxSaves:1}},{$limit:3}])

// 8. TIMEZONE: events per day in India time, not UTC
db.events.aggregate([{$match:{status:"published"}},{$group:{_id:{$dateToString:{format:"%Y-%m-%d",date:"$schedule.start",timezone:"Asia/Kolkata"}},n:{$sum:1}}},{$sort:{_id:1}},{$limit:3}])

// 9. INDEXES, and proof one is used (look for IXSCAN)
db.events.getIndexes()
db.events.find({status:"published"}).sort({"schedule.start":1}).explain("executionStats")

// 10. VALIDATION: the database rejects bad data (error 121)
db.events.insertOne({title:"bad"})

// 11. SUBSET PATTERN: a post carries only its latest comments
db.posts.findOne({}, {title:1, comment_count:1, recent_comments:1})

// 12. TRANSACTION in a scratch database: abort leaves nothing, commit keeps it
const s = db.getMongo().startSession(); const t = s.getDatabase("scratch").t;
s.startTransaction(); t.insertOne({a:1}); s.abortTransaction();   t.countDocuments({})   // 0
s.startTransaction(); t.insertOne({a:1}); s.commitTransaction();  t.countDocuments({})   // 1
db.getSiblingDB("scratch").dropDatabase(); s.endSession()
```

Command 12 uses a throwaway database named `scratch`; it does not touch your data.

## 12. How to actually learn this (a plan that fits a few evenings)

1. **Run section 11 once**, reading each result. Do not skip 9 and 10.
2. **For each pipeline in section 5, read the function and draw the stages as boxes** (documents flow left to right). Start
   with `range_pipeline` (simplest), then catalogue, then Top 10. `docs/AGGREGATION_SHOWCASE.md` shows real inputs and outputs.
3. **Be able to answer these five questions for any collection**: why embed or reference? which indexes and why? which
   operators update it? is it in a transaction? how does it get validated?
4. **Know the three "why MongoDB" stories**: flexible `details` per event type; snapshot and subset patterns that avoid
   joins; one database doing text search, ranking aggregations, file storage (GridFS) and transactions.
5. **Use `docs/VIVA_CHEATSHEET.md`** for likely questions, and the SQL comparison (`docs/SQL_COMPARISON.md`) for
   "why not PostgreSQL?".

## 13. Honest limits (do not claim these)

- We do **not** use Atlas Search or vector search (our text search is MongoDB's built-in `$text`).
- We do **not** use sharding or a multi-node replica set (one node, replica set only to allow transactions).
- Geo queries, change streams, and `$graphLookup` are **not** used.
- The "bucket pattern" was considered but not implemented.
- Transactions on Atlas's free tier have not been tested by us.
