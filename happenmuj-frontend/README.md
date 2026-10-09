# HappenMUJ frontend

Vite + React 18 + TypeScript. Dark-first, with a light theme that follows the system and a header toggle.

## Run it

```bash
npm install
npm run dev          # http://localhost:5173, uses built-in sample data
npm test             # logic + UI tests
npm run build        # production bundle in dist/
```

## Sample data vs your backend

`src/lib/api/index.ts` picks the adapter:

| `VITE_API_BASE_URL` | Adapter | Use |
|---|---|---|
| empty (default) | `mock.ts`, seeded relative to "now" | demos, design work |
| `/api` or a full URL | `http.ts`, talks to FastAPI | real backend |

Copy `.env.example` to `.env`. In dev, `/api` is proxied to `VITE_PROXY_TARGET` (default `http://localhost:8000`).
Demo logins (sample mode only, password `demo1234`): `student@muj-demo.edu`, `acm@muj-demo.edu` (club admin), `admin@muj-demo.edu` (platform admin).

## Assumptions to check against your backend

All field-name handling lives in `src/lib/api/http.ts` (normalisers), so fixes are local.

- `POST /auth/login` and `/auth/register` return a token (`access_token` or `token`) and the user, or the user is fetched via `GET /auth/me`.
- `/auth/me` includes `managed_club_ids`, `followed_club_ids`, `interests`, `preferred_categories`.
- Event cards follow the card shape in the backend prompt (section 6).
- A cancelled event can still be read by id.
- `POST /events/{id}/registration-click` returns `{ "url": "https://..." }`.
- Overlap warnings are computed in the browser from saved events.
- Dates arrive as UTC ISO strings; all day logic (Today, Tomorrow, Next 7 days, calendar) is done in IST.

## Behaviour worth knowing

- Registration is external only. The button opens the organiser's link and records a click; the UI never says "registered".
- Home filters: OR inside a group (categories, or clubs), AND between groups. The server does the matching.
- Event detail fields vary by event type; `src/lib/eventDetails.ts` drives both the form and the read-only panel.
- `npm run build:artifact` produces a single HTML fragment (`dist-artifact/artifact.html`) with React from a CDN, used for the hosted preview.
