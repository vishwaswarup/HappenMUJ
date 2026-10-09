"""Generate docs/AGGREGATION_SHOWCASE.md from the REAL pipeline builders and a seeded database.

Every pipeline shown is the exact one the API runs (imported, not retyped), and every explain() block
is captured from the server, so the document cannot drift from the code.

    cd backend && .venv/bin/python -m app.seed --reset && .venv/bin/python scripts/gen_aggregation_showcase.py
"""

import asyncio
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bson import json_util  # noqa: E402
from pymongo.errors import WriteError  # noqa: E402

from app import db as db_module  # noqa: E402
from app.services import analytics, community, discovery, saved  # noqa: E402
from app.services.settings import get_ranking_settings  # noqa: E402
from app.validators import VALIDATORS  # noqa: E402

OUT = Path(__file__).resolve().parents[2] / "docs" / "AGGREGATION_SHOWCASE.md"


def j(obj) -> str:
    return json_util.dumps(obj, indent=2)


# ------------------------------------------------------------------ explain helpers
def unwrap(plan: dict) -> dict:
    """Slot-based-execution plans wrap the classic stage tree in `queryPlan`."""
    return unwrap(plan["queryPlan"]) if "queryPlan" in plan else plan


def chain(plan: dict) -> str:
    plan = unwrap(plan)
    name = plan["stage"] + (f"({plan['indexName']})" if plan.get("indexName") else "")
    kids = plan.get("inputStages") or ([plan["inputStage"]] if plan.get("inputStage") else [])
    if plan.get("shards"):
        return name
    if not kids:
        return name
    return name + " > " + (chain(kids[0]) if len(kids) == 1 else "[" + " | ".join(chain(k) for k in kids) + "]")


def indexes_in(plan: dict) -> list[str]:
    plan = unwrap(plan)
    found = [plan["indexName"]] if plan.get("indexName") else []
    for k in plan.get("inputStages") or ([plan["inputStage"]] if plan.get("inputStage") else []):
        found += indexes_in(k)
    return list(dict.fromkeys(found))


def summarize(ex: dict) -> dict:
    node = ex["stages"][0]["$cursor"] if "stages" in ex else ex
    plan = node["queryPlanner"]["winningPlan"]
    es = node["executionStats"]
    return {
        "chain": chain(plan), "indexes": indexes_in(plan), "returned": es["nReturned"],
        "keys": es["totalKeysExamined"], "docs": es["totalDocsExamined"], "ms": es["executionTimeMillis"],
        "rejected": len(node["queryPlanner"].get("rejectedPlans", [])),
    }  # fmt: skip


async def explain_agg(db, coll: str, pipeline: list[dict]) -> dict:
    ex = await db.command(
        {"explain": {"aggregate": coll, "pipeline": pipeline, "cursor": {}}, "verbosity": "executionStats"}
    )
    return summarize(ex)


async def explain_find(db, coll: str, flt: dict, sort: dict | None = None, limit: int | None = None) -> dict:
    cmd: dict = {"find": coll, "filter": flt}
    if sort:
        cmd["sort"] = sort
    if limit:
        cmd["limit"] = limit
    return summarize(await db.command({"explain": cmd, "verbosity": "executionStats"}))


def explain_block(s: dict, note: str = "") -> str:
    verdict = f"**index scan** on `{'`, `'.join(s['indexes'])}`" if s["indexes"] else "**no index (collection scan)**"
    text = (
        f"| Winning plan | `{s['chain']}` |\n|---|---|\n| Index | {verdict} |\n"
        f"| nReturned | {s['returned']} |\n| totalKeysExamined | {s['keys']} |\n"
        f"| totalDocsExamined | {s['docs']} |\n| executionTimeMillis | {s['ms']} |\n| rejected plans | {s['rejected']} |\n"
    )
    return text + (f"\n{note}\n" if note else "")


class Doc:
    def __init__(self) -> None:
        self.parts: list[str] = []
        self.n = 0

    def add(self, text: str) -> None:
        self.parts.append(text)

    async def pipeline(self, db, *, title, coll, endpoint, features, purpose, pipeline, note="", params=""):
        self.n += 1
        s = await explain_agg(db, coll, pipeline)
        self.add(
            f"### {self.n}. {title}\n\n**Endpoint:** {endpoint}  \n**Collection:** `{coll}`  \n"
            f"**MongoDB features:** {features}\n\n**Purpose.** {purpose}\n\n"
            + (f"_Parameters used here:_ {params}\n\n" if params else "")
            + f"<details><summary>Pipeline ({len(pipeline)} stages, exact JSON the API runs)</summary>\n\n```json\n{j(pipeline)}\n```\n\n</details>\n\n"
            + '**`explain("executionStats")`** (the `$cursor` stage = the part served by the query planner/indexes):\n\n'
            + explain_block(s, note)
            + "\n"
        )
        return s

    async def find(self, db, *, title, coll, endpoint, features, purpose, flt, sort=None, limit=None, note=""):
        self.n += 1
        s = await explain_find(db, coll, flt, sort, limit)
        q = (
            f"db.{coll}.find({j(flt)})"
            + (f".sort({json.dumps(sort)})" if sort else "")
            + (f".limit({limit})" if limit else "")
        )
        self.add(
            f"### {self.n}. {title}\n\n**Endpoint:** {endpoint}  \n**Collection:** `{coll}`  \n"
            f"**MongoDB features:** {features}\n\n**Purpose.** {purpose}\n\n```js\n{q}\n```\n\n"
            + '**`explain("executionStats")`:**\n\n'
            + explain_block(s, note)
            + "\n"
        )
        return s


async def main() -> None:
    db = await db_module.init_db()
    try:
        await run(db)
    finally:
        await db_module.close_db()


async def run(db) -> None:
    now = datetime.now(UTC)
    if await db.events.estimated_document_count() < 20:
        raise SystemExit("Seed the database first: python -m app.seed --reset")
    student = await db.users.find_one(
        {"role": "student", "interests": {"$ne": []}, "followed_club_ids": {"$ne": []}}, sort=[("created_at", 1)]
    )
    acm, ieee = await db.clubs.find_one({"slug": "acm"}), await db.clubs.find_one({"slug": "ieee"})
    post = (await (await db.posts.aggregate([{"$sort": {"comment_count": -1}}, {"$limit": 1}])).to_list(1))[0]
    cfg = await get_ranking_settings(db)
    saved_ids = [
        r["event_id"] for r in await db.saved_events.find({"user_id": student["_id"]}, {"event_id": 1}).to_list(None)
    ]
    tz = "Asia/Kolkata"
    counts = {
        c: await db[c].estimated_document_count()
        for c in ("events", "saved_events", "event_interactions", "posts", "comments", "reactions")
    }

    d = Doc()
    d.add(
        "# Aggregation showcase\n\n"
        f"_Generated {now:%Y-%m-%d %H:%M} UTC by `backend/scripts/gen_aggregation_showcase.py` against MongoDB "
        f"{(await db.command('buildInfo'))['version']} with the demo seed "
        + ", ".join(f"{v} {k}" for k, v in counts.items())
        + ".\nEvery pipeline below is imported from the code that serves the API (not retyped), and every `explain` block was captured from the server._\n\n"
        "**How to read the explain tables.** `totalKeysExamined` = index entries read; `totalDocsExamined` = documents fetched; "
        "`nReturned` = documents the query planner hands to the rest of the pipeline. A healthy indexed query reads few keys/docs "
        "relative to the collection size (the numbers above give the sizes). With only a few dozen events the planner's wall-clock "
        "times are ~1 ms either way, so the *keys/docs examined* columns are the meaningful evidence, not milliseconds.\n\n"
        "**Honest caveats.** (1) Stages after the first `$match`/`$sort`/`$limit` (`$lookup`, `$facet`, `$group`, `$setWindowFields`, `$addFields`) "
        "run on the matched documents in memory and are not index-served; the explain shows the index-served prefix. "
        "(2) Where a sort includes `_id` as a deterministic tiebreak, the index provides the filter but MongoDB adds an in-memory `SORT` "
        "limited by `$limit`. (3) A `$lookup` sub-pipeline is explained separately below because the parent explain does not expand it.\n\n"
        "## Index inventory\n\n"
    )
    inv = ["| Collection | Index | Kind | Used by |", "|---|---|---|---|"]
    used_by = {
        "status_start": "catalogue, home ranges, Top 10, Suggested, analytics", "club_start": "club event lists",
        "category_start": "created per spec; the planner currently prefers `status_start` for the catalogue (see entry 1), so treat it as a candidate for dropping if write cost matters", "tags_multikey": "tag lookups (multikey)", "featured_partial": "Featured section",
        "events_text": "catalogue `q=` search", "email_unique": "login, registration", "slug_unique": "club by slug",
        "admin_ids_multikey": "authorization (is this user an admin of the club?)", "followed_clubs_multikey": "club follower counts",
        "user_event_unique": "idempotent save", "user_event_start": "saved list, calendar", "event_type_ts": "Top 10 `$lookup` (entry 4)",
        "ts_ttl": "auto-expiry after 90 days; also the time-window range for the funnel (entry 18)", "scope_created": "community feeds", "posts_text": "post search",
        "post_created": "comment threads", "parent": "reply `$lookup` (foreignField `parent_id`)", "verified": "verified-club list (tiny collection)", "user_target_unique": "one reaction per user per target",
    }  # fmt: skip
    for coll in ("users", "clubs", "events", "saved_events", "event_interactions", "posts", "comments", "reactions"):
        for name, info in (await db[coll].index_information()).items():
            if name == "_id_":
                continue
            kinds = []
            if info.get("unique"):
                kinds.append("unique")
            if "expireAfterSeconds" in info:
                kinds.append(f"TTL {info['expireAfterSeconds'] // 86400}d")
            if "partialFilterExpression" in info:
                kinds.append("partial")
            if any(k == "_fts" for k, _ in info["key"]):
                kinds.append("text, weights " + json.dumps(info["weights"]))
            if "multikey" in name:
                kinds.append("multikey")
            inv.append(
                f"| `{coll}` | `{name}` `{json.dumps(dict(info['key']))}` | {', '.join(kinds) or 'compound/single'} | {used_by.get(name, '')} |"
            )
    d.add("\n".join(inv) + "\n\n## Aggregation pipelines\n\n")

    # ---- discovery
    await d.pipeline(
        db, title="Catalogue: filters + facets in one round trip", coll="events", endpoint="`GET /events?category=technical&category=hackathon&club=acm&club=ieee`",
        features="`$match` (OR within a group via `$in`, AND between groups), `$facet` (items + total + 2 disjunctive facets), `$group`, `$sort`, `$skip/$limit`",
        purpose="Returns one page of event cards, the exact total, and per-category / per-club counts for the current filters, all from a single scan of the public-and-upcoming set. This is what a SQL application would do with 4 queries.",
        pipeline=discovery.catalogue_pipeline(now, q=None, categories=["technical", "hackathon"], club_ids=[acm["_id"], ieee["_id"]], date_from=None, date_to=None, sort="date", skip=0, limit=20),
        note="The base `$match` (`status`, `schedule.end`) is index-served; the `$facet` branches operate on those documents in memory.",
        params="categories technical+hackathon, clubs ACM+IEEE",
    )  # fmt: skip
    await d.pipeline(
        db, title="Weighted full-text search", coll="events", endpoint="`GET /events?q=cloud`",
        features="`$text` with a weighted text index (title 10, tags 6, club name 5, one_liner 3, venue 2, description 1), `$meta: textScore`, `$facet`",
        purpose="Relevance-ranked search: a hit in the title outranks the same hit in the description. `$text` must be the first stage, so visibility filters ride in the same `$match`.",
        pipeline=discovery.catalogue_pipeline(now, q="cloud", categories=[], club_ids=None, date_from=None, date_to=None, sort="relevance", skip=0, limit=20),
        note="`TEXT_MATCH` over the `events_text` index; no collection scan.",
        params='q="cloud"',
    )  # fmt: skip
    await d.pipeline(
        db, title="Top 10 Events to Participate In", coll="events", endpoint="`GET /home/top-events`",
        features="`$lookup` with a correlated sub-pipeline (+ `localField/foreignField`), `$setWindowFields` (max-normalisation across the eligible set), `$map/$filter/$sum`, `$exp`, `$cond`, `$addFields`, `$sort/$limit`",
        purpose=f"One pipeline computes the score from windowed engagement (last {cfg['window_days']} days) + proximity + urgency, using configurable weights from the `settings` collection. Old all-time views cannot dominate because only interactions inside the window are counted. Each result carries its `score_breakdown` for transparency.",
        pipeline=discovery.top_events_pipeline(now, cfg["weights"], cfg["window_days"]),
        note="Index-served prefix: eligible events by `status` + `schedule.start`. The `$lookup` into `event_interactions` is explained in the next entry.",
        params=f"weights {cfg['weights']}, window_days {cfg['window_days']}",
    )  # fmt: skip
    ev = await db.events.find_one({"status": "published", "schedule.start": {"$gt": now}})
    await d.find(
        db,
        title="Top 10 `$lookup` inner query (per event)",
        coll="event_interactions",
        endpoint="`GET /home/top-events` (inside the `$lookup`)",
        features="compound index `{event_id, type, ts}`, range on `ts`",
        purpose="For each eligible event the `$lookup` runs this query. It must not scan the interaction log; the equality on `event_id` uses the compound index prefix.",
        flt={"event_id": ev["_id"], "ts": {"$gte": now - timedelta(days=cfg["window_days"])}},
        note="The windowed counts per event come from the index entries for that `event_id` only.",
    )
    await d.pipeline(
        db, title="Suggested for you (logged in)", coll="events", endpoint="`GET /home/suggested`",
        features="`$setIntersection` + `$size` (interest match), `$in` (category/club match), `$exp`, `$cond`, `$nin` (hide already-saved)",
        purpose="Rule-based personal score `0.35·interest + 0.20·category + 0.20·club + 0.15·date + 0.10·deadline`. Tags and interests are lower-cased on write so comparison is exact and index-friendly.",
        pipeline=discovery.suggested_pipeline(now, student, saved_ids),
        params=f"{student['name']}: interests {student['interests']}, {len(student['followed_club_ids'])} followed clubs, {len(saved_ids)} saved events excluded",
    )  # fmt: skip
    await d.pipeline(
        db,
        title="Popular upcoming (anonymous / no-signal fallback)",
        coll="events",
        endpoint="`GET /home/suggested` (anonymous)",
        features="computed pattern (`stats.*` counters), `$addFields`, `$sort`",
        purpose="Ordering by popularity reads the embedded counters instead of counting interactions, which is why `stats` is embedded (computed pattern).",
        pipeline=discovery.popular_upcoming_pipeline(now, []),
    )
    await d.pipeline(
        db, title="Tomorrow / next 7 days", coll="events", endpoint="`GET /home/tomorrow`, `GET /home/next-7-days`",
        features="range `$match` on IST-aligned UTC bounds, `$addFields` for `registration_open`",
        purpose="Chronological list for an IST day range. Bounds are computed in `core/timeutil.py` (`[00:00 IST, 00:00 IST next day)` converted to UTC).",
        pipeline=discovery.range_pipeline(now, *__import__("app.core.timeutil", fromlist=["x"]).next_7_days_range(now), 50),
        params="next-7-days range",
    )  # fmt: skip
    await d.pipeline(
        db,
        title="Featured event",
        coll="events",
        endpoint="`GET /home/featured`",
        features="**partial index** `featured_partial` (only documents with `featured.is_featured: true`)",
        purpose="The most recently featured upcoming event. The partial index contains only the handful of featured events, so it stays tiny regardless of catalogue size.",
        pipeline=discovery.featured_pipeline(now),
        note="The planner picks the **partial index** on its own: it holds only the featured events, so it examines 1 key no matter how many events exist.",
    )
    await d.find(
        db,
        title="Featured events via the partial index",
        coll="events",
        endpoint="`GET /home/featured`",
        features="partial index `{featured.featured_at: -1}` where `featured.is_featured == true`",
        purpose="Same lookup expressed so the partial index is eligible: the filter implies the index's partial expression.",
        flt={"featured.is_featured": True},
        sort={"featured.featured_at": -1},
        limit=1,
    )
    await d.find(
        db,
        title="Multikey index: events by tag",
        coll="events",
        endpoint="(tag lookups)",
        features="multikey index on the `tags` array",
        purpose="One index entry per array element lets `{tags: 'ai'}` match without scanning documents.",
        flt={"tags": "ai"},
    )
    await d.find(
        db,
        title="Multikey index: is this user a club admin?",
        coll="clubs",
        endpoint="authorization checks, `GET /events/mine`",
        features="multikey index on `admin_ids`",
        purpose="`admin_ids` is the single source of truth for membership; authorization asks 'which clubs list me?'.",
        flt={"admin_ids": student["_id"]},
    )

    # ---- saved/calendar
    await d.pipeline(
        db,
        title="My saved events",
        coll="saved_events",
        endpoint="`GET /saved-events?upcoming=true`",
        features="compound index `{user_id, event_start}` (range + sort without a join), then `$lookup` into `events` by `_id`",
        purpose="`event_start` is a deliberate denormalised copy, so 'my upcoming saved events' is an index range scan; only the page's events are joined afterwards.",
        pipeline=saved.saved_list_pipeline(student["_id"], now, upcoming=True, skip=0, limit=20),
        params=f"user {student['name']}",
    )
    await d.pipeline(
        db,
        title="Calendar month grouped by IST day",
        coll="saved_events",
        endpoint="`GET /calendar?year=2026&month=10`",
        features="`$dateToString` with `timezone: Asia/Kolkata`, `$group` + `$push`, `$lookup`",
        purpose="Range-queries the denormalised `event_start` for an IST month, then groups by IST date inside the database so the day boundary is correct (an event at 00:30 IST belongs to the next IST day even though its UTC date is the previous one).",
        pipeline=saved.calendar_pipeline(student["_id"], now, now.year, now.month),
        params=f"{now.year}-{now.month:02d}",
    )

    # ---- community
    await d.pipeline(
        db,
        title="Comment thread (top-level + reply preview)",
        coll="comments",
        endpoint="`GET /posts/{id}/comments?replies=3`",
        features="two correlated `$lookup` sub-pipelines (reply preview with `$limit`; reply count with `$count`), index `{post_id, created_at}`",
        purpose="Pages top-level comments and attaches up to N replies plus the true reply total in one query. Threading is capped at two levels, so one `$lookup` level suffices (no recursion).",
        pipeline=community.comments_pipeline(post["_id"], 0, 20, 3),
        params=f"post with {post['comment_count']} comments",
    )
    await d.find(
        db,
        title="Community feed",
        coll="posts",
        endpoint="`GET /posts?scope=club&ref_id=…`",
        features="compound index `{scope.type, scope.ref_id, created_at: -1}`",
        purpose="Feed for one scope (global / event / club) newest first.",
        flt={"status": "active", "scope.type": "global"},
        sort={"created_at": -1},
        limit=20,
    )
    await d.find(
        db,
        title="Post search",
        coll="posts",
        endpoint="`GET /posts?q=…`",
        features="text index on `title` + `body`",
        purpose="Full-text search over posts.",
        flt={"status": "active", "$text": {"$search": "campus"}},
    )

    # ---- analytics
    await d.pipeline(
        db,
        title="Analytics overview",
        coll="events",
        endpoint="`GET /analytics/overview`",
        features="`$facet` with three independent `$group` branches, computed-pattern counters (`$sum: $stats.saves`)",
        purpose="Events per category (published), per status (all), and top clubs by saves, in one pass over the collection.",
        pipeline=analytics.overview_pipeline(),
        note="`COLLSCAN` is the *intended* plan here: a whole-collection rollup must read every event, so an index cannot help. "
        "It stays cheap because the counters it sums (`stats.*`) are embedded, so no `event_interactions` scan or `$lookup` is needed.",
    )
    await d.pipeline(
        db,
        title="Engagement funnel (views → saves → registration clicks)",
        coll="event_interactions",
        endpoint="`GET /analytics/engagement?days=30`",
        features="range `$match` on `ts`, two-step `$group` (count per event/type, then pivot to columns with `$cond`), `$lookup`, `$round`, `$facet` (rows + totals)",
        purpose="Per-event funnel with conversion rates; zero denominators yield 0. The interaction log is the source of truth here (counters on events are all-time).",
        pipeline=analytics.engagement_pipeline(now - timedelta(days=30), 20),
        note="The `ts_ttl` index doubles as the range index for the time window. The 30-day window covers the whole 14-day seed, "
        "so every interaction is read here; on a long-lived system the window bounds the work.",
    )
    await d.pipeline(
        db,
        title="Busiest days and hours (IST)",
        coll="events",
        endpoint="`GET /analytics/busiest-days`",
        features="`$isoDayOfWeek` / `$hour` with `timezone`, `$facet` (by weekday, by hour, heatmap)",
        purpose="Counts published events by the IST weekday/hour of their start, computed server-side in the campus timezone.",
        pipeline=analytics.busiest_pipeline(tz),
        note="This is a **covered query**: `status` and `schedule.start` are both in the `status_start` index, so MongoDB answers from the index alone "
        "(`totalDocsExamined` is 0).",
    )
    await d.pipeline(
        db,
        title="Club analytics",
        coll="events",
        endpoint="`GET /analytics/clubs/{club_id}`",
        features="index `{club_id, schedule.start}`, `$facet` (status breakdown, upcoming/past split via `$cond`, engagement totals, top 5)",
        purpose="Everything a club admin needs about their club from a single pass over that club's events.",
        pipeline=analytics.club_pipeline(acm["_id"], now),
        params="ACM",
    )

    # ---- non-aggregation features
    d.add("## Other MongoDB features, demonstrated\n\n")
    ttl = (await db.event_interactions.index_information())["ts_ttl"]
    oldest = await db.event_interactions.find_one({}, sort=[("ts", 1)])
    d.add(
        "### TTL index: interactions expire by themselves\n\n"
        f"`event_interactions` has `{{ts: 1}}` with `expireAfterSeconds: {ttl['expireAfterSeconds']}` ({ttl['expireAfterSeconds'] // 86400} days). "
        "MongoDB's background TTL monitor deletes older documents roughly every 60 seconds; no cron job exists in this project. "
        f"The oldest seeded interaction is {oldest['ts']:%Y-%m-%d} (seeded interactions span 14 days, so none expire yet).\n\n"
        "```js\ndb.event_interactions.getIndexes().filter(i => i.name === 'ts_ttl')\n```\n\n"
        "This is also why the Top 10 uses a *windowed* interaction count while `events.stats.*` holds all-time counters.\n\n"
    )
    ev_validator = (await (await db.list_collections(filter={"name": "events"})).to_list(1))[0]["options"]
    try:
        await db.events.insert_one({"title": "bad", "status": "bogus"})
        rejected = "(unexpectedly accepted)"
    except WriteError as e:
        rejected = f"WriteError code {e.code}: {e.details.get('errmsg')}"
    d.add(
        "### `$jsonSchema` validation (schema where we want it, freedom where we need it)\n\n"
        f"`events`, `users` and `clubs` carry validators with `validationLevel: {ev_validator['validationLevel']}`, "
        f"`validationAction: {ev_validator['validationAction']}`. Only common fields are constrained; `details` is intentionally absent from the schema "
        "because its shape depends on `event_type` (Pydantic checks it).\n\n"
        f"Attempting `db.events.insertOne({{title: 'bad', status: 'bogus'}})` is rejected by the server itself, bypassing the API:\n\n```\n{rejected}\n```\n\n"
        f"<details><summary>Validator on <code>events</code></summary>\n\n```json\n{j(VALIDATORS['events'])}\n```\n\n</details>\n\n"
    )
    shapes: dict[str, list[str]] = {}
    for t in await db.events.distinct("event_type"):
        sample = await db.events.find_one({"event_type": t})
        shapes[t] = sorted(sample["details"])
    d.add(
        "### Flexible schema: one collection, eight `details` shapes\n\n| event_type | keys of `details` in the stored document |\n|---|---|\n"
        + "\n".join(f"| `{t}` | {', '.join(f'`{k}`' for k in ks)} |" for t, ks in sorted(shapes.items()))
        + "\n\nAll eight live in `events` with no NULL columns and no per-type tables.\n\n"
    )
    f = await db["fs.files"].find_one()
    n_chunks = await db["fs.chunks"].count_documents({})
    d.add(
        "### GridFS: posters stored inside MongoDB\n\n"
        f"{await db['fs.files'].count_documents({})} posters → `fs.files` (metadata) + {n_chunks} `fs.chunks` (binary, {f['chunkSize']} bytes each). "
        "`events.poster_file_id` references the file; `GET /files/{id}` streams it with `ETag` + immutable cache headers. "
        "Replacing a poster uploads the new file first and deletes the old one afterwards.\n\n"
        f"```json\n{j({k: f[k] for k in ('_id', 'filename', 'length', 'chunkSize', 'uploadDate', 'metadata')})}\n```\n\n"
        f"Indexes: `fs.files` {sorted(await db['fs.files'].index_information())}, `fs.chunks` {sorted(await db['fs.chunks'].index_information())} "
        "(`files_id, n` lets chunks stream in order).\n\n"
    )
    d.add(
        "### Multi-document transactions\n\n"
        "Used where one logical action touches several documents; each is covered by a forced-failure rollback test:\n\n"
        "| Action | Writes (all-or-nothing) | Rollback test |\n|---|---|---|\n"
        "| Save an event | `saved_events` insert + `events.stats.saves` `$inc` + `event_interactions` insert | `tests/test_saved.py::test_save_rolls_back_on_midway_failure` |\n"
        "| Unsave | `saved_events` delete + `$inc -1` + retract the save interaction | `test_unsave_rolls_back_on_midway_failure` |\n"
        "| Comment | `comments` insert + `posts.comment_count` `$inc` + `$push` to `recent_comments` with `$slice: -3` | `tests/test_community.py::test_comment_rolls_back_on_midway_failure` |\n"
        "| React (toggle) | `reactions` insert/update/delete + counter `$inc`s | `test_reaction_rolls_back_on_failure` |\n"
        "| Rename a club | `clubs` update + `events.club_snapshot.name` `update_many` | `tests/test_events.py::test_club_rename_updates_event_snapshots` |\n"
        "| Edit an event's schedule | `events` update + `saved_events.event_start` `update_many` | `test_schedule_edit_updates_denormalized_saved_events` |\n\n"
        "A control test (`test_without_transaction_the_failure_would_leave_partial_state`) shows the same writes without a transaction leave counters and logs disagreeing. "
        "Transactions need a replica set, which is why `docker-compose.yml` runs a single-node replica set.\n"
    )
    OUT.write_text("".join(d.parts))
    print(f"wrote {OUT} ({d.n} numbered entries)")


if __name__ == "__main__":
    asyncio.run(main())
