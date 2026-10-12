"""Migration-vs-ORM schema drift check with a committed baseline (Week 2, A3).

Compares the ORM metadata (app.core.database.Base) with a database that has had
`alembic upgrade head` applied, using Alembic's autogenerate comparison, and
reduces every difference to a stable signature, e.g.
    "add_column anomaly_events.pollutant"
    "remove_index ix_stations_city"
CI fails when:
  * a signature appears that is NOT in schema_drift_baseline.json (new drift), or
  * a baseline signature no longer occurs (stale: remove it / fix was made).
Pre-existing drift is recorded in the baseline rather than hidden; it is a
cleanup backlog item, not an accepted state.

    python -m app.tools.schema_drift --database-url postgresql+asyncpg://...
    python -m app.tools.schema_drift --database-url ... --write-baseline
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from pathlib import Path

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import MetaData
from sqlalchemy.engine import Connection

BASELINE_PATH = Path(__file__).resolve().parents[2] / "schema_drift_baseline.json"

# Objects that are not part of the application schema.
IGNORED_TABLES = {"spatial_ref_sys", "alembic_version"}
# Indexes TimescaleDB creates automatically on hypertable time columns; they
# exist only in Timescale-enabled databases and have no ORM counterpart.
IGNORED_INDEX_PATTERN = re.compile(r".*_(timestamp|time|observed_at)_idx$")


def _flatten(diffs):
    for d in diffs:
        if isinstance(d, list):
            yield from _flatten(d)
        else:
            yield d


def signature(diff) -> str | None:
    op = diff[0]
    if op in ("add_table", "remove_table"):
        name = diff[1].name
        return None if name in IGNORED_TABLES else f"{op} {name}"
    if op in ("add_column", "remove_column"):
        table, col = diff[2], diff[3].name
        return None if table in IGNORED_TABLES else f"{op} {table}.{col}"
    if op in ("add_index", "remove_index"):
        idx = diff[1]
        if idx.table.name in IGNORED_TABLES or IGNORED_INDEX_PATTERN.match(
            idx.name or ""
        ):
            return None
        return f"{op} {idx.name}"
    if op in ("add_constraint", "remove_constraint"):
        c = diff[1]
        cols = ",".join(
            sorted(getattr(col, "name", str(col)) for col in getattr(c, "columns", []))
        )
        table = getattr(getattr(c, "table", None), "name", "?")
        return f"{op} {table}({cols}) {type(c).__name__}"
    if op.startswith("modify_"):
        table, col = diff[2], diff[3]
        return None if table in IGNORED_TABLES else f"{op} {table}.{col}"
    return f"{op} {diff[1:]!s}"[:200]


def signatures_for(connection: Connection, metadata: MetaData) -> list[str]:
    ctx = MigrationContext.configure(
        connection,
        opts={"compare_type": False, "compare_server_default": False},
    )
    sigs = {s for d in _flatten(compare_metadata(ctx, metadata)) if (s := signature(d))}
    return sorted(sigs)


def diff_against_baseline(current: list[str], baseline: list[str]):
    cur, base = set(current), set(baseline)
    return sorted(cur - base), sorted(base - cur)  # (new drift, stale baseline)


async def _current_signatures(database_url: str) -> list[str]:
    from sqlalchemy.ext.asyncio import create_async_engine

    import app.models  # noqa: F401  (register all models)
    from app.core.database import Base

    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as conn:
            return await conn.run_sync(lambda sc: signatures_for(sc, Base.metadata))
    finally:
        await engine.dispose()


def main() -> int:  # pragma: no cover - thin CLI
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--database-url", required=True)
    p.add_argument("--baseline", type=Path, default=BASELINE_PATH)
    p.add_argument("--write-baseline", action="store_true")
    a = p.parse_args()
    current = asyncio.run(_current_signatures(a.database_url))
    if a.write_baseline:
        a.baseline.write_text(json.dumps({"signatures": current}, indent=1) + "\n")
        print(f"baseline written: {len(current)} signatures -> {a.baseline}")
        return 0
    baseline = (
        json.loads(a.baseline.read_text())["signatures"] if a.baseline.exists() else []
    )
    new, stale = diff_against_baseline(current, baseline)
    print(
        f"schema drift: current={len(current)} baseline={len(baseline)} new={len(new)} stale={len(stale)}"
    )
    for s in new[:50]:
        print("  NEW DRIFT  ", s)
    for s in stale[:50]:
        print("  STALE BASELINE (fixed? remove it)", s)
    return 1 if new or stale else 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
