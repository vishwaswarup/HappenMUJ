#!/usr/bin/env python3
"""Read-mostly check of a DEPLOYED API that has the production seed (no demo accounts needed).

    python3 scripts/live_check.py https://your-api.example.com/api

Checks health, sign-in config, the 16 clubs, the catalogue and home endpoints, then registers one throwaway
student (smoke-<random>@example.org) and verifies sign-in and /auth/me. Exit code 0 = all passed.
"""

import json
import secrets
import sys
import urllib.error
import urllib.request

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8001/api").rstrip("/")
failures = 0


def call(method: str, path: str, body=None, token=None):
    req = urllib.request.Request(BASE + path, method=method, data=json.dumps(body).encode() if body else None)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:  # first call may wake a sleeping free-tier host
            return r.status, json.loads(r.read() or "null")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or "null")


def check(name: str, ok: bool, detail: str = "") -> None:
    global failures
    failures += not ok
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  ({detail})" if detail and not ok else ""))


s, h = call("GET", "/health")
check("health", s == 200 and h["status"] == "ok" and h["transactions_supported"], str(h))
s, cfg = call("GET", "/auth/config")
check("auth config", s == 200 and "google_client_id" in cfg)
s, clubs = call("GET", "/clubs?page_size=50")
check("16 verified clubs", s == 200 and clubs["total"] == 16, str(clubs.get("total") if s == 200 else s))
s, ev = call("GET", "/events?page_size=5")
check("catalogue answers", s == 200 and "facets" in ev)
for path in ("/home/featured", "/home/suggested", "/home/top-events", "/home/tomorrow", "/home/next-7-days"):
    s, _ = call("GET", path)
    check(path, s == 200)
s, _ = call("GET", "/admin/events")
check("admin area needs sign-in", s == 401)
email, pw = f"smoke-{secrets.token_hex(4)}@example.org", secrets.token_urlsafe(12)
s, reg = call("POST", "/auth/register", {"name": "Live Check", "email": email, "password": pw})
check("register", s == 201 and reg["user"]["role"] == "student")
s, login = call("POST", "/auth/login", {"email": email, "password": pw})
check("login", s == 200)
s, me = call("GET", "/auth/me", token=login.get("access_token") if s == 200 else None)
check("me", s == 200 and me["email"] == email)
s, _ = call("POST", "/auth/login", {"email": email, "password": "wrong-password-1"})
check("wrong password rejected", s == 401)
print(f"\n{'ALL PASSED' if not failures else str(failures) + ' FAILED'} against {BASE}")
print(f"(left one test account behind: {email}; delete it in the database if you care)")
sys.exit(1 if failures else 0)
