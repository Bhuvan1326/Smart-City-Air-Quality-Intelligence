"""Week 2 (B1): demo users must never be created with a published password."""

import pytest
from sqlalchemy import select

from app.core import seeder
from app.core.config import Settings, settings
from app.core.security import verify_password
from app.models.user import User

STRONG = "local-test-only-pw-9f3a1c"  # test fixture value, not a real secret


def _static_password_literals():
    import pathlib
    import re

    src = pathlib.Path(seeder.__file__).read_text()
    return re.findall(r"[A-Z][a-z]+@123", src)


def test_no_static_demo_password_literals_in_seeder_source():
    assert _static_password_literals() == []


def test_empty_seed_flag_from_compose_is_auto():
    s = Settings(
        SEED_DEMO_USERS="",
        ENVIRONMENT="production",
        SECRET_KEY="a-real-unique-secret-key-0123456789abcdef",
    )
    assert s.SEED_DEMO_USERS is None and s.should_seed_demo_users is False


@pytest.mark.parametrize("pw", ["", "short", "a" * 11])
def test_missing_or_short_password_means_no_seeding(monkeypatch, pw):
    monkeypatch.setattr(settings, "DEMO_USER_PASSWORD", pw)
    assert seeder.demo_seeding_password() is None


def test_valid_password_is_used_and_not_logged(monkeypatch, capsys):
    monkeypatch.setattr(settings, "DEMO_USER_PASSWORD", STRONG)
    assert seeder.demo_seeding_password() == STRONG
    out = capsys.readouterr()
    assert STRONG not in out.out + out.err


def test_built_users_use_supplied_password_and_known_roles():
    users = seeder.build_demo_users(STRONG)
    assert {u.email for u in users} == {e for e, *_ in seeder.DEMO_USER_SPECS}
    assert len(users) == 4
    assert all(verify_password(STRONG, u.hashed_password) for u in users)
    assert not any(verify_password("Admin@123", u.hashed_password) for u in users)
    assert {u.role.name for u in users} == {
        "CITY_ADMINISTRATOR",
        "POLLUTION_CONTROL_OFFICER",
        "FIELD_INSPECTOR",
        "CITIZEN",
    }


@pytest.mark.asyncio
async def test_seed_users_skips_without_password(monkeypatch, db_session):
    monkeypatch.setattr(settings, "DEMO_USER_PASSWORD", "")
    await seeder._seed_users(db_session)
    rows = (await db_session.execute(select(User))).scalars().all()
    assert rows == []


@pytest.mark.asyncio
async def test_seed_users_with_password_creates_accounts_that_do_not_accept_old_default(
    monkeypatch, db_session
):
    monkeypatch.setattr(settings, "DEMO_USER_PASSWORD", STRONG)
    await seeder._seed_users(db_session)
    rows = (await db_session.execute(select(User))).scalars().all()
    assert len(rows) == 4
    assert not any(verify_password("Admin@123", u.hashed_password) for u in rows)
    assert all(verify_password(STRONG, u.hashed_password) for u in rows)


# ---------------- S8: docs exposure and health error text in production --------
@pytest.mark.parametrize(
    "env,flag,expected",
    [
        ("development", None, True),
        ("production", None, False),
        ("production", True, True),
        ("development", False, False),
        ("production", "", False),  # compose passes an empty string when unset
    ],
)
def test_api_docs_policy(env, flag, expected):
    s = Settings(
        ENVIRONMENT=env,
        ENABLE_API_DOCS=flag,
        SECRET_KEY="a-real-unique-secret-key-0123456789abcdef",
    )
    assert s.api_docs_enabled is expected


def test_health_error_label_never_echoes_exception_text_in_production(monkeypatch):
    from app import main

    err = RuntimeError("postgresql://user:secret@db.internal:5432/x refused")
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    assert main.health_error_label(err) == "error"
    monkeypatch.setattr(settings, "ENVIRONMENT", "development")
    assert "refused" in main.health_error_label(err)
