"""Demo data: ``python -m app.seed --reset``  (run from backend/).

Deterministic (random seed 42) and *relative to now*, so every homepage section is populated whenever
it runs. Clubs, events, saves, comments and reactions go through the real service functions, so they
obey the same validation and keep the same counters as live traffic. Bulk views/clicks are inserted
directly together with the matching ``$inc`` on ``events.stats`` (same documents the API would write).
All sample people, clubs and events are fictional.
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
from app.config import get_settings
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
PASSWORD = "password123"
N_STUDENTS = 40
N_SAVES = 400
N_VIEWS = 2350
N_CLICKS = 250  # 400 saves + 2350 views + 250 clicks = 3000 interactions
N_POSTS, N_COMMENTS, N_REACTIONS = 20, 120, 300
POSTER_SHARE = 0.7

# name, category, description, verified
CLUBS = [
    ("ACM", "technical", "Computing and AI community: talks, workshops and coding contests.", True),
    ("IEEE", "technical", "Electronics, hardware and engineering student chapter.", True),
    ("LITMUS", "debating", "Literature, debating and public speaking society.", True),
    ("TMC", "social", "General-interest student club for meetups and socials.", True),
    ("AURA", "cultural", "Music, dance and the annual cultural fest.", True),
    ("E-Cell", "career", "Entrepreneurship cell: startups, pitching and careers.", True),
    ("Sports Committee", "sports", "Inter-department leagues and campus sports.", True),
    ("AWS Cloud Club", "technical", "Cloud computing community.", True),
    ("Robotix", "technical", "Robotics and embedded systems club.", True),
    ("Lens Photography Club", "cultural", "Photography walks, contests and exhibitions.", True),
    ("Game Guild", "gaming", "Esports and tabletop gaming (awaiting verification).", False),
    ("Dance Club", "cultural", "Street and fusion dance crew (awaiting verification).", False),
]  # fmt: skip

# title, one_liner, club, category, event_type, tags
E = [
    ("Intro to Generative AI", "Build a small LLM app hands-on in one evening.", "ACM", "technical", "workshop", ["AI", "GenAI", "LLM"]),
    ("Cloud 101: Deploying on AWS", "Launch your first app on the cloud, start to finish.", "AWS Cloud Club", "technical", "workshop", ["AWS", "Cloud", "DevOps"]),
    ("Arduino Basics Bootcamp", "Blink, sense, move: your first embedded projects.", "Robotix", "workshop", "workshop", ["Arduino", "Robotics", "Electronics"]),
    ("Portrait Photography Masterclass", "Light, lenses and posing for striking portraits.", "Lens Photography Club", "workshop", "workshop", ["Photography", "Portrait"]),
    ("Resume Building Workshop", "Craft a one-page resume recruiters actually read.", "E-Cell", "career", "workshop", ["Resume", "Careers"]),
    ("Git & GitHub for Beginners", "Version control and open-source contribution basics.", "ACM", "technical", "workshop", ["Git", "OpenSource"]),
    ("PCB Design with KiCad", "From schematic to a manufacturable board.", "IEEE", "technical", "workshop", ["PCB", "Hardware", "Electronics"]),
    ("Public Speaking Essentials", "Overcome stage fright and structure a talk.", "LITMUS", "debating", "workshop", ["Public Speaking", "Communication"]),
    ("Pitch Deck Clinic", "Get live feedback on your startup pitch.", "E-Cell", "career", "workshop", ["Startup", "Pitch"]),
    ("Machine Learning with Python", "Train, evaluate and ship a first ML model.", "ACM", "academic", "workshop", ["ML", "Python", "AI"]),
    ("CodeSprint 2.0", "Solve algorithmic problems against the clock.", "ACM", "competition", "competition", ["Competitive Programming", "DSA"]),
    ("Inter-Branch Quiz League", "Teams from every branch battle in a multi-round quiz.", "LITMUS", "competition", "competition", ["Quiz", "Trivia"]),
    ("Robo Race", "Line-following robots race for the podium.", "Robotix", "competition", "competition", ["Robotics", "Line Follower"]),
    ("Capture the Campus", "Photo contest: show us MUJ like you've never seen it.", "Lens Photography Club", "competition", "competition", ["Photography", "Contest"]),
    ("Parliamentary Debate Championship", "Format-driven debating with seasoned adjudicators.", "LITMUS", "debating", "competition", ["Debate", "MUN"]),
    ("Business Plan Battle", "Pitch a venture to a panel of founders.", "E-Cell", "competition", "competition", ["Startup", "Entrepreneurship"]),
    ("Valorant Campus Cup", "5v5 esports bracket with a live caster.", "TMC", "gaming", "competition", ["Valorant", "Esports"]),
    ("Open Mic Showdown", "Sing, rap, recite: the stage is yours.", "AURA", "cultural", "competition", ["Music", "Open Mic"]),
    ("HackMUJ 24h", "Build something real in 24 hours.", "ACM", "hackathon", "hackathon", ["Hackathon", "Web", "AI"]),
    ("Cloud Innovate Hackathon", "Serverless ideas that scale.", "AWS Cloud Club", "hackathon", "hackathon", ["AWS", "Cloud", "Serverless"]),
    ("IEEE HardwareHack", "Hardware-first hackathon with IoT kits provided.", "IEEE", "hackathon", "hackathon", ["IoT", "Hardware"]),
    ("Climate Tech Sprint", "Prototype for a greener campus and city.", "E-Cell", "hackathon", "hackathon", ["Climate", "Sustainability"]),
    ("Game Jam Weekend", "Make a playable game around a surprise theme.", "TMC", "gaming", "hackathon", ["Game Dev", "Unity"]),
    ("Inter-Department Football League", "Round-robin league across departments.", "Sports Committee", "sports", "sports_match", ["Football"]),
    ("Basketball Friendly: CSE vs ECE", "A friendly with bragging rights.", "Sports Committee", "sports", "sports_match", ["Basketball"]),
    ("Cricket Premier League Finals", "The season finale under the lights.", "Sports Committee", "sports", "sports_match", ["Cricket"]),
    ("Badminton Doubles Open", "Open doubles bracket, all skill levels.", "Sports Committee", "sports", "sports_match", ["Badminton"]),
    ("Table Tennis Knockout", "Single-elimination, best of five.", "Sports Committee", "sports", "sports_match", ["Table Tennis"]),
    ("Chess Rapid Tournament", "Swiss-system rapid chess.", "Sports Committee", "sports", "sports_match", ["Chess"]),
    ("AURA Night 2026", "The flagship night of music and dance.", "AURA", "cultural", "cultural_show", ["Music", "Dance", "Fest"]),
    ("Classical Evening", "An evening of Hindustani and Carnatic classical.", "AURA", "cultural", "cultural_show", ["Classical", "Music"]),
    ("Street Play Festival", "Nukkad natak performances on social themes.", "LITMUS", "cultural", "cultural_show", ["Theatre", "Street Play"]),
    ("Fusion Dance Showcase", "Contemporary meets folk.", "AURA", "cultural", "cultural_show", ["Dance"]),
    ("Stand-up Comedy Night", "Student comics take the mic.", "TMC", "cultural", "cultural_show", ["Comedy"]),
    ("Battle of Bands", "Campus bands compete live.", "AURA", "cultural", "cultural_show", ["Bands", "Rock"]),
    ("Future of Quantum Computing", "Where qubits are heading, from lab to industry.", "IEEE", "seminar", "seminar", ["Quantum", "Physics"]),
    ("Careers in Cloud: Industry Talk", "Roles, skills and paths in cloud engineering.", "AWS Cloud Club", "career", "seminar", ["Cloud", "Careers"]),
    ("Women in Tech Panel", "Panel on building a career in technology.", "ACM", "seminar", "seminar", ["Diversity", "Careers"]),
    ("From Campus to Startup", "Founders share how they made the jump.", "E-Cell", "seminar", "seminar", ["Startup"]),
    ("AI Ethics and Society", "Bias, privacy and accountability in AI.", "ACM", "academic", "seminar", ["AI", "Ethics"]),
    ("5G and the Next-gen Networks", "What 5G changes, and what 6G might.", "IEEE", "seminar", "seminar", ["5G", "Networks"]),
    ("Research Paper Writing Seminar", "Structure, citations and getting published.", "IEEE", "academic", "seminar", ["Research", "Writing"]),
    ("Placement Prep: Aptitude Strategies", "Speed and accuracy for aptitude rounds.", "E-Cell", "career", "seminar", ["Placements", "Aptitude"]),
    ("Freshers' Meetup", "Meet your seniors and find your club.", "TMC", "social", "social", ["Freshers", "Networking"]),
    ("Board Games Evening", "Catan, Codenames and chai.", "TMC", "gaming", "social", ["Board Games"]),
    ("Photo Walk: Old Jaipur", "A morning walk with cameras through the old city.", "Lens Photography Club", "social", "social", ["Photo Walk", "Jaipur"]),
    ("Alumni Interaction Evening", "Chat with alumni about life after MUJ.", "E-Cell", "social", "social", ["Alumni", "Networking"]),
    ("Cleanliness Drive", "Volunteer to clean up the campus perimeter.", "TMC", "social", "social", ["Volunteering"]),
    ("Movie Night: Sci-Fi Special", "Open-air screening and popcorn.", "ACM", "social", "social", ["Movies", "SciFi"]),
    ("Blood Donation Camp", "Donate blood with the city hospital's team.", "TMC", "other", "other", ["Donation", "Health"]),
    ("Open House: Club Fair", "Every club at one place, one afternoon.", "E-Cell", "other", "other", ["Clubs", "Fair"]),
    ("Tech Exhibition 2026", "Student projects on display.", "IEEE", "other", "other", ["Exhibition", "Projects"]),
    ("Book Swap Day", "Bring one, take one.", "LITMUS", "other", "other", ["Books", "Swap"]),
    ("Charity Run 5K", "A 5K run for a good cause.", "Sports Committee", "other", "other", ["Charity", "Running"]),
    ("Orientation: Library Resources", "Journals, databases and how to use them.", "LITMUS", "academic", "other", ["Library", "Research"]),
]  # fmt: skip
assert len(E) == 55

FIRST = ["Aarav", "Diya", "Vivaan", "Ananya", "Kabir", "Ishita", "Reyansh", "Meera", "Arjun", "Saanvi", "Rohan", "Kavya",
         "Aditya", "Tanvi", "Karan", "Nisha", "Yash", "Riya", "Dev", "Pooja"]  # fmt: skip
LAST = ["Sharma", "Verma", "Gupta", "Singh", "Mehta", "Jain", "Rao", "Nair", "Kapoor", "Bansal"]
INTERESTS = ["ai", "machine learning", "robotics", "web development", "cloud", "startups", "photography", "music",
             "dance", "debate", "football", "cricket", "chess", "gaming", "electronics", "iot", "design",
             "public speaking", "research", "quantum"]  # fmt: skip
SPEAKERS = [("Dr. Meera Iyer", "IIT Delhi"), ("Prof. Arvind Rao", "IISc Bangalore"), ("Neha Kulkarni", "Google"),
            ("Rahul Menon", "AWS"), ("Dr. Sunita Joshi", "MUJ Faculty"), ("Vikram Sethi", "Founder, an EdTech startup")]  # fmt: skip
POST_TITLES = [
    "Looking for teammates for the next hackathon", "Best resources to learn system design?",
    "Which club should a first-year join?", "Anyone up for a weekend football match?",
    "Lost: blue water bottle near AB3", "Tips for placement season", "Laptop recommendations under 60k?",
    "Share your best campus photos", "Study group for Data Structures", "Open source contribution ideas",
    "Cafeteria feedback thread", "Which sessions are you excited about?", "Need a drummer for Battle of Bands",
    "How do you balance clubs and academics?", "Any good internship leads?", "Carpool to the city this weekend?",
    "Book recommendations for the break", "Is anyone attending the workshop?", "Ideas for the next club event",
    "Roast my resume (be kind)",
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


class Stats:
    def __init__(self) -> None:
        self.rows: dict[str, Any] = {}


def slugify_email(first: str, last: str, n: int, domain: str) -> str:
    return f"{first}.{last}{n}@{domain}".lower()


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
    domain = (get_settings().email_domains or ["jaipur.manipal.edu"])[0]

    if reset:
        await db.client.drop_database(db.name)  # also drops GridFS (fs.files / fs.chunks)
    await prepare_database()
    if await db.events.estimated_document_count() or await db.clubs.estimated_document_count():
        raise SystemExit("Database already has data. Re-run with --reset to wipe and reseed.")

    now = timeutil.now()
    pw_hash = hash_password(PASSWORD)  # one hash for every seeded user keeps seeding fast

    async def add_user(name: str, email: str, **extra: Any) -> dict:
        doc = {"name": name, "email": email, "password_hash": pw_hash, "role": "student", "interests": [],
               "preferred_categories": [], "followed_club_ids": [], "created_at": now - timedelta(days=rng.randint(5, 60)),
               "schema_v": SCHEMA_VERSION, **extra}  # fmt: skip
        doc["_id"] = (await db.users.insert_one(doc)).inserted_id
        return doc

    admin = await db.users.find_one({"role": "platform_admin"})

    # ---------------------------------------------------------------- students
    students: list[dict] = []
    for i in range(N_STUDENTS):
        first, last = FIRST[i % len(FIRST)], LAST[(i * 3) % len(LAST)]
        students.append(await add_user(
            f"{first} {last}", slugify_email(first, last, i + 1, domain),
            interests=normalize_terms(rng.sample(INTERESTS, rng.randint(2, 5))),
            preferred_categories=rng.sample(CATEGORIES[:9], rng.randint(1, 3)),
        ))  # fmt: skip

    # ---------------------------------------------------------------- clubs + admins (through the services)
    club_docs: dict[str, dict] = {}
    club_admins: dict[str, list[dict]] = {}
    for idx, (name, cat, desc, verified) in enumerate(CLUBS):
        requester = students[idx]
        club = await clubs_svc.request_club(db, requester["_id"], ClubCreate(name=name, description=desc, category=cat))
        if verified:
            await clubs_svc.verify_club(db, club["_id"], admin["_id"])
            club_admins[name] = []
            for k in range(rng.choice([1, 2])):
                slug = club["slug"].replace("-", "")
                u = await add_user(f"{name} Admin {k + 1}", f"admin.{slug}{k + 1}@{domain}")
                await clubs_svc.add_admin(db, club["_id"], u["_id"])
                club_admins[name].append(await db.users.find_one({"_id": u["_id"]}))
        club_docs[name] = await db.clubs.find_one({"_id": club["_id"]})
    verified_ids = [club_docs[c[0]]["_id"] for c in CLUBS if c[3]]
    for s in students:  # follows
        pick = rng.sample(verified_ids, rng.randint(0, 3))
        await db.users.update_one({"_id": s["_id"]}, {"$set": {"followed_club_ids": pick}})
        s["followed_club_ids"] = pick

    # ---------------------------------------------------------------- events (through the services)
    slots = (["today"] * 3 + ["tomorrow"] * 5 + ["week"] * 12 + ["later"] * 17 + ["past"] * 8
             + ["cancelled"] * 2 + ["pending"] * 3 + ["draft"] * 3 + ["rejected"] * 2)  # fmt: skip
    rng.shuffle(slots)
    not_specified = set(rng.sample(range(len(E)), 8))
    today_ist = timeutil.ist_date(now)

    def ist_at(days: int, hour_min: tuple[int, int] = (9, 19)):
        start, _ = timeutil.ist_day_range(today_ist + timedelta(days=days))
        return start + timedelta(hours=rng.randint(*hour_min), minutes=rng.choice([0, 15, 30, 45]))

    def start_for(slot: str):
        if slot == "today":
            return now + timedelta(minutes=rng.randint(45, 300))
        if slot == "tomorrow":
            return ist_at(1)
        if slot == "week":
            return ist_at(rng.randint(2, 6))
        if slot == "past":
            return now - timedelta(days=rng.randint(1, 13), hours=rng.randint(1, 8))
        if slot in ("later",):
            return ist_at(rng.randint(8, 28))
        return ist_at(rng.randint(3, 25))  # cancelled / pending / draft / rejected: upcoming

    events: list[dict] = []
    closed_left = 4
    pngs = 0
    for i, ((title, liner, club_name, cat, etype, tags), slot) in enumerate(zip(E, slots, strict=True)):
        start = start_for(slot)
        lo, hi = DURATION_H[etype]
        end = start + timedelta(hours=rng.randint(lo, hi), minutes=rng.choice([0, 30]))
        required = rng.random() < (0.9 if etype in ("workshop", "competition", "hackathon", "seminar") else 0.35)
        reg: dict[str, Any] = {"required": required}
        deadline = None
        if required:
            plat = rng.choice(REG_PLATFORM.get(etype, ["google_forms", "website"]))
            reg.update(platform=plat, url=f"https://forms.example.com/{plat}/{i + 1}")
            if slot in ("week", "later") and closed_left:
                deadline, closed_left = now - timedelta(days=1), closed_left - 1  # registration already closed
            elif slot in ("today", "tomorrow", "week") and rng.random() < 0.5:
                d = min(now + timedelta(hours=rng.randint(6, 60)), start - timedelta(minutes=30))
                deadline = d if d > now + timedelta(hours=1) else None  # urgent: within 72h
            elif rng.random() < 0.6:
                d = start - timedelta(days=1)
                deadline = d if d > now else None
        reg["deadline"] = deadline
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
            "contact": {"name": rng.choice(FIRST), "email": f"contact.{club_docs[club_name]['slug']}@{domain}"},
            "details": details_for(etype, title, tags, rng),
        }  # fmt: skip
        owner = rng.choice(club_admins[club_name])
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

    upcoming = [e for e in events if e["slot"] in ("today", "tomorrow", "week", "later")]
    for e in rng.sample([x for x in upcoming if x["slot"] in ("today", "week", "later")], 3):
        await events_svc.set_featured(db, e["id"], True)

    # ---------------------------------------------------------------- engagement
    public = [e for e in events if e["slot"] in ("today", "tomorrow", "week", "later", "past")]
    weights = [
        (0.3 if e["slot"] == "past" else 1.0) / (rank + 1) ** 0.8
        for rank, e in enumerate(rng.sample(public, len(public)))
    ]
    order = rng.sample(public, len(public))  # a random popularity ranking
    docs_by_id = {e["id"]: e for e in public}
    people = students + [u for lst in club_admins.values() for u in lst]

    def rand_ts(e: dict):
        lo, hi = now - timedelta(days=14), min(now, e["start"])
        if hi <= lo + timedelta(hours=1):
            hi = now
        return lo + (hi - lo) * rng.random()

    pairs: set[tuple[ObjectId, ObjectId]] = set()
    saved_pairs: list[tuple[dict, dict]] = []
    attempts = 0
    while len(pairs) < N_SAVES and attempts < N_SAVES * 20:
        attempts += 1
        e = rng.choices(order, weights)[0]
        s = rng.choice(students)
        if (s["_id"], e["id"]) in pairs:
            continue
        saved, created = await saved_svc.save_event(db, s["_id"], e["id"])
        pairs.add((s["_id"], e["id"]))
        ts = rand_ts(e)
        await db.saved_events.update_one({"_id": saved["_id"]}, {"$set": {"created_at": ts}})
        await db.event_interactions.update_one(
            {"event_id": e["id"], "user_id": s["_id"], "type": "save"}, {"$set": {"ts": ts}}
        )
        saved_pairs.append((s, e))

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
        e["id"]
        for e in public
        if (await db.events.find_one({"_id": e["id"]}, {"registration.required": 1}))["registration"]["required"]
    }
    clicked_pairs: set[tuple[ObjectId, ObjectId]] = set()
    for s, e in saved_pairs:  # some saved events were followed through to the registration page
        if e["id"] in reg_required and rng.random() < 0.3:
            log("registration_click", e, s, "registration_clicks")
            clicked_pairs.add((s["_id"], e["id"]))
    reg_pool = [e for e in order if e["id"] in reg_required]
    while sum(1 for i in interactions if i["type"] == "registration_click") < N_CLICKS and reg_pool:
        e = rng.choice(reg_pool)
        log("registration_click", e, rng.choice(students) if rng.random() < 0.8 else None, "registration_clicks")
    await db.event_interactions.insert_many(interactions)
    await db.events.bulk_write(
        [UpdateOne({"_id": eid}, {"$inc": {f"stats.{k}": v for k, v in c.items()}}) for eid, c in counters.items()]
    )
    for uid, eid in clicked_pairs:
        await db.saved_events.update_one(
            {"user_id": uid, "event_id": eid}, {"$set": {"status": "registration_initiated"}}
        )
    assert docs_by_id

    # ---------------------------------------------------------------- community (through the services)
    posts: list[dict] = []
    scopes = ([PostScope(type="global")] * 8
              + [PostScope(type="event", ref_id=str(e["id"])) for e in rng.sample(public, 6)]
              + [PostScope(type="club", ref_id=str(club_docs[c[0]]["_id"])) for c in rng.sample([c for c in CLUBS if c[3]], 6)])  # fmt: skip
    for title, scope in zip(POST_TITLES[:N_POSTS], scopes, strict=True):
        author = rng.choice(people)
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
    sample_student = next(s for s in students if s["interests"])
    return {
        "counts": counts, "events_by_status": by_status, "posters": pngs,
        "credentials": {
            "student": (sample_student["email"], PASSWORD),
            "club_admin": (club_admins["ACM"][0]["email"], PASSWORD),
            "platform_admin": (get_settings().platform_admin_email, get_settings().platform_admin_password),
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
    print("\nNext: uvicorn app.main:app --reload  ->  http://localhost:8000/docs\n")


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
