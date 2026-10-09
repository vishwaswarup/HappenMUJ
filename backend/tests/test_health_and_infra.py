from app.indexes import INDEXES
from app.validators import VALIDATORS


async def test_health_reports_replica_set(client):
    import httpx

    from app.main import app

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/health")
    assert r.status_code == 200
    assert r.json()["transactions_supported"] is True


async def test_all_indexes_exist(db):
    for coll, models in INDEXES.items():
        info = await db[coll].index_information()
        for m in models:
            assert m.document["name"] in info, f"{coll}.{m.document['name']} missing"


async def test_special_index_options(db):
    ev = await db.events.index_information()
    assert ev["featured_partial"]["partialFilterExpression"] == {"featured.is_featured": True}
    assert ev["events_text"]["weights"]["title"] == 10
    ttl = await db.event_interactions.index_information()
    assert ttl["ts_ttl"]["expireAfterSeconds"] == 90 * 24 * 3600


async def test_validators_applied_and_enforced(db):
    import pytest
    from pymongo.errors import WriteError

    infos = {c["name"]: c for c in await (await db.list_collections()).to_list(None)}
    for name in VALIDATORS:
        opts = infos[name]["options"]
        assert opts["validationLevel"] == "moderate" and opts["validationAction"] == "error"
    with pytest.raises(WriteError):
        await db.clubs.insert_one({"name": "x"})
    # events.details stays open: validator only covers common fields
    assert "details" not in VALIDATORS["events"]["properties"]


async def test_prepare_database_is_idempotent():
    from app.main import prepare_database

    await prepare_database()
    await prepare_database()
