"""Week 2 (B3): evidence media requires auth/ownership or a valid signed link."""

import time
import uuid

import pytest
import pytest_asyncio

from app.core.config import settings
from app.core.security import hash_password
from app.models.user import User, UserRole
from app.services import media_access

pytestmark = pytest.mark.integration
PW = "Passw0rd!123"
JPEG = b"\xff\xd8\xff\xe0" + b"0" * 64  # tiny fake jpeg payload (test fixture)


async def _user(db, client, email, role):
    db.add(
        User(
            email=email,
            hashed_password=hash_password(PW),
            full_name="T " + role.value,
            role=role,
            city="Pune",
            is_active=True,
        )
    )
    await db.commit()
    r = await client.post("/api/v1/auth/login", json={"email": email, "password": PW})
    return {"Authorization": f"Bearer {r.json()['data']['access_token']}"}


@pytest.fixture(autouse=True)
def media_root(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "MEDIA_ROOT", str(tmp_path))
    return tmp_path


@pytest_asyncio.fixture
async def world(db_session, client, media_root):
    h = {
        "owner": await _user(db_session, client, "own@t.in", UserRole.CITIZEN),
        "other": await _user(db_session, client, "oth@t.in", UserRole.CITIZEN),
        "inspector": await _user(
            db_session, client, "ins@t.in", UserRole.FIELD_INSPECTOR
        ),
    }
    created = await client.post(
        "/api/v1/civic/issues",
        json={
            "city": "Pune",
            "latitude": 18.52,
            "longitude": 73.85,
            "issue_type": "garbage",
        },
        headers=h["owner"],
    )
    assert created.status_code == 201, created.text
    issue_id = created.json()["data"]["id"]
    d = media_root / "evidence" / str(issue_id)
    d.mkdir(parents=True)
    (d / "a.jpg").write_bytes(JPEG)
    orphan = media_root / "evidence" / str(uuid.uuid4())  # e.g. enforcement action
    orphan.mkdir(parents=True)
    (orphan / "b.jpg").write_bytes(JPEG)
    return {
        "h": h,
        "issue_path": f"/media/evidence/{issue_id}/a.jpg",
        "orphan_path": f"/media/evidence/{orphan.name}/b.jpg",
    }


@pytest.mark.asyncio
async def test_unauthenticated_is_401(client, world):
    assert (await client.get(world["issue_path"])).status_code == 401


@pytest.mark.asyncio
async def test_owner_and_staff_can_read_non_owner_cannot(client, world):
    p, h = world["issue_path"], world["h"]
    r = await client.get(p, headers=h["owner"])
    assert r.status_code == 200 and r.content == JPEG
    assert r.headers["cache-control"] == "private, no-store"
    assert (await client.get(p, headers=h["inspector"])).status_code == 200
    assert (await client.get(p, headers=h["other"])).status_code == 404


@pytest.mark.asyncio
async def test_enforcement_style_evidence_is_staff_only(client, world):
    p, h = world["orphan_path"], world["h"]
    assert (await client.get(p, headers=h["owner"])).status_code == 404
    assert (await client.get(p, headers=h["inspector"])).status_code == 200


@pytest.mark.asyncio
async def test_path_traversal_and_bad_shapes_are_404(client, world):
    h = world["h"]["inspector"]
    for bad in (
        "/media/evidence/../../etc/passwd",
        "/media/evidence/%2e%2e/%2e%2e/x.jpg",
        "/media/other/x/y.jpg",
        "/media/evidence/a/b/c.jpg",
    ):
        r = await client.get(bad, headers=h)
        assert r.status_code in (404, 400), bad


@pytest.mark.asyncio
async def test_signed_link_lifecycle(client, world):
    p, h = world["issue_path"], world["h"]
    # Minting requires authorization on the file.
    assert (
        await client.post(
            "/api/v1/media/signed-url", json={"path": p}, headers=h["other"]
        )
    ).status_code == 404
    r = await client.post(
        "/api/v1/media/signed-url", json={"path": p}, headers=h["owner"]
    )
    assert r.status_code == 200
    url = r.json()["data"]["url"]
    # No Authorization header needed for the signed link.
    assert (await client.get(url)).status_code == 200
    # Tampered signature / different file / expired are rejected.
    assert (await client.get(url[:-4] + "0000")).status_code == 403
    rel = p[len("/media/") :]
    exp, sig = media_access.sign(rel)
    other = world["orphan_path"]
    assert (await client.get(f"{other}?exp={exp}&sig={sig}")).status_code == 403
    exp_old, sig_old = media_access.sign(rel, ttl_seconds=-10)
    assert (await client.get(f"{p}?exp={exp_old}&sig={sig_old}")).status_code == 403


def test_signature_expiry_logic():
    now = time.time()
    exp, sig = media_access.sign("evidence/x/y.jpg", ttl_seconds=60, now=now)
    assert media_access.verify("evidence/x/y.jpg", exp, sig, now=now + 59)
    assert not media_access.verify("evidence/x/y.jpg", exp, sig, now=now + 61)
    assert not media_access.verify("evidence/x/z.jpg", exp, sig, now=now)
