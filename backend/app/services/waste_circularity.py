"""Smart Waste & Circularity Intelligence.

There is no universal free real-time municipal-waste API (confirmed by
inspecting available providers — this mirrors the conclusion already
reached for energy demand in app/services/energy_provider.py). Municipal
waste-generation/collection/recycling/composting/landfill figures are
instead admin-entered per ward in app.models.demographics.WardDemographics
(waste_* fields), following the exact same integrity rule already
established there for population and green-cover data: no default is
seeded, an authoritative source is cited in source_note, and a metric
that hasn't been entered is EXCLUDED from the score rather than assumed
to be zero or any other value. waste_data_as_of records how current the
underlying figures are — periodic administrative reports are never
labeled "live" or given a sensor-style minute-scale freshness.

This module computes recovery rate, landfill dependency, and an overall
circularity score from whatever subset of those fields is on file. If
nothing is on file, it returns exactly what the platform's data-
truthfulness principle requires: "Unavailable" with the reason
"Insufficient verified waste-flow data" — never a fabricated score built
from arbitrary defaults.

No "reuse rate" is computed anywhere in this module: WardDemographics has
no field distinguishing reuse from recycling, and inventing a proxy for
data that was never collected would violate the same principle.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

METHODOLOGY = (
    "Recovery Rate = recycling_pct + composting_pct (each only counted if "
    "on file; capped at 100%). Landfill Dependency = landfill_pct, reported "
    "as-is when on file. Circularity Score = 0.6 x Recovery Rate + 0.4 x "
    "Collection Efficiency, computed ONLY when both a recovery-rate "
    "component (recycling and/or composting) and collection efficiency are "
    "on file for the ward — otherwise the score is reported Unavailable. "
    "No 'Reuse Rate' is computed: this platform has no data source "
    "distinguishing reuse from recycling."
)

_MUNICIPAL_DATA_STALE_AFTER_DAYS = 400  # a periodic (roughly annual) report


@dataclass
class CircularityScore:
    ward_id: str
    waste_generation_tons_per_day: float | None
    collection_efficiency_pct: float | None
    recycling_pct: float | None
    composting_pct: float | None
    landfill_pct: float | None
    recovery_rate_pct: float | None
    recovery_rate_includes_recycling: bool
    recovery_rate_includes_composting: bool
    landfill_dependency_pct: float | None
    circularity_score: float | None
    circularity_unavailable_reason: str | None
    data_as_of: date | None
    freshness_label: str
    is_data_configured: bool
    missing_fields: list[str]
    methodology: str = field(default=METHODOLOGY)


def _freshness_label(data_as_of: date | None, today: date) -> str:
    if data_as_of is None:
        return "unavailable"
    age_days = (today - data_as_of).days
    if age_days > _MUNICIPAL_DATA_STALE_AFTER_DAYS:
        return "latest_available_possibly_outdated"
    return "latest_available"


def score_circularity(
    *,
    ward_id: str,
    today: date,
    waste_generation_tons_per_day: float | None = None,
    collection_efficiency_pct: float | None = None,
    recycling_pct: float | None = None,
    composting_pct: float | None = None,
    landfill_pct: float | None = None,
    data_as_of: date | None = None,
) -> CircularityScore:
    missing_fields: list[str] = []
    if waste_generation_tons_per_day is None:
        missing_fields.append("waste_generation_tons_per_day")
    if collection_efficiency_pct is None:
        missing_fields.append("collection_efficiency_pct")
    if recycling_pct is None:
        missing_fields.append("recycling_pct")
    if composting_pct is None:
        missing_fields.append("composting_pct")
    if landfill_pct is None:
        missing_fields.append("landfill_pct")

    is_data_configured = len(missing_fields) < 5  # at least one real figure on file

    recovery_components = [v for v in (recycling_pct, composting_pct) if v is not None]
    recovery_rate_pct = (
        min(sum(recovery_components), 100.0) if recovery_components else None
    )

    circularity_score: float | None = None
    circularity_unavailable_reason: str | None = None
    if recovery_rate_pct is not None and collection_efficiency_pct is not None:
        circularity_score = round(
            0.6 * recovery_rate_pct + 0.4 * collection_efficiency_pct, 1
        )
    else:
        circularity_unavailable_reason = "Insufficient verified waste-flow data"

    return CircularityScore(
        ward_id=ward_id,
        waste_generation_tons_per_day=waste_generation_tons_per_day,
        collection_efficiency_pct=collection_efficiency_pct,
        recycling_pct=recycling_pct,
        composting_pct=composting_pct,
        landfill_pct=landfill_pct,
        recovery_rate_pct=recovery_rate_pct,
        recovery_rate_includes_recycling=recycling_pct is not None,
        recovery_rate_includes_composting=composting_pct is not None,
        landfill_dependency_pct=landfill_pct,
        circularity_score=circularity_score,
        circularity_unavailable_reason=circularity_unavailable_reason,
        data_as_of=data_as_of,
        freshness_label=_freshness_label(data_as_of, today),
        is_data_configured=is_data_configured,
        missing_fields=missing_fields,
    )
