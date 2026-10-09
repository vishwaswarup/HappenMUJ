# HappenMUJ API reference

_Generated from the running FastAPI app by `backend/scripts/gen_api_docs.py`; regenerate it after changing routes. The interactive version (with request/response examples) is Swagger UI at `/docs`._

**58 endpoints** under `/api/v1`, plus `GET /health` and `/docs`.

## Conventions

| Topic | Rule |
|---|---|
| Auth | `Authorization: Bearer <jwt>` from `POST /auth/login` or `/auth/register`. Roles: `student`, `club_admin`, `platform_admin`. |
| Errors | Always `{"error": {"code": "...", "message": "...", "details": [...]?}}`. Codes seen: `validation_error` (422), `unauthorized` (401), `forbidden` (403), `not_found` (404), `invalid_state` / `conflict` / `email_taken` / `club_exists` / `registration_closed` (409), `file_too_large` (413), `unsupported_media_type` (415). |
| Pagination | `page` (>=1) and `page_size` (1-50, default 20) -> `{items, total, page, page_size}`. |
| Time | All datetimes are UTC ISO-8601 in responses. Requests must carry an offset (`+05:30` or `Z`); naive datetimes are rejected with 422. "Day" logic (tomorrow, next 7 days, calendar months, `date_from`/`date_to`) uses `Asia/Kolkata` boundaries. |
| Public visibility | Only `published`, non-cancelled events appear in public endpoints. Drafts, pending, rejected and cancelled events are visible only to their club's admins and platform admins (detail endpoint). |
| Event card | Every list returns: `id, title, one_liner, club{id,name,slug}, category, event_type, tags, poster_url, schedule{start,end}, venue{name,building}, fee{type,amount,currency,display}, team{type,min,max,display}, registration{required,platform,deadline}, registration_open, featured, stats{saves,views}, is_saved`. `is_saved` is `null` for anonymous callers. The detail adds `description, details, contact, registration.url, status, change_log, ...`. |
| Event `details` | Shape depends on `event_type` (workshop, competition, hackathon, sports_match, cultural_show, seminar, social, other); see the `*Details` schemas in `/docs`. Unknown fields are rejected. |

## Auth

| Method | Path | Auth | Query / path params | Summary |
|---|---|---|---|---|
| POST | `/auth/register` | public | - | Create a student account |
| POST | `/auth/login` | public | - | Log in |
| GET | `/auth/me` | login | - | Current user |

## Users

| Method | Path | Auth | Query / path params | Summary |
|---|---|---|---|---|
| PATCH | `/users/me` | login | - | Update profile and interests |
| POST | `/users/me/follow/{club_id}` | login | - | Follow a verified club |
| DELETE | `/users/me/follow/{club_id}` | login | - | Unfollow a club |

## Clubs

| Method | Path | Auth | Query / path params | Summary |
|---|---|---|---|---|
| GET | `/clubs` | public | `q`, `page`, `page_size` | Verified clubs (powers 'Browse by Club') |
| GET | `/clubs/{id_or_slug}` | optional (extra fields when logged in) | - | One club by id or slug (unverified clubs: requester, its admins, platform admins only) |
| POST | `/clubs` | login | - | Request a new club (starts unverified) |
| PATCH | `/clubs/{club_id}` | admin of that club (or platform admin) | - | Edit a club (rename refreshes event snapshots in a transaction) |

## Events (catalogue, detail, club-admin management)

| Method | Path | Auth | Query / path params | Summary |
|---|---|---|---|---|
| GET | `/events` | optional (extra fields when logged in) | `q`, `category`, `club`, `date_from`, `date_to`, `sort`, `page`, `page_size` | Catalogue: search, filters (OR within a group, AND between groups), sort, facets |
| POST | `/events` | club admin / platform admin | - | Create a draft event (club admin of a verified club) |
| GET | `/events/mine` | club admin / platform admin | `club_id`, `status`, `page`, `page_size` | Events I manage, any status |
| GET | `/events/{event_id}` | optional (extra fields when logged in) | - | Event detail (public if published; its club admins and platform admins see any state) |
| PATCH | `/events/{event_id}` | login | - | Edit an event |
| POST | `/events/{event_id}/submit` | login | - | draft|rejected -> pending_review |
| POST | `/events/{event_id}/cancel` | login | - | published -> cancelled |
| DELETE | `/events/{event_id}` | login | - | Delete a draft |
| POST | `/events/{event_id}/poster` | login | - | Upload/replace the poster (PNG/JPEG/WebP, max 5 MB, stored in GridFS) |
| POST | `/events/{event_id}/view` | optional (extra fields when logged in) | - | Record a view (a user's repeat views within 30 minutes are ignored) |
| POST | `/events/{event_id}/registration-click` | optional (extra fields when logged in) | - | Record a click on Register and return the external URL (we never claim a student registered) |

## Files (GridFS posters)

| Method | Path | Auth | Query / path params | Summary |
|---|---|---|---|---|
| GET | `/files/{file_id}` | public | - | Stream a poster from GridFS (immutable, so cached aggressively) |

## Home sections

| Method | Path | Auth | Query / path params | Summary |
|---|---|---|---|---|
| GET | `/home/featured` | optional (extra fields when logged in) | - | Platform-admin featured event (fallback: soonest with poster) |
| GET | `/home/suggested` | optional (extra fields when logged in) | `limit` | Logged in: rule-based score from interests/categories/clubs. Anonymous: upcoming by popularity |
| GET | `/home/top-events` | optional (extra fields when logged in) | - | Top 10 events to participate in (windowed engagement) |
| GET | `/home/top-events/config` | public | - | The ranking weights, in the open |
| GET | `/home/next-7-days` | optional (extra fields when logged in) | `limit` | [now, 00:00 IST today+7d), chronological |
| GET | `/home/tomorrow` | optional (extra fields when logged in) | `limit` | Tomorrow in IST; an empty list is a valid answer |

## Saved events and calendar

| Method | Path | Auth | Query / path params | Summary |
|---|---|---|---|---|
| POST | `/saved-events` | login | - | Save an event (transaction; idempotent: saving twice returns 200 with the existing record) |
| DELETE | `/saved-events/{event_id}` | login | - | Unsave (idempotent) |
| GET | `/saved-events` | login | `upcoming`, `page`, `page_size` | My saved events |
| GET | `/calendar` | login | `year`, `month` | Saved events in an IST month, grouped by IST date |

## Community (posts, comments, reactions)

| Method | Path | Auth | Query / path params | Summary |
|---|---|---|---|---|
| POST | `/posts` | login | - | Create a post (global, event or club scope) |
| GET | `/posts` | optional (extra fields when logged in) | `scope`, `ref_id`, `q`, `page`, `page_size` | Feed. Public; includes my_reaction when authenticated |
| GET | `/posts/{post_id}` | optional (extra fields when logged in) | - | One post with its last 3 comments (removed posts: platform admins only) |
| DELETE | `/posts/{post_id}` | login | - | Remove my post (soft delete) |
| POST | `/posts/{post_id}/comments` | login | - | Comment or reply (transaction: insert + comment_count + recent_comments). Depth capped at 2 |
| GET | `/posts/{post_id}/comments` | optional (extra fields when logged in) | `replies`, `page`, `page_size` | Top-level comments, each with up to N replies (2-level threading) |
| DELETE | `/comments/{comment_id}` | login | - | Remove my comment (soft delete) |
| PUT | `/reactions` | login | - | Toggle a reaction: same kind removes it, a different kind switches it (counters updated in a transaction) |

## Analytics

| Method | Path | Auth | Query / path params | Summary |
|---|---|---|---|---|
| GET | `/analytics/overview` | platform admin | - | Events per category and status; top clubs by saves |
| GET | `/analytics/engagement` | platform admin | `days`, `limit`, `club_id` | Per-event funnel: views -> saves -> registration clicks |
| GET | `/analytics/busiest-days` | platform admin | - | Published events per IST weekday and hour |
| GET | `/analytics/clubs/{club_id}` | admin of that club (or platform admin) | - | Club stats (platform admins, or the club's own admins) |

## Platform admin

| Method | Path | Auth | Query / path params | Summary |
|---|---|---|---|---|
| GET | `/admin/clubs` | platform admin | `status`, `page`, `page_size` | Clubs by verification status |
| POST | `/admin/clubs/{club_id}/verify` | platform admin | - | Verify a club |
| POST | `/admin/clubs/{club_id}/admins` | platform admin | - | Add a club admin (promotes the user to club_admin) |
| DELETE | `/admin/clubs/{club_id}/admins/{user_id}` | platform admin | - | Remove a club admin (demotes to student if they administer no other club) |
| GET | `/admin/users` | platform admin | `role`, `page`, `page_size` | All users, filterable by role |
| PATCH | `/admin/users/{user_id}/role` | platform admin | - | Change a user's role |
| GET | `/admin/events` | platform admin | `status`, `page`, `page_size` | Events by status (default: review queue) |
| POST | `/admin/events/{event_id}/approve` | platform admin | - | pending_review -> published |
| POST | `/admin/events/{event_id}/reject` | platform admin | - | pending_review -> rejected |
| POST | `/admin/events/{event_id}/feature` | platform admin | - | Feature a published event |
| DELETE | `/admin/events/{event_id}/feature` | platform admin | - | Remove featured flag |
| POST | `/admin/posts/{post_id}/remove` | platform admin | - | Remove any post |
| POST | `/admin/comments/{comment_id}/remove` | platform admin | - | Remove any comment |

## Meta

| Method | Path | Auth | Query / path params | Summary |
|---|---|---|---|---|
| GET | `/meta/categories` | public | - | The 13 categories (and event types) |

