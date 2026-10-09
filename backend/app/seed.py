"""Demo data: ``python -m app.seed --reset``  (run from backend/).

Deterministic (random seed 42) and *relative to now*, so every homepage section is populated whenever it
runs. Clubs, events, saves, comments and reactions go through the real service functions, so they obey the
same validation and keep the same counters as live traffic. Bulk views/clicks are inserted directly together
with the matching ``$inc`` on ``events.stats`` (the same documents the API would write).

The 16 clubs are the real MUJ clubs (names and categories as supplied; descriptions are generic one-liners).
People, events, posts and comments are fictional sample content.

Demo logins (password ``demo1234``): student@muj-demo.edu, acm@muj-demo.edu (club admin), admin@muj-demo.edu.
"""

import argparse
import asyncio
import io
import random
import sys
import textwrap
from datetime import timedelta
from typing import Any

from bson import ObjectId
from PIL import Image, ImageDraw, ImageFont
from pymongo import UpdateOne
from pymongo.asynchronous.database import AsyncDatabase

from app import db as db_module
from app.core import timeutil
from app.core.security import hash_password
from app.main import prepare_database
from app.models.clubs import ClubCreate
from app.models.common import SCHEMA_VERSION, normalize_terms
from app.models.community import CommentCreate, PostCreate, PostScope
from app.models.events import EventCreate
from app.services import clubs as clubs_svc
from app.services import community as community_svc
from app.services import events as events_svc
from app.services import saved as saved_svc
from app.validators import CATEGORIES

SEED = 42
PASSWORD = "demo1234"
DOMAIN = "muj-demo.edu"
DEMO_STUDENT = f"student@{DOMAIN}"
DEMO_ADMIN = f"admin@{DOMAIN}"
N_STUDENTS = 25  # the demo student + 24 more, so ranking, suggestions and analytics have something to chew on
N_SAVES = 180
N_VIEWS = 1300
N_CLICKS = 120  # 180 saves + 1300 views + 120 clicks = 1600 interactions over the last 14 days
N_POSTS, N_COMMENTS, N_REACTIONS = 12, 50, 100
POSTER_SHARE = 0.7

# name, category, one-line description. Names and categories as supplied; all verified.
CLUBS = [
    ("ACM", "technical", "Student chapter of the Association for Computing Machinery: computing talks, workshops and coding contests."),
    ("IEEE SB", "technical", "IEEE Student Branch: engineering and technology events for the whole campus."),
    ("IEEE CS", "technical", "IEEE Computer Society student chapter: software, AI and computing events."),
    ("IEEE WIE", "technical", "IEEE Women in Engineering affinity group: events that support women in technology."),
    ("LITMUS", "debating", "The literary and debating society: debates, quizzes and public speaking."),
    ("RANDOMIZE", "technical", "Student technical club (description to be confirmed by the club)."),
    ("GARUDA", "technical", "Student technical club (description to be confirmed by the club)."),
    ("DE ARTISTRY CLUB", "cultural", "Art and design club: sketching, painting and exhibitions."),
    ("THE MUSICAL CLUB (TMC)", "cultural", "Music club: open mics, band nights and jam sessions."),
    ("CHOREOGRAPHIA", "cultural", "Dance club: performances, workshops and showcases."),
    ("ROTARACT", "social", "Community service club: drives, camps and volunteering."),
    ("OMPHALOS", "cultural", "Student cultural club (description to be confirmed by the club)."),
    ("CINEPHILIA", "cultural", "Film club: screenings and discussions."),
    ("MARKSOC", "career", "Marketing society: case studies, branding and campaigns."),
    ("MANAGIA", "career", "Management club: business competitions, talks and workshops."),
    ("GLITCH", "gaming", "Gaming club: esports tournaments, game jams and board-game nights."),
]  # fmt: skip

# title, one_liner, club, category, event_type, tags, slot
# slots: today / tomorrow / week (days 2-6) / later (days 8-28) / past (1-13 days ago) /
#        cancelled / pending (pending_review) / draft / rejected
E = [
    ("Intro to Generative AI", "Build a small LLM app hands-on in one evening.", "ACM", "technical", "workshop", ["AI", "GenAI", "LLM"], "tomorrow"),
    ("CodeSprint 2.0", "Solve algorithmic problems against the clock.", "ACM", "competition", "competition", ["Competitive Programming", "DSA"], "week"),
    ("HackMUJ 24h", "Build something real in 24 hours.", "ACM", "hackathon", "hackathon", ["Hackathon", "Web", "AI"], "later"),
    ("Git & GitHub for Beginners", "Version control and open-source contribution basics.", "ACM", "technical", "workshop", ["Git", "OpenSource"], "past"),
    ("Linux Install Fest", "Bring your laptop and leave with a dual-boot setup.", "ACM", "technical", "workshop", ["Linux", "OpenSource"], "draft"),
    ("PCB Design with KiCad", "From schematic to a manufacturable board.", "IEEE SB", "technical", "workshop", ["PCB", "Hardware", "Electronics"], "week"),
    ("IEEE HardwareHack", "Hardware-first hackathon with IoT kits provided.", "IEEE SB", "hackathon", "hackathon", ["IoT", "Hardware"], "pending"),
    ("Tech Exhibition 2026", "Student projects on display.", "IEEE SB", "technical", "other", ["Exhibition", "Projects"], "later"),
    ("5G and the Next-gen Networks", "What 5G changes, and what 6G might.", "IEEE SB", "seminar", "seminar", ["5G", "Networks"], "rejected"),
    ("Machine Learning with Python", "Train, evaluate and ship a first ML model.", "IEEE CS", "academic", "workshop", ["ML", "Python", "AI"], "week"),
    ("AI Ethics and Society", "Bias, privacy and accountability in AI.", "IEEE CS", "academic", "seminar", ["AI", "Ethics"], "pending"),
    ("Women in Tech Panel", "Panel on building a career in technology.", "IEEE WIE", "seminar", "seminar", ["Diversity", "Careers"], "tomorrow"),
    ("Resume & LinkedIn Clinic", "Craft a resume recruiters actually read.", "IEEE WIE", "career", "workshop", ["Resume", "Careers"], "week"),
    ("Parliamentary Debate Championship", "Format-driven debating with seasoned adjudicators.", "LITMUS", "debating", "competition", ["Debate", "MUN"], "later"),
    ("Public Speaking Essentials", "Overcome stage fright and structure a talk.", "LITMUS", "debating", "workshop", ["Public Speaking", "Communication"], "tomorrow"),
    ("Inter-Branch Quiz League", "Teams from every branch battle in a multi-round quiz.", "LITMUS", "competition", "competition", ["Quiz", "Trivia"], "week"),
    ("Competitive Programming Bootcamp", "Patterns, practice and mock contests.", "RANDOMIZE", "technical", "workshop", ["DSA", "Competitive Programming"], "week"),
    ("Capture the Flag: Beginner Edition", "Your first security CTF, with hints on tap.", "RANDOMIZE", "technical", "competition", ["Security", "CTF"], "cancelled"),
    ("Drone Flight Basics", "Hands-on introduction to flying and building drones.", "GARUDA", "technical", "workshop", ["Drones", "Robotics"], "later"),
    ("Aero Design Challenge", "Design, build and fly a glider.", "GARUDA", "competition", "competition", ["Aero", "Design"], "past"),
    ("Live Sketching Jam", "Sketch live models and campus scenes together.", "DE ARTISTRY CLUB", "cultural", "other", ["Art", "Sketching"], "week"),
    ("Mural Painting Day", "Paint a wall of the campus together.", "DE ARTISTRY CLUB", "cultural", "other", ["Art", "Mural"], "cancelled"),
    ("Open Mic Night", "Sing, rap, recite: the stage is yours.", "THE MUSICAL CLUB (TMC)", "cultural", "cultural_show", ["Music", "Open Mic"], "tomorrow"),
    ("Battle of Bands", "Campus bands compete live.", "THE MUSICAL CLUB (TMC)", "cultural", "cultural_show", ["Bands", "Rock"], "later"),
    ("Unplugged Evening", "An acoustic evening under the stars.", "THE MUSICAL CLUB (TMC)", "cultural", "cultural_show", ["Music", "Acoustic"], "past"),
    ("Fusion Dance Showcase", "Contemporary meets folk.", "CHOREOGRAPHIA", "cultural", "cultural_show", ["Dance"], "week"),
    ("Salsa Workshop for Beginners", "No partner needed: learn your first steps.", "CHOREOGRAPHIA", "workshop", "workshop", ["Dance", "Salsa"], "today"),
    ("Blood Donation Camp", "Donate blood with the city hospital's team.", "ROTARACT", "social", "other", ["Donation", "Health"], "week"),
    ("Cleanliness Drive", "Volunteer to clean up the campus perimeter.", "ROTARACT", "social", "social", ["Volunteering"], "cancelled"),
    ("Cultural Fest Kickoff", "Announcing the line-up and opening the stalls.", "OMPHALOS", "cultural", "cultural_show", ["Fest", "Cultural"], "later"),
    ("Street Play Festival", "Nukkad natak performances on social themes.", "OMPHALOS", "cultural", "cultural_show", ["Theatre", "Street Play"], "week"),
    ("Short Film Screening & Discussion", "Watch student shorts and talk to the makers.", "CINEPHILIA", "cultural", "social", ["Film", "Shorts"], "tomorrow"),
    ("Sci-Fi Movie Night", "Open-air screening and popcorn.", "CINEPHILIA", "social", "social", ["Movies", "SciFi"], "past"),
    ("Marketing Case Study Contest", "Crack a real brand's growth problem in teams.", "MARKSOC", "career", "competition", ["Marketing", "Case Study"], "week"),
    ("Branding 101", "How brands are built, with examples.", "MARKSOC", "career", "seminar", ["Branding", "Marketing"], "pending"),
    ("Business Plan Battle", "Pitch a venture to a panel of founders.", "MANAGIA", "competition", "competition", ["Startup", "Entrepreneurship"], "pending"),
    ("Startup Founders Talk", "Founders share how they made the jump.", "MANAGIA", "career", "seminar", ["Startup", "Founders"], "today"),
    ("Valorant Campus Cup", "5v5 esports bracket with a live caster.", "GLITCH", "gaming", "competition", ["Valorant", "Esports"], "later"),
    ("Game Jam Weekend", "Make a playable game around a surprise theme.", "GLITCH", "gaming", "hackathon", ["Game Dev", "Unity"], "later"),
    ("Board Games Evening", "Catan, Codenames and chai.", "GLITCH", "gaming", "social", ["Board Games"], "past"),
]  # fmt: skip
assert len(E) == 40 and {r[2] for r in E} == {c[0] for c in CLUBS}, "every club has at least one event"

# The demo student saves these two on purpose: their times overlap, so the calendar's overlap warning shows.
OVERLAP = {"Intro to Generative AI": (15, 0, 2.5), "Open Mic Night": (16, 30, 2.0)}  # tomorrow IST: hour, minute, hours
FEATURED_TITLE = "HackMUJ 24h"
DEMO_SAVES = [
    "Intro to Generative AI",
    "Open Mic Night",
    "Women in Tech Panel",
    FEATURED_TITLE,
    "Salsa Workshop for Beginners",
    "Unplugged Evening",
]

FIRST = ["Aarav", "Diya", "Vivaan", "Ananya", "Kabir", "Ishita", "Reyansh", "Meera", "Arjun", "Saanvi", "Rohan", "Kavya",
         "Aditya", "Tanvi", "Karan", "Nisha", "Yash", "Riya", "Dev", "Pooja"]  # fmt: skip
LAST = ["Sharma", "Verma", "Gupta", "Singh", "Mehta", "Jain", "Rao", "Nair", "Kapoor", "Bansal"]
INTERESTS = ["ai", "machine learning", "robotics", "web development", "cloud", "startups", "photography", "music",
             "dance", "debate", "football", "cricket", "chess", "gaming", "electronics", "iot", "design",
             "public speaking", "research", "quantum"]  # fmt: skip
SPEAKERS = [("Dr. Meera Iyer", "IIT Delhi"), ("Prof. Arvind Rao", "IISc Bangalore"), ("Neha Kulkarni", "Google"),
            ("Rahul Menon", "AWS"), ("Dr. Sunita Joshi", "MUJ Faculty"), ("Vikram Sethi", "Founder, an EdTech startup")]  # fmt: skip
POST_TITLES = [
    "Looking for teammates for HackMUJ", "Best resources to learn system design?", "Which club should a first-year join?",
    "Anyone up for a weekend football match?", "Lost: blue water bottle near AB3", "Tips for placement season",
    "Who is coming to the Open Mic?", "Share your best campus photos", "Study group for Data Structures",
    "Need a drummer for Battle of Bands", "How do you balance clubs and academics?", "Is anyone attending the workshop?",
]  # fmt: skip
POST_BODIES = [
    "Would love to hear what has worked for you all. Drop your experiences below.",
    "Posting here so more people see it. Happy to share what I find.",
    "Totally new to this, so any pointers would be really appreciated!",
    "We have a couple of spots open. Reply or message if interested.",
    "Sharing a quick summary so nobody misses out.",
]
COMMENTS = [
    "Count me in!", "Great idea, thanks for posting.", "I tried this last semester and it worked well.",
    "Can you share more details?", "Same here, following this thread.", "DM me, happy to help.",
    "This is really useful, bookmarking it.", "Not sure about that, but worth a shot.",
    "Anyone from ECE interested?", "See you there!", "Thanks, that clears it up.",
    "I would add: start early and ask seniors.", "+1, I was about to ask the same thing.",
    "Which venue is this at?", "Good point, hadn't thought of it that way.",
]  # fmt: skip


def make_poster(title: str, club: str, rng: random.Random) -> bytes:
    w, h = 480, 640
    c1 = tuple(rng.randint(30, 200) for _ in range(3))
    c2 = tuple(rng.randint(30, 200) for _ in range(3))
    img = Image.new("RGB", (w, h))
    d = ImageDraw.Draw(img)
    for y in range(h):  # vertical gradient
        t = y / h
        d.line([(0, y), (w, y)], fill=tuple(int(a + (b - a) * t) for a, b in zip(c1, c2, strict=True)))
    try:
        big, small = ImageFont.load_default(size=38), ImageFont.load_default(size=22)
    except TypeError:  # very old Pillow: fixed-size bitmap font
        big = small = ImageFont.load_default()
    y = 200
    for line in textwrap.wrap(title, 16):
        d.text((36, y), line, fill="white", font=big)
        y += 48
    d.text((36, h - 70), club, fill="white", font=small)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def details_for(etype: str, title: str, tags: list[str], rng: random.Random) -> dict:
    sp = rng.choice(SPEAKERS)
    money = lambda: rng.choice(["Rs 5,000", "Rs 10,000", "Rs 15,000", "Goodies + certificate"])  # noqa: E731
    if etype == "workshop":
        return {"speaker": {"name": sp[0], "bio": f"{sp[1]}; practitioner and mentor."}, "topics": [t.title() for t in tags],
                "duration_minutes": rng.choice([90, 120, 180]), "prerequisites": rng.choice([[], ["Basic programming"], ["Laptop"]]),
                "bring_own_laptop": rng.random() < 0.6}  # fmt: skip
    if etype == "competition":
        return {"prizes": [{"rank": 1, "reward": money()}, {"rank": 2, "reward": money()}],
                "eligibility": rng.choice(["Open to all MUJ students", "Undergraduates only", "Teams from any branch"]),
                "rounds": [{"name": "Prelims", "description": "Screening round"}, {"name": "Finals", "description": "Top teams"}],
                "judging_criteria": ["Accuracy", "Creativity", "Presentation"]}  # fmt: skip
    if etype == "hackathon":
        return {"themes": [t.title() for t in tags[:2]], "tracks": rng.sample(["Open Innovation", "Web", "AI/ML", "IoT", "Social Impact"], 3),
                "duration_hours": rng.choice([12, 24, 36]), "prizes": [{"rank": 1, "reward": "Rs 25,000"}, {"rank": 2, "reward": "Rs 10,000"}],
                "max_teams": rng.choice([20, 30, 50])}  # fmt: skip
    if etype == "sports_match":
        return {"sport": tags[0], "match_type": rng.choice(["league", "knockout", "friendly", "final"]),
                "teams": [{"name": n} for n in rng.sample(["CSE", "ECE", "Mech", "Civil", "IT", "EEE"], 2)],
                "format": rng.choice(["Best of 3", "Single elimination", "Round robin", "Timed halves"])}  # fmt: skip
    if etype == "cultural_show":
        return {"performances": [{"title": f"Act {i}", "performer": rng.choice(FIRST)} for i in range(1, 4)],
                "artists": rng.sample(FIRST, 3), "auditions_required": rng.random() < 0.4, "audition_date": None}  # fmt: skip
    if etype == "seminar":
        return {"speaker": {"name": sp[0], "affiliation": sp[1]}, "topic": title, "q_and_a_enabled": rng.random() < 0.8}
    return {"extra": {"note": f"Organised by campus clubs: {', '.join(tags)}", "capacity": rng.choice([50, 100, 200])}}


def fee_for(etype: str, rng: random.Random) -> dict:
    table = {
        "workshop": [{"type": "free"}, {"type": "fixed", "amount": 99}, {"type": "fixed", "amount": 199}, {"type": "per_participant", "amount": 150}],
        "competition": [{"type": "per_team", "amount": 200}, {"type": "per_team", "amount": 500}, {"type": "fixed", "amount": 100}, {"type": "free"}],
        "hackathon": [{"type": "per_team", "amount": 300}, {"type": "per_team", "amount": 500}, {"type": "free"}],
        "sports_match": [{"type": "free"}, {"type": "per_team", "amount": 500}, {"type": "per_team", "amount": 1000}],
        "cultural_show": [{"type": "free"}, {"type": "fixed", "amount": 50}, {"type": "fixed", "amount": 200}],
    }  # fmt: skip
    return rng.choice(table.get(etype, [{"type": "free"}, {"type": "free"}, {"type": "fixed", "amount": 50}]))


def team_for(etype: str, rng: random.Random) -> dict:
    if etype == "competition":
        return rng.choice(
            [
                {"type": "individual"},
                {"type": "range", "min": 2, "max": 4},
                {"type": "fixed", "min": 2, "max": 2},
                {"type": "fixed", "min": 3, "max": 3},
            ]
        )
    if etype == "hackathon":
        return rng.choice([{"type": "range", "min": 2, "max": 4}, {"type": "range", "min": 3, "max": 5}])
    if etype == "sports_match":
        return {"type": "fixed", "min": rng.choice([5, 7, 11]), "max": None}
    if etype in ("workshop", "seminar"):
        return rng.choice([{"type": "individual"}, {"type": "not_applicable"}])
    return {"type": "not_applicable"}


DURATION_H = {"workshop": (2, 3), "competition": (3, 5), "hackathon": (24, 24), "sports_match": (2, 3),
              "cultural_show": (3, 3), "seminar": (1, 2), "social": (2, 3), "other": (3, 5)}  # fmt: skip
REG_PLATFORM = {"hackathon": ["devfolio", "unstop"], "competition": ["unstop", "google_forms"]}


async def run_seed(db: AsyncDatabase, *, reset: bool) -> dict:
    random.seed(SEED)
    rng = random.Random(SEED)

    if reset:
        await db.client.drop_database(db.name)  # also drops GridFS (fs.files / fs.chunks)
    await prepare_database()
    if await db.events.estimated_document_count() or await db.clubs.estimated_document_count():
        raise SystemExit("Database already has data. Re-run with --reset to wipe and reseed.")

    now = timeutil.now()
    pw_hash = hash_password(PASSWORD)  # one hash for every seeded user keeps seeding fast

    async def add_user(name: str, email: str, role: str = "student", **extra: Any) -> dict:
        doc = {"name": name, "email": email, "password_hash": pw_hash, "role": role, "interests": [],
               "preferred_categories": [], "followed_club_ids": [], "created_at": now - timedelta(days=rng.randint(5, 60)),
               "schema_v": SCHEMA_VERSION, **extra}  # fmt: skip
        doc["_id"] = (await db.users.insert_one(doc)).inserted_id
        return doc

    # The platform admin. If .env already bootstrapped this email, reuse it and set the demo password.
    await db.users.update_one(
        {"email": DEMO_ADMIN},
        {"$set": {"role": "platform_admin", "password_hash": pw_hash, "name": "Platform Admin"},
         "$setOnInsert": {"interests": [], "preferred_categories": [], "followed_club_ids": [], "created_at": now, "schema_v": SCHEMA_VERSION}},
        upsert=True,
    )  # fmt: skip
    admin = await db.users.find_one({"email": DEMO_ADMIN})

    # ---------------------------------------------------------------- students (the demo student first)
    students: list[dict] = [
        await add_user("Demo Student", DEMO_STUDENT, interests=["ai", "robotics", "music", "gaming"],
                       preferred_categories=["technical", "hackathon", "cultural"])
    ]  # fmt: skip
    for i in range(1, N_STUDENTS):
        first, last = FIRST[i % len(FIRST)], LAST[(i * 3) % len(LAST)]
        students.append(await add_user(
            f"{first} {last}", f"{first}.{last}{i}@{DOMAIN}".lower(),
            interests=normalize_terms(rng.sample(INTERESTS, rng.randint(2, 5))),
            preferred_categories=rng.sample(CATEGORIES[:9], rng.randint(1, 3)),
        ))  # fmt: skip

    # ---------------------------------------------------------------- the 16 real clubs, all verified, one admin each
    club_docs: dict[str, dict] = {}
    club_admin: dict[str, dict] = {}
    for idx, (name, cat, desc) in enumerate(CLUBS):
        club = await clubs_svc.request_club(
            db, students[idx + 1]["_id"], ClubCreate(name=name, description=desc, category=cat)
        )
        await clubs_svc.verify_club(db, club["_id"], admin["_id"])
        u = await add_user(f"{name.title()} Admin", f"{club['slug']}@{DOMAIN}")
        await clubs_svc.add_admin(db, club["_id"], u["_id"])
        club_admin[name] = await db.users.find_one({"_id": u["_id"]})  # re-read: role is now club_admin
        club_docs[name] = await db.clubs.find_one({"_id": club["_id"]})
    club_ids = [c["_id"] for c in club_docs.values()]
    for s in students:  # follows: the demo student follows ACM, IEEE SB and GLITCH
        pick = (
            [club_docs[n]["_id"] for n in ("ACM", "IEEE SB", "GLITCH")] if s["email"] == DEMO_STUDENT
            else rng.sample(club_ids, rng.randint(0, 3))
        )  # fmt: skip
        await db.users.update_one({"_id": s["_id"]}, {"$set": {"followed_club_ids": pick}})
        s["followed_club_ids"] = pick

    # ---------------------------------------------------------------- events (through the services)
    not_specified = set(rng.sample(range(len(E)), 5))  # a few events leave fee and team unstated
    today_ist = timeutil.ist_date(now)

    def ist_at(days: int, hour: int, minute: int = 0):
        start, _ = timeutil.ist_day_range(today_ist + timedelta(days=days))
        return start + timedelta(hours=hour, minutes=minute)

    def start_for(title: str, slot: str):
        if slot == "today":
            return now + timedelta(minutes=rng.randint(60, 240))
        if slot == "tomorrow":
            if title in OVERLAP:
                h, m, _ = OVERLAP[title]
                return ist_at(1, h, m)
            return ist_at(1, rng.randint(9, 19), rng.choice([0, 30]))
        if slot == "week":
            return ist_at(rng.randint(2, 6), rng.randint(9, 19), rng.choice([0, 15, 30, 45]))
        if slot == "past":
            return now - timedelta(days=rng.randint(1, 13), hours=rng.randint(1, 8))
        if slot == "later":
            return ist_at(rng.randint(8, 28), rng.randint(9, 19), rng.choice([0, 15, 30, 45]))
        return ist_at(
            rng.randint(3, 25), rng.randint(9, 19), rng.choice([0, 30])
        )  # cancelled / pending / draft / rejected

    events: list[dict] = []
    closed_left = 3  # a few upcoming events whose registration deadline has already passed
    pngs = 0
    for i, (title, liner, club_name, cat, etype, tags, slot) in enumerate(E):
        start = start_for(title, slot)
        if title in OVERLAP:
            end = start + timedelta(hours=OVERLAP[title][2])
        else:
            lo, hi = DURATION_H[etype]
            end = start + timedelta(hours=rng.randint(lo, hi), minutes=rng.choice([0, 30]))
        required = rng.random() < (0.9 if etype in ("workshop", "competition", "hackathon", "seminar") else 0.35)
        reg: dict[str, Any] = {"required": required}
        deadline = None
        if required:
            plat = rng.choice(REG_PLATFORM.get(etype, ["google_forms", "website"]))
            reg.update(platform=plat, url=f"https://forms.example.com/{plat}/{i + 1}")
            if slot in ("week", "later") and closed_left and title != FEATURED_TITLE:
                deadline, closed_left = now - timedelta(days=1), closed_left - 1  # registration already closed
            elif slot in ("today", "tomorrow", "week") and rng.random() < 0.5:
                d = min(now + timedelta(hours=rng.randint(6, 60)), start - timedelta(minutes=30))
                deadline = d if d > now + timedelta(hours=1) else None  # urgent: within 72h
            elif rng.random() < 0.6:
                d = start - timedelta(days=1)
                deadline = d if d > now else None
        fee, team = fee_for(etype, rng), team_for(etype, rng)
        if i in not_specified:
            fee, team = {"type": "not_specified"}, {"type": "not_specified"}
        publish_start = start if slot != "past" else now + timedelta(days=1)  # backdated after publishing
        payload = {
            "club_id": str(club_docs[club_name]["_id"]), "title": title, "one_liner": liner,
            "description": f"{liner} Organised by {club_name}. Details and updates will be shared on this page.",
            "category": cat, "event_type": etype, "tags": tags,
            "schedule": {"start": publish_start.isoformat(), "end": (publish_start + (end - start)).isoformat()},
            "venue": rng.choice([{"name": "AB3 Seminar Hall", "building": "AB3"}, {"name": "Main Auditorium", "building": "AB1"},
                                 {"name": "Sports Complex", "building": "Sports"}, {"name": "Open Air Theatre"},
                                 {"name": "Library Lawns"}, {"name": "AB2 Lab 204", "building": "AB2", "room": "204"}]),
            "fee": fee, "team": team,
            "registration": {**reg, "deadline": None if slot == "past" else (deadline.isoformat() if deadline else None)},
            "contact": {"name": rng.choice(FIRST), "email": f"{club_docs[club_name]['slug']}@{DOMAIN}"},
            "details": details_for(etype, title, tags, rng),
        }  # fmt: skip
        owner = club_admin[club_name]
        ev = await events_svc.create_event(db, owner, EventCreate.model_validate(payload))
        eid = ev["_id"]
        if slot != "draft":
            await events_svc.submit_event(db, owner, eid)
        if slot == "rejected":
            await events_svc.reject_event(db, eid, "Please add a clearer description and venue details.")
        if slot in ("today", "tomorrow", "week", "later", "past", "cancelled"):
            await events_svc.approve_event(db, eid)
        if slot == "cancelled":
            await events_svc.cancel_event(db, owner, eid, "Venue unavailable on the scheduled date.")
        if slot == "past":  # backdate: published, then time passed
            await db.events.update_one({"_id": eid}, {"$set": {
                "schedule.start": start, "schedule.end": end, "registration.deadline": (start - timedelta(days=2)) if required else None,
                "published_at": start - timedelta(days=10)}})  # fmt: skip
        if rng.random() < POSTER_SHARE:
            await events_svc.set_poster(db, owner, eid, make_poster(title, club_name, rng), "image/png")
            pngs += 1
        events.append({"id": eid, "slot": slot, "title": title, "start": start, "etype": etype, "owner": owner})

    by_title = {e["title"]: e for e in events}
    await events_svc.set_featured(db, by_title[FEATURED_TITLE]["id"], True)  # exactly one featured event

    # ---------------------------------------------------------------- engagement
    public = [e for e in events if e["slot"] in ("today", "tomorrow", "week", "later", "past")]
    order = rng.sample(public, len(public))  # a random popularity ranking, skewed so the Top 10 is not flat
    weights = [(0.3 if e["slot"] == "past" else 1.0) / (rank + 1) ** 0.8 for rank, e in enumerate(order)]
    people = students + list(club_admin.values())

    def rand_ts(e: dict):
        lo, hi = now - timedelta(days=14), min(now, e["start"])
        if hi <= lo + timedelta(hours=1):
            hi = now
        return lo + (hi - lo) * rng.random()

    pairs: set[tuple[ObjectId, ObjectId]] = set()
    saved_pairs: list[tuple[dict, dict]] = []

    async def do_save(s: dict, e: dict) -> None:
        saved, _ = await saved_svc.save_event(db, s["_id"], e["id"])  # the real service: counters stay consistent
        pairs.add((s["_id"], e["id"]))
        ts = rand_ts(e)
        await db.saved_events.update_one({"_id": saved["_id"]}, {"$set": {"created_at": ts}})
        await db.event_interactions.update_one(
            {"event_id": e["id"], "user_id": s["_id"], "type": "save"}, {"$set": {"ts": ts}}
        )
        saved_pairs.append((s, e))

    for title in DEMO_SAVES:  # the demo student's saves, including the overlapping pair
        await do_save(students[0], by_title[title])
    attempts = 0
    while len(pairs) < N_SAVES and attempts < N_SAVES * 20:
        attempts += 1
        e, s = rng.choices(order, weights)[0], rng.choice(students)
        if (s["_id"], e["id"]) not in pairs:
            await do_save(s, e)

    interactions: list[dict] = []
    counters: dict[ObjectId, dict[str, int]] = {}

    def log(kind: str, e: dict, user: dict | None, stat: str) -> None:
        interactions.append({"event_id": e["id"], "user_id": user["_id"] if user else None, "type": kind,
                             "ts": rand_ts(e), "schema_v": SCHEMA_VERSION})  # fmt: skip
        counters.setdefault(e["id"], {}).setdefault(stat, 0)
        counters[e["id"]][stat] += 1

    for _ in range(N_VIEWS):
        log("view", rng.choices(order, weights)[0], rng.choice(people) if rng.random() < 0.7 else None, "views")
    reg_required = {
        e["id"] for e in public
        if (await db.events.find_one({"_id": e["id"]}, {"registration.required": 1}))["registration"]["required"]
    }  # fmt: skip
    clicked_pairs: set[tuple[ObjectId, ObjectId]] = set()
    for s, e in saved_pairs:  # some saved events were followed through to the registration page
        if e["id"] in reg_required and rng.random() < 0.3:
            log("registration_click", e, s, "registration_clicks")
            clicked_pairs.add((s["_id"], e["id"]))
    reg_pool = [e for e in order if e["id"] in reg_required]
    while sum(1 for i in interactions if i["type"] == "registration_click") < N_CLICKS and reg_pool:
        log(
            "registration_click",
            rng.choice(reg_pool),
            rng.choice(students) if rng.random() < 0.8 else None,
            "registration_clicks",
        )
    await db.event_interactions.insert_many(interactions)
    await db.events.bulk_write(
        [UpdateOne({"_id": eid}, {"$inc": {f"stats.{k}": v for k, v in c.items()}}) for eid, c in counters.items()]
    )
    for uid, eid in clicked_pairs:
        await db.saved_events.update_one(
            {"user_id": uid, "event_id": eid}, {"$set": {"status": "registration_initiated"}}
        )

    # ---------------------------------------------------------------- community (through the services)
    posts: list[dict] = []
    scopes = ([PostScope(type="global")] * 5
              + [PostScope(type="event", ref_id=str(e["id"])) for e in rng.sample(public, 4)]
              + [PostScope(type="club", ref_id=str(club_docs[n]["_id"])) for n in ("ACM", "THE MUSICAL CLUB (TMC)", "GLITCH")])  # fmt: skip
    for n, (title, scope) in enumerate(zip(POST_TITLES[:N_POSTS], scopes, strict=True)):
        author = students[0] if n in (1, 6) else rng.choice(people)  # the demo student authors two posts
        posts.append(await community_svc.create_post(db, author, PostCreate(
            scope=scope, title=title, body=rng.choice(POST_BODIES), tags=rng.sample(["help", "teamup", "advice", "events", "campus"], 2))))  # fmt: skip
    by_post: dict[ObjectId, list[dict]] = {p["_id"]: [] for p in posts}
    all_comments: list[dict] = []
    for _ in range(N_COMMENTS):
        p = rng.choice(posts)
        parent = rng.choice(by_post[p["_id"]]) if by_post[p["_id"]] and rng.random() < 0.4 else None
        c = await community_svc.create_comment(db, rng.choice(people), p["_id"], CommentCreate(
            body=rng.choice(COMMENTS), parent_id=str(parent["_id"]) if parent else None))  # fmt: skip
        by_post[p["_id"]].append(c)
        all_comments.append(c)
    targets = [("post", p["_id"]) for p in posts] + [("comment", c["_id"]) for c in all_comments]
    reacted: set[tuple[ObjectId, str, ObjectId]] = set()
    while len(reacted) < N_REACTIONS:
        ttype, tid = rng.choice(targets) if rng.random() < 0.4 else rng.choice(targets[: len(posts)])
        u = rng.choice(people)
        if (u["_id"], ttype, tid) in reacted:
            continue
        reacted.add((u["_id"], ttype, tid))
        await community_svc.toggle_reaction(db, u, ttype, tid, "like" if rng.random() < 0.75 else "insightful")

    # ---------------------------------------------------------------- summary
    counts = {
        n: await db[n].count_documents({})
        for n in ["users", "clubs", "events", "saved_events", "event_interactions", "posts", "comments", "reactions"]
    }
    counts["posters (fs.files)"] = await db["fs.files"].count_documents({})
    by_status = {
        r["_id"]: r["count"]
        async for r in await db.events.aggregate([{"$group": {"_id": "$status", "count": {"$sum": 1}}}])
    }
    return {
        "counts": counts, "events_by_status": by_status, "posters": pngs,
        "credentials": {
            "student": (DEMO_STUDENT, PASSWORD),
            "club_admin": (f"acm@{DOMAIN}", PASSWORD),
            "platform_admin": (DEMO_ADMIN, PASSWORD),
        },
    }  # fmt: skip


def print_summary(res: dict) -> None:
    print("\nSeeded HappenMUJ demo data\n" + "-" * 38)
    for k, v in res["counts"].items():
        print(f"  {k:<24}{v:>6}")
    print("\n  events by status: " + ", ".join(f"{k}={v}" for k, v in sorted(res["events_by_status"].items())))
    print("\nSample logins")
    for role, (email, pw) in res["credentials"].items():
        print(f"  {role:<15}{email}  /  {pw}")
    print(
        "\nNext: uvicorn app.main:app --reload  ->  http://localhost:8000/docs   (frontend: cd ../happenmuj-frontend && npm run dev)\n"
    )


async def main() -> None:
    ap = argparse.ArgumentParser(description="Seed the HappenMUJ database with demo data")
    ap.add_argument("--reset", action="store_true", help="drop the configured database first")
    args = ap.parse_args()
    db = await db_module.init_db()
    try:
        print(f"Seeding database '{db.name}'" + (" (reset)" if args.reset else ""))
        print_summary(await run_seed(db, reset=args.reset))
    finally:
        await db_module.close_db()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
