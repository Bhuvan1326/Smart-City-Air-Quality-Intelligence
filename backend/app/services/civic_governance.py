"""Municipality / ward-office / department / representative lookups.

Municipality and WardOffice answer "which operational body is responsible
here" — reused together with app.services.civic_sla's department mapping
as the "RESPONSIBLE CIVIC AUTHORITY" for a civic issue.

WardRepresentative answers a DIFFERENT question — "who is the elected
representative for this ward" — and is surfaced separately, explicitly
labeled, and NEVER treated as an operational authority. A civic issue
response should show both (when data exists) but must never imply the
representative personally performs cleanup work, and must never
attribute an overdue/unresolved issue to them by name.

All lookups return None when no admin-entered record exists — never a
fabricated municipality, office, or representative.
"""

from __future__ import annotations

from app.models.civic_governance import (Municipality, WardOffice,
                                         WardRepresentative)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


async def get_municipality(session: AsyncSession, city: str) -> Municipality | None:
    result = await session.execute(
        select(Municipality).where(
            Municipality.city == city, Municipality.is_deleted.is_(False)
        )
    )
    return result.scalar_one_or_none()


async def get_ward_office(
    session: AsyncSession, city: str, ward_id: str
) -> WardOffice | None:
    result = await session.execute(
        select(WardOffice).where(
            WardOffice.city == city,
            WardOffice.ward_id == ward_id,
            WardOffice.is_deleted.is_(False),
        )
    )
    return result.scalar_one_or_none()


async def get_ward_representative(
    session: AsyncSession, city: str, ward_id: str
) -> WardRepresentative | None:
    """Returns the current representative (term_end null or in the
    future) if one is on file — never fabricated.
    """
    from datetime import date

    result = await session.execute(
        select(WardRepresentative).where(
            WardRepresentative.city == city,
            WardRepresentative.ward_id == ward_id,
            WardRepresentative.is_deleted.is_(False),
        )
    )
    candidates = result.scalars().all()
    today = date.today()
    current = [r for r in candidates if r.term_end is None or r.term_end >= today]
    if current:
        return max(current, key=lambda r: r.term_start or date.min)
    return None
