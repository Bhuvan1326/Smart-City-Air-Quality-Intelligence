"""Schemas for the City Sustainability Score endpoint.

Field names and shapes deliberately match the `SustainabilityScore` /
`SustainabilityComponent` TypeScript interfaces already declared in
frontend/lib/api/services.ts, which were written ahead of this backend
endpoint as the intended contract.
"""

from datetime import datetime

from app.schemas.base import BaseSchema


class SustainabilityComponentResponse(BaseSchema):
    name: str
    score: float | None
    classification: str
    note: str


class SustainabilityScoreResponse(BaseSchema):
    city: str
    overall_score: float | None
    indicators_available: int
    indicators_total: int
    components: list[SustainabilityComponentResponse]
    methodology: str
    generated_at: datetime
