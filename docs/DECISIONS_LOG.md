# Decisions log

- `docs/PRD.md` / `docs/PRD_homepage.md` were not present in the repo at M0; built from the build prompt alone.
- Python deps managed with `uv`; Docker daemon was unavailable on the dev machine, so a Docker-free `scripts/local_mongo.sh` (port 27018) is provided alongside `docker-compose.yml`; tests default to `:27018`.
- `LoginIn.email` is a plain string (not `EmailStr`) so a platform admin configured with any env email can log in; `RegisterIn` validates the format.
- JWT expiry uses the real clock, not the injectable one (PyJWT validates `exp` against real time).
- Club slug collisions return 409 `club_exists` (slug derives from name; no auto-suffixing).
- Unverified clubs are visible via `GET /clubs/{id_or_slug}` only to their requester, their admins and platform admins.
- Platform admin may add admins to an unverified club; those admins still cannot manage events until it is verified.
- Removing a club admin demotes them to `student` only if they administer no other club.
- Platform admin cannot change their own role (prevents lock-out).
- Following a club requires it to be verified; unfollowing is always allowed.
- Platform admin bootstrap runs at startup, upserts by email, sets role, and never overwrites an existing password.
- `GET /admin/users` and `PATCH /admin/users/{id}/role` were built in M1 (they are role management).
