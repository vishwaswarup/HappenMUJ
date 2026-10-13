"""Production seed: ``python -m app.seed_prod``  (run from backend/).

Creates ONLY the real data a live site needs: the 16 MUJ clubs (verified) and the platform admin from
PLATFORM_ADMIN_EMAIL / PLATFORM_ADMIN_PASSWORD. No demo students, events, posts or demo password. Never wipes
anything and refuses to run if clubs already exist. Set APP_ENV=production so unsafe settings are rejected.
"""

import asyncio
import sys

from app import db as db_module
from app.config import get_settings
from app.main import prepare_database
from app.models.clubs import ClubCreate
from app.seed import CLUBS
from app.services import clubs as clubs_svc


async def run() -> int:
    s = get_settings()
    if problems := s.production_problems():
        print("Refusing to seed: " + "; ".join(problems), file=sys.stderr)
        return 1
    db = await db_module.init_db()
    try:
        await prepare_database()  # also creates the admin from the environment
        if await db.clubs.estimated_document_count():
            print("Clubs already exist; nothing to do.", file=sys.stderr)
            return 1
        admin = await db.users.find_one({"email": s.platform_admin_email.lower()})
        for name, category, description in CLUBS:
            club = await clubs_svc.request_club(
                db, admin["_id"], ClubCreate(name=name, description=description, category=category)
            )
            await clubs_svc.verify_club(db, club["_id"], admin["_id"])
        print(f"Seeded {len(CLUBS)} verified clubs into '{db.name}'. Admin: {s.platform_admin_email}")
        return 0
    finally:
        await db_module.close_db()


if __name__ == "__main__":
    sys.exit(asyncio.run(run()))
