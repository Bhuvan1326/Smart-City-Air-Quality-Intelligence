"""GIS ward assignment for civic issues.

Provider hierarchy, most-precise first:

1. Real PostGIS point-in-polygon (ST_Contains) against an admin-entered
   app.models.civic_governance.WardBoundary polygon for the given city —
   genuinely spatial, not a distance heuristic. Only the boundary
   currently effective (effective_to is null or in the future) is used.
2. Falls back to app.gis.operations.GISService.point_in_ward, which is
   nearest-ward-centroid distance, not true polygon containment, and
   labeled accordingly.
3. If neither finds anything, returns UNAVAILABLE — never fabricates a
   ward.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from app.gis.operations import GISService
from app.models.civic_issue import WardAssignmentMethod
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass
class WardAssignmentResult:
    ward_id: str | None
    method: WardAssignmentMethod


async def _point_in_ward_boundary(
    session: AsyncSession, *, city: str, latitude: float, longitude: float
) -> str | None:
    today = date.today()
    result = await session.execute(
        text(
            """
            SELECT ward_id
            FROM ward_boundaries
            WHERE city = :city
              AND is_deleted = false
              AND effective_from <= :today
              AND (effective_to IS NULL OR effective_to >= :today)
              AND ST_Contains(
                  geometry,
                  ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)
              )
            ORDER BY effective_from DESC
            LIMIT 1
            """
        ),
        {"city": city, "today": today, "lon": longitude, "lat": latitude},
    )
    row = result.first()
    return row[0] if row else None


async def assign_ward(
    session: AsyncSession, *, city: str, latitude: float, longitude: float
) -> WardAssignmentResult:
    polygon_ward_id = await _point_in_ward_boundary(
        session, city=city, latitude=latitude, longitude=longitude
    )
    if polygon_ward_id is not None:
        return WardAssignmentResult(
            ward_id=polygon_ward_id, method=WardAssignmentMethod.POINT_IN_POLYGON
        )

    gis = GISService(session)
    approximate_ward_id = await gis.point_in_ward(latitude, longitude, city)
    if approximate_ward_id is not None:
        return WardAssignmentResult(
            ward_id=approximate_ward_id,
            method=WardAssignmentMethod.NEAREST_WARD_CENTROID_APPROXIMATE,
        )

    return WardAssignmentResult(ward_id=None, method=WardAssignmentMethod.UNAVAILABLE)
