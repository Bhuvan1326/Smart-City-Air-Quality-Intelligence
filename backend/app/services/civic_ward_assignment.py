"""GIS ward assignment for civic issues.

Reuses app.gis.operations.GISService.point_in_ward rather than
duplicating ward-lookup logic. That method is nearest-ward-centroid
distance, not true PostGIS point-in-polygon containment (no polygon
containment query exists anywhere in this codebase yet), and is only
populated for Pune. This wrapper's only job is to translate that into an
honest WardAssignmentMethod label rather than silently claiming
precision the underlying lookup doesn't have.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.gis.operations import GISService
from app.models.civic_issue import WardAssignmentMethod


@dataclass
class WardAssignmentResult:
    ward_id: str | None
    method: WardAssignmentMethod


async def assign_ward(
    session: AsyncSession, *, city: str, latitude: float, longitude: float
) -> WardAssignmentResult:
    gis = GISService(session)
    ward_id = await gis.point_in_ward(latitude, longitude, city)
    if ward_id is None:
        return WardAssignmentResult(
            ward_id=None, method=WardAssignmentMethod.UNAVAILABLE
        )
    return WardAssignmentResult(
        ward_id=ward_id,
        method=WardAssignmentMethod.NEAREST_WARD_CENTROID_APPROXIMATE,
    )
