"""Generate docs/API.md from the live FastAPI app (routes, params, auth) so it cannot drift.

cd backend && .venv/bin/python scripts/gen_api_docs.py
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("DB_NAME", "happenmuj")

from fastapi.routing import APIRoute  # noqa: E402

from app.core.deps import current_user, optional_user  # noqa: E402
from app.main import ROUTERS  # noqa: E402

OUT = Path(__file__).resolve().parents[2] / "docs" / "API.md"
TAG_ORDER = ["auth", "users", "clubs", "events", "files", "home", "saved", "community", "analytics", "admin", "meta"]
TAG_TITLES = {
    "auth": "Auth", "users": "Users", "clubs": "Clubs", "events": "Events (catalogue, detail, club-admin management)",
    "files": "Files (GridFS posters)", "home": "Home sections", "saved": "Saved events and calendar",
    "community": "Community (posts, comments, reactions)", "analytics": "Analytics", "admin": "Platform admin",
    "meta": "Meta",
}  # fmt: skip


def walk(dependant):
    for d in dependant.dependencies:
        yield d.call
        yield from walk(d)


def auth_of(route: APIRoute) -> str:
    calls = list(walk(route.dependant))
    roles = next((c.required_roles for c in calls if hasattr(c, "required_roles")), None)
    guard = any(hasattr(c, "club_admin_guard") for c in calls)
    if roles == ("platform_admin",):
        return "platform admin"
    if roles:
        return " / ".join(r.replace("_", " ") for r in roles)
    if guard:
        return "admin of that club (or platform admin)"
    if current_user in calls:
        return "login"
    if optional_user in calls:
        return "optional (extra fields when logged in)"
    return "public"


def params_of(route: APIRoute) -> str:
    out = []
    for p in route.dependant.path_params:
        out.append(f"`{p.name}` (path)")
    for p in route.dependant.query_params:
        out.append(f"`{p.name}`")
    # class-based dependency (PageParams) contributes page / page_size via sub-dependants
    return ", ".join(out)


def collect_query(route: APIRoute) -> list[str]:
    names: list[str] = []

    def rec(dep):
        for q in dep.query_params:
            names.append(q.name)
        for sub in dep.dependencies:
            rec(sub)

    rec(route.dependant)
    return list(dict.fromkeys(names))


def main() -> None:
    routes = [r for router in ROUTERS for r in router.routes if isinstance(r, APIRoute)]
    by_tag: dict[str, list[APIRoute]] = {}
    for r in routes:
        by_tag.setdefault((r.tags or ["misc"])[0], []).append(r)
    lines = [
        "# HappenMUJ API reference",
        "",
        "_Generated from the running FastAPI app by `backend/scripts/gen_api_docs.py`; regenerate it after changing routes. "
        "The interactive version (with request/response examples) is Swagger UI at `/docs`._",
        "",
        f"**{len(routes)} endpoints** under `/api/v1`, plus `GET /health` and `/docs`.",
        "",
        "## Conventions",
        "",
        "| Topic | Rule |",
        "|---|---|",
        "| Auth | `Authorization: Bearer <jwt>` from `POST /auth/login` or `/auth/register`. Roles: `student`, `club_admin`, `platform_admin`. |",
        '| Errors | Always `{"error": {"code": "...", "message": "...", "details": [...]?}}`. Codes seen: `validation_error` (422), `unauthorized` (401), `forbidden` (403), `not_found` (404), `invalid_state` / `conflict` / `email_taken` / `club_exists` / `registration_closed` (409), `file_too_large` (413), `unsupported_media_type` (415). |',
        "| Pagination | `page` (>=1) and `page_size` (1-50, default 20) -> `{items, total, page, page_size}`. |",
        '| Time | All datetimes are UTC ISO-8601 in responses. Requests must carry an offset (`+05:30` or `Z`); naive datetimes are rejected with 422. "Day" logic (tomorrow, next 7 days, calendar months, `date_from`/`date_to`) uses `Asia/Kolkata` boundaries. |',
        "| Public visibility | Only `published`, non-cancelled events appear in public endpoints. Drafts, pending, rejected and cancelled events are visible only to their club's admins and platform admins (detail endpoint). |",
        "| Event card | Every list returns: `id, title, one_liner, club{id,name,slug}, category, event_type, tags, poster_url, schedule{start,end}, venue{name,building}, fee{type,amount,currency,display}, team{type,min,max,display}, registration{required,platform,deadline}, registration_open, featured, stats{saves,views}, is_saved`. `is_saved` is `null` for anonymous callers. The detail adds `description, details, contact, registration.url, status, change_log, ...`. |",
        "| Event `details` | Shape depends on `event_type` (workshop, competition, hackathon, sports_match, cultural_show, seminar, social, other); see the `*Details` schemas in `/docs`. Unknown fields are rejected. |",
        "",
    ]
    for tag in [*TAG_ORDER, *[t for t in by_tag if t not in TAG_ORDER]]:
        if tag not in by_tag:
            continue
        lines += [
            f"## {TAG_TITLES.get(tag, tag.title())}",
            "",
            "| Method | Path | Auth | Query / path params | Summary |",
            "|---|---|---|---|---|",
        ]
        for r in by_tag[tag]:
            for m in sorted(r.methods - {"HEAD", "OPTIONS"}):
                path = r.path
                lines.append(
                    f"| {m} | `{path}` | {auth_of(r)} | {', '.join(f'`{n}`' for n in collect_query(r)) or '-'} | {r.summary or r.name.replace('_', ' ')} |"
                )
        lines.append("")
    OUT.write_text("\n".join(lines) + "\n")
    print(f"wrote {OUT} ({len(routes)} endpoints)")


if __name__ == "__main__":
    main()
