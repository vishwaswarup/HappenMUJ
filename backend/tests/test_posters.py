import io

from PIL import Image


def _img(fmt: str, size=(20, 20)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, (200, 30, 30)).save(buf, fmt)
    return buf.getvalue()


async def _setup(client, make_club, make_event):
    club, owner = await make_club("Club A")
    ev = await make_event(club["id"], owner)
    return club, owner, ev


async def _upload(client, owner, eid, data: bytes, ctype: str, name="poster.png"):
    return await client.post(f"/events/{eid}/poster", headers=owner.headers, files={"file": (name, data, ctype)})


async def test_upload_and_stream_poster(client, make_club, make_event, db):
    _, owner, ev = await _setup(client, make_club, make_event)
    data = _img("PNG")
    r = await _upload(client, owner, ev["id"], data, "image/png")
    assert r.status_code == 200, r.text
    url = r.json()["poster_url"]
    assert url.startswith("/api/v1/files/")
    # it lives in GridFS
    assert await db["fs.files"].count_documents({}) == 1
    f = await client.get(url.removeprefix("/api/v1"))
    assert f.status_code == 200 and f.content == data
    assert f.headers["content-type"] == "image/png"
    assert "immutable" in f.headers["cache-control"] and f.headers["etag"]
    cached = await client.get(url.removeprefix("/api/v1"), headers={"If-None-Match": f.headers["etag"]})
    assert cached.status_code == 304


async def test_replacing_poster_removes_old_file(client, make_club, make_event, db):
    _, owner, ev = await _setup(client, make_club, make_event)
    r1 = await _upload(client, owner, ev["id"], _img("PNG"), "image/png")
    r2 = await _upload(client, owner, ev["id"], _img("JPEG"), "image/jpeg", "p.jpg")
    assert r1.json()["poster_url"] != r2.json()["poster_url"]
    assert await db["fs.files"].count_documents({}) == 1
    assert (await client.get(r1.json()["poster_url"].removeprefix("/api/v1"))).status_code == 404
    assert (await client.get(r2.json()["poster_url"].removeprefix("/api/v1"))).headers["content-type"] == "image/jpeg"


async def test_webp_accepted(client, make_club, make_event):
    _, owner, ev = await _setup(client, make_club, make_event)
    assert (await _upload(client, owner, ev["id"], _img("WEBP"), "image/webp", "p.webp")).status_code == 200


async def test_wrong_type_rejected(client, make_club, make_event):
    _, owner, ev = await _setup(client, make_club, make_event)
    r = await _upload(client, owner, ev["id"], _img("GIF"), "image/gif", "p.gif")
    assert r.status_code == 415
    r = await _upload(client, owner, ev["id"], b"%PDF-1.4 ...", "application/pdf", "p.pdf")
    assert r.status_code == 415


async def test_spoofed_content_rejected(client, make_club, make_event, db):
    _, owner, ev = await _setup(client, make_club, make_event)
    # a script with an image name and image header
    r = await _upload(client, owner, ev["id"], b"<script>alert(1)</script>", "image/png", "evil.png")
    assert r.status_code == 415
    # real JPEG labelled as PNG
    r = await _upload(client, owner, ev["id"], _img("JPEG"), "image/png", "x.png")
    assert r.status_code == 415
    assert await db["fs.files"].count_documents({}) == 0


async def test_too_large_rejected(client, make_club, make_event):
    _, owner, ev = await _setup(client, make_club, make_event)
    big = b"\x89PNG\r\n\x1a\n" + b"0" * (5 * 1024 * 1024)
    r = await _upload(client, owner, ev["id"], big, "image/png")
    assert r.status_code == 413
    assert r.json()["error"]["code"] == "file_too_large"


async def test_empty_file_rejected(client, make_club, make_event):
    _, owner, ev = await _setup(client, make_club, make_event)
    assert (await _upload(client, owner, ev["id"], b"", "image/png")).status_code == 422


async def test_poster_authorization(client, make_club, make_event, make_user):
    club_a, owner_a, ev = await _setup(client, make_club, make_event)
    _, owner_b = await make_club("Club B")
    student = await make_user()
    for who in (owner_b, student):
        assert (await _upload(client, who, ev["id"], _img("PNG"), "image/png")).status_code == 403
    assert (
        await client.post(f"/events/{ev['id']}/poster", files={"file": ("a.png", _img("PNG"), "image/png")})
    ).status_code == 401


async def test_deleting_draft_removes_poster(client, make_club, make_event, db):
    _, owner, ev = await _setup(client, make_club, make_event)
    await _upload(client, owner, ev["id"], _img("PNG"), "image/png")
    assert await db["fs.files"].count_documents({}) == 1
    assert (await client.delete(f"/events/{ev['id']}", headers=owner.headers)).status_code == 204
    assert await db["fs.files"].count_documents({}) == 0


async def test_unknown_file_404(client):
    assert (await client.get("/files/000000000000000000000000")).status_code == 404
