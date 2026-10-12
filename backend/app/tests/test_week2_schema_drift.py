"""Week 2 (A3): the drift checker must detect a deliberate ORM/migration mismatch."""

import os

import pytest
import sqlalchemy as sa

from app.tools import schema_drift as sd


def _db(meta: sa.MetaData):
    engine = sa.create_engine("sqlite://")
    meta.create_all(engine)
    return engine


def _meta(extra_col=False, extra_index=False, extra_table=False):
    m = sa.MetaData()
    t = sa.Table(
        "things",
        m,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(20), nullable=False),
        *([sa.Column("color", sa.String(10))] if extra_col else []),
    )
    if extra_index:
        sa.Index("ix_things_name", t.c.name)
    if extra_table:
        sa.Table("gadgets", m, sa.Column("id", sa.Integer, primary_key=True))
    return m


def test_aligned_schema_has_no_drift():
    engine = _db(_meta())
    with engine.connect() as c:
        assert sd.signatures_for(c, _meta()) == []


def test_deliberate_mismatch_is_detected_with_stable_signatures():
    engine = _db(_meta())  # "migrated" database
    with engine.connect() as c:
        sigs = sd.signatures_for(
            c, _meta(extra_col=True, extra_index=True, extra_table=True)
        )
    assert "add_column things.color" in sigs
    assert "add_index ix_things_name" in sigs
    assert "add_table gadgets" in sigs


def test_ignored_objects_are_not_reported():
    m = sa.MetaData()
    engine = sa.create_engine("sqlite://")
    with engine.begin() as c:
        c.execute(sa.text("CREATE TABLE spatial_ref_sys (srid INTEGER PRIMARY KEY)"))
        c.execute(sa.text("CREATE TABLE t (id INTEGER PRIMARY KEY, ts TEXT)"))
        c.execute(sa.text("CREATE INDEX t_ts_timestamp_idx ON t (ts)"))
    with engine.connect() as c:
        sigs = sd.signatures_for(c, m)
    assert not any("spatial_ref_sys" in s or "timestamp_idx" in s for s in sigs)
    assert "remove_table t" in sigs


def test_baseline_comparison_reports_new_and_stale():
    new, stale = sd.diff_against_baseline(["a", "b", "c"], ["b", "c", "d"])
    assert new == ["a"] and stale == ["d"]
    assert sd.diff_against_baseline(["x"], ["x"]) == ([], [])


@pytest.mark.skipif(
    not os.environ.get("MIGRATED_DATABASE_URL"),
    reason="needs a database with `alembic upgrade head` applied (set MIGRATED_DATABASE_URL)",
)
@pytest.mark.asyncio
async def test_real_migrated_schema_matches_committed_baseline():
    import json

    current = await sd._current_signatures(os.environ["MIGRATED_DATABASE_URL"])
    baseline = json.loads(sd.BASELINE_PATH.read_text())["signatures"]
    new, stale = sd.diff_against_baseline(current, baseline)
    assert not new, f"new migration-vs-ORM drift: {new[:10]}"
    assert not stale, f"stale baseline entries (remove them): {stale[:10]}"
