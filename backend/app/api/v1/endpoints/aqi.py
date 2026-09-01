from datetime import datetime, timedelta, timezone
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_db
from app.core.redis_client import cache_get, cache_set
from app.repositories.aqi import AQIReadingRepository, MonitoringStationRepository
from app.schemas.aqi import (
    AQIReadingResponse,
    CompareRoutesRequest,
    HealthRiskResponse,
    IndiaAQIObservationResponse,
    LiveAQIResponse,
    LocationRecommendationResponse,
    PollutantRiskResponse,
    RouteAnalysisResponse,
    RouteComparisonResponse,
    RouteExposureResultResponse,
    RouteSampleResponse,
    StationResponse,
    TrafficPeriodStatsResponse,
    TrafficPollutionResponse,
    get_aqi_category,
    resolve_data_source,
)
from app.schemas.base import APIResponse, PaginatedResponse
from app.services.aqi_providers import pune_stations
from app.services.data_freshness import classify_freshness
from app.services.health_risk import assess_health_risk
from app.services.india_aqi import (
    IndiaAQIFilters,
    InvalidIndiaAQIFilterError,
    get_india_aqi_observations,
    get_india_states,
)
from app.services.location_recommendation import rank_locations
from app.services.route_analysis import analyze_route
from app.services.route_comparison import RouteCandidate, Waypoint, compare_routes
from app.services.traffic_pollution import analyze_traffic_pollution

router = APIRouter(prefix="/aqi", tags=["AQI Monitoring"])


@router.get(
    "/india", response_model=APIResponse[PaginatedResponse[IndiaAQIObservationResponse]]
)
async def get_india_aqi(
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_db)],
    state: str | None = Query(None, description="Indian state, e.g. Maharashtra"),
    city: str | None = Query(None, description="City name, e.g. Pune"),
    category: str | None = Query(
        None,
        description="AQI category, e.g. 'Unhealthy' (matches existing classification)",
    ),
    source: str | None = Query(
        None,
        description="Data source: 'openaq' (real) or 'synthetic' (statistical fallback)",
    ),
    min_lat: float | None = Query(None, ge=-90, le=90),
    min_lon: float | None = Query(None, ge=-180, le=180),
    max_lat: float | None = Query(None, ge=-90, le=90),
    max_lon: float | None = Query(None, ge=-180, le=180),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
) -> APIResponse[PaginatedResponse[IndiaAQIObservationResponse]]:
    """India AQI Intelligence — India-wide monitoring station observations.

    Reuses the existing monitoring-station / AQI-reading data and
    repositories (see app/services/india_aqi.py) — no new data source, no
    fabricated stations or readings. Returns exactly the India-tagged
    stations already in the database (the existing Pune/Mumbai fixtures,
    plus any stations discovered by
    app.workers.tasks.aqi_ingestion.discover_and_ingest_india_locations).

    Every observation preserves its own AQI methodology/provenance
    (`aqi_method`, `data_source`, `quality_flag`) rather than presenting
    all readings as equivalent.
    """
    try:
        filters = IndiaAQIFilters(
            state=state,
            city=city,
            category=category,
            source=source,
            min_lat=min_lat,
            min_lon=min_lon,
            max_lat=max_lat,
            max_lon=max_lon,
            page=page,
            page_size=page_size,
        )
    except InvalidIndiaAQIFilterError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)
        ) from e

    cache_key = (
        "india_aqi:"
        f"state={state}:city={city}:category={category}:source={source}:"
        f"bbox={min_lat},{min_lon},{max_lat},{max_lon}:"
        f"page={page}:page_size={page_size}"
    )
    cached = await cache_get(cache_key)
    if cached:
        return APIResponse(data=cached)

    observations, total = await get_india_aqi_observations(session, filters)

    response = PaginatedResponse.create(observations, total, page, page_size)
    await cache_set(cache_key, response.model_dump(mode="json"), ttl=300)
    return APIResponse(data=response)


@router.get("/india/states", response_model=APIResponse[list[str]])
async def get_india_states_list(
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> APIResponse[list[str]]:
    """Distinct Indian states actually present in the database, for the
    India AQI state filter dropdown. Deliberately NOT a static list of
    India's 28 states/8 union territories — see
    app/services/india_aqi.get_india_states — so the frontend never shows
    a filter option for a state with no real data behind it.
    """
    cache_key = "india_aqi:states"
    cached = await cache_get(cache_key)
    if cached is not None:
        return APIResponse(data=cached)

    states = await get_india_states(session)
    await cache_set(cache_key, states, ttl=300)
    return APIResponse(data=states)


@router.get("/stations", response_model=APIResponse[PaginatedResponse[StationResponse]])
async def list_stations(
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_db)],
    city: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
) -> APIResponse[PaginatedResponse[StationResponse]]:
    repo = MonitoringStationRepository(session)
    filters = {}
    if city:
        filters["city"] = city
    stations, total = await repo.get_all(
        skip=(page - 1) * page_size,
        limit=page_size,
        filters=filters,
    )
    items = [StationResponse.model_validate(s) for s in stations]
    return APIResponse(data=PaginatedResponse.create(items, total, page, page_size))


def _build_live_aqi_response(station, reading) -> LiveAQIResponse:
    category, health_msg = None, None
    if reading is not None and reading.aqi is not None:
        category, health_msg = get_aqi_category(reading.aqi)
    data_source = (
        resolve_data_source(reading.quality_flag) if reading else "unavailable"
    )
    freshness = classify_freshness(
        reading.timestamp if reading else None,
        is_synthetic=(reading is not None and reading.quality_flag == "synthetic"),
    ).value
    return LiveAQIResponse(
        station=StationResponse.model_validate(station),
        station_code=station.station_code,
        station_name=station.name,
        provider=station.operator,
        reading=AQIReadingResponse.model_validate(reading) if reading else None,
        aqi_category=category,
        health_message=health_msg,
        trend=None,
        data_source=data_source,
        freshness=freshness,
        unresolved=False,
    )


async def _get_pune_live_aqi(session: AsyncSession) -> list[LiveAQIResponse]:
    """The six authoritative real-time Pune stations, always returned in
    the same fixed order, always exactly six entries — including a clear
    "unresolved"/"unavailable" placeholder entry (no fabricated station,
    no fabricated reading) for any station not yet matched to a real
    OpenAQ location or currently reporting no observation. See
    app.services.aqi_providers.pune_stations.REQUIRED_STATIONS and
    app.workers.tasks.aqi_ingestion.fetch_live_aqi_pune_stations (the
    Celery task that actually ingests these every 60 seconds).
    """
    station_repo = MonitoringStationRepository(session)
    reading_repo = AQIReadingRepository(session)

    codes = [spec.station_code for spec in pune_stations.REQUIRED_STATIONS]
    stations_by_code = await station_repo.get_by_station_codes(codes)

    results: list[LiveAQIResponse] = []
    for spec in pune_stations.REQUIRED_STATIONS:
        station = stations_by_code.get(spec.station_code)
        if station is None:
            # Never matched to a real OpenAQ location yet — no fabricated
            # coordinates, no fabricated reading. The frontend shows
            # "Real-time observation unavailable" for this card.
            results.append(
                LiveAQIResponse(
                    station=None,
                    station_code=spec.station_code,
                    station_name=spec.display_name,
                    provider=spec.provider,
                    reading=None,
                    data_source="unavailable",
                    freshness="unavailable",
                    unresolved=True,
                )
            )
            continue

        reading = await reading_repo.get_latest_by_station(station.id)
        item = _build_live_aqi_response(station, reading)
        if reading is not None:
            item.trend = await reading_repo.get_station_trend(station.id, reading.aqi)
        results.append(item)

    return results


@router.get("/live", response_model=APIResponse[list[LiveAQIResponse]])
async def get_live_aqi(
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_db)],
    city: str | None = Query(
        None,
        description="City name. Required unless scope=all (India-wide view across every city with monitoring stations).",
    ),
    scope: str = Query(
        "city",
        description="'city' (default, requires `city`) or 'all' for stations across every city.",
    ),
) -> APIResponse[list[LiveAQIResponse]]:
    is_all_scope = scope == "all"
    if not is_all_scope and not city:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="city is required unless scope=all",
        )

    # Pune's Live AQI is now backed exclusively by the six real,
    # OpenAQ-matched stations (see requirement 2/7) — never the legacy
    # ward CAAQMS fixtures, and never scope=all's more general station
    # list. Cached for a much shorter TTL than the general case since
    # ingestion refreshes this data every 60 seconds (requirement 23).
    if not is_all_scope and city and city.strip().lower() == "pune":
        cache_key = "live_aqi:pune_six_stations"
        cached = await cache_get(cache_key)
        if cached:
            return APIResponse(data=cached)

        results = await _get_pune_live_aqi(session)
        serialized = [r.model_dump(mode="json") for r in results]
        await cache_set(cache_key, serialized, ttl=45)
        return APIResponse(data=results)

    cache_key = "live_aqi:__all__" if is_all_scope else f"live_aqi:{city}"
    cached = await cache_get(cache_key)
    if cached:
        return APIResponse(data=cached)

    station_repo = MonitoringStationRepository(session)
    reading_repo = AQIReadingRepository(session)
    stations = (
        await station_repo.get_active_all_cities()
        if is_all_scope
        else await station_repo.get_active_by_city(city)
    )

    results: list[LiveAQIResponse] = []
    for station in stations:
        reading = await reading_repo.get_latest_by_station(station.id)
        if reading is None:
            continue
        # The India-wide heatmap (scope=all) must show real observations
        # only — statistical-fallback data must never be painted onto the
        # nationwide map as if it were measured coverage. City-scoped
        # dashboards keep seeing synthetic-fallback readings (clearly
        # flagged via data_source below) since that's an existing,
        # separate feature this task does not touch.
        if is_all_scope and reading.quality_flag == "synthetic":
            continue
        item = _build_live_aqi_response(station, reading)
        item.trend = await reading_repo.get_station_trend(station.id, reading.aqi)
        results.append(item)

    serialized = [r.model_dump(mode="json") for r in results]
    await cache_set(cache_key, serialized, ttl=300)
    return APIResponse(data=results)


@router.get("/history", response_model=APIResponse[list[dict]])
async def get_aqi_history(
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_db)],
    station_id: UUID | None = Query(None),
    city: str | None = Query(None),
    ward_id: str | None = Query(None),
    start_time: datetime = Query(
        default_factory=lambda: datetime.now(timezone.utc) - timedelta(days=7)
    ),
    end_time: datetime = Query(default_factory=lambda: datetime.now(timezone.utc)),
    interval: str = Query("1h", pattern="^(15m|1h|6h|24h)$"),
) -> APIResponse[list[dict]]:
    if not station_id and not city:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Either station_id or city is required",
        )

    repo = AQIReadingRepository(session)
    data = await repo.get_history(
        station_id, start_time, end_time, interval, city=city, ward_id=ward_id
    )
    return APIResponse(data=data)


@router.get("/health-risk", response_model=APIResponse[HealthRiskResponse])
async def get_health_risk(
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_db)],
    city: str | None = Query(None, description="City name"),
    ward_id: str | None = Query(None, description="Ward to scope the assessment to"),
    station_id: UUID | None = Query(None, description="Specific station"),
) -> APIResponse[HealthRiskResponse]:
    """Health-risk intelligence derived from the latest AQI/pollutant reading.

    This endpoint reuses the existing AQI ingestion pipeline (no separate
    data source) and applies a deterministic CPCB-breakpoint rules engine —
    see app/services/health_risk.py. It is guidance, not a diagnosis.
    """
    if not station_id and not city:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Either station_id or city is required",
        )

    station_repo = MonitoringStationRepository(session)
    reading_repo = AQIReadingRepository(session)

    reading = None
    resolved_station_id: UUID | None = None
    resolved_ward_id: str | None = ward_id

    if station_id:
        reading = await reading_repo.get_latest_by_station(station_id)
        resolved_station_id = station_id
    else:
        stations = await station_repo.get_active_by_city(city)
        if ward_id:
            stations = [s for s in stations if s.ward_id == ward_id]
        if not stations:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No active monitoring stations found for this city/ward",
            )
        # Health guidance should reflect worst-case exposure the person could
        # realistically encounter in the area, so we pick the station with
        # the highest current AQI rather than an arbitrary/first station.
        candidates = []
        for station in stations:
            r = await reading_repo.get_latest_by_station(station.id)
            if r is not None:
                candidates.append((station, r))
        if not candidates:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No recent readings available for this city/ward",
            )
        worst_station, reading = max(candidates, key=lambda pair: pair[1].aqi or 0)
        resolved_station_id = worst_station.id
        resolved_ward_id = ward_id or worst_station.ward_id

    if reading is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No recent reading available for this station",
        )

    assessment = assess_health_risk(
        aqi=reading.aqi,
        pm25=reading.pm25,
        pm10=reading.pm10,
        no2=reading.no2,
        co=reading.co,
        o3=reading.o3,
        so2=reading.so2,
    )

    return APIResponse(
        data=HealthRiskResponse(
            overall_risk=assessment.overall_risk.value,
            aqi=assessment.aqi,
            station_id=resolved_station_id,
            ward_id=resolved_ward_id,
            pollutant_risks=[
                PollutantRiskResponse(
                    pollutant=p.pollutant,
                    label=p.label,
                    value=p.value,
                    unit=p.unit,
                    risk_level=p.risk_level.value,
                    reason=p.reason,
                )
                for p in assessment.pollutant_risks
            ],
            precautions=assessment.precautions,
            sensitive_group_note=assessment.sensitive_group_note,
            generated_at=assessment.generated_at,
            is_estimate=assessment.is_estimate,
        )
    )


@router.get(
    "/recommend-locations",
    response_model=APIResponse[list[LocationRecommendationResponse]],
)
async def recommend_locations(
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_db)],
    latitude: float = Query(..., ge=-90, le=90, description="Origin latitude"),
    longitude: float = Query(..., ge=-180, le=180, description="Origin longitude"),
    city: str = Query(..., description="City to search within"),
    radius_km: float = Query(default=15.0, ge=0.5, le=100.0),
    limit: int = Query(default=5, ge=1, le=20),
) -> APIResponse[list[LocationRecommendationResponse]]:
    """Recommend nearby locations with better air quality.

    Reuses the existing monitoring-station and AQI-reading data — no new
    data source is introduced. Stations with no recent reading are simply
    excluded rather than backfilled with an invented value. Synthetic
    (statistically-modeled) readings are explicitly labeled as demo data
    in the response so the UI can be honest about data provenance.
    """
    station_repo = MonitoringStationRepository(session)
    reading_repo = AQIReadingRepository(session)

    stations = await station_repo.get_active_by_city(city)

    candidates = []
    for station in stations:
        reading = await reading_repo.get_latest_by_station(station.id)
        if reading is None:
            continue
        candidates.append((station, reading))

    if not candidates:
        return APIResponse(
            data=[], message="No recent readings available for this city"
        )

    ranked = rank_locations(
        candidates,
        origin_lat=latitude,
        origin_lon=longitude,
        limit=limit * 3,  # over-fetch before applying radius filter
    )

    within_radius = [r for r in ranked if r.distance_km <= radius_km][:limit]

    return APIResponse(
        data=[
            LocationRecommendationResponse(
                rank=item.rank,
                station_id=item.station.id,
                station_name=item.station.name,
                ward_id=item.station.ward_id,
                latitude=item.station.latitude,
                longitude=item.station.longitude,
                distance_km=round(item.distance_km, 2),
                aqi=item.aqi,
                aqi_category=(
                    get_aqi_category(item.aqi)[0] if item.aqi is not None else None
                ),
                freshness=item.freshness.value,
                reason=item.reason,
                observed_at=item.reading.timestamp,
            )
            for item in within_radius
        ]
    )


@router.get("/route-analysis", response_model=APIResponse[RouteAnalysisResponse])
async def route_analysis(
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_db)],
    origin_lat: float = Query(..., ge=-90, le=90),
    origin_lon: float = Query(..., ge=-180, le=180),
    dest_lat: float = Query(..., ge=-90, le=90),
    dest_lon: float = Query(..., ge=-180, le=180),
    city: str = Query(..., description="City to source monitoring stations from"),
    num_samples: int = Query(default=6, ge=2, le=20),
) -> APIResponse[RouteAnalysisResponse]:
    """Estimate environmental exposure along a straight-line path.

    No routing/directions engine is integrated in this deployment (see
    app/services/route_analysis.py), so this endpoint does NOT return real
    driving directions — it samples points along the direct line between
    origin and destination and reports the nearest monitoring station's AQI
    at each point. This is clearly labeled in the response via
    `routing_data_source` and `data_disclaimer`.
    """
    station_repo = MonitoringStationRepository(session)
    reading_repo = AQIReadingRepository(session)

    stations = await station_repo.get_active_by_city(city)
    candidates = []
    for station in stations:
        reading = await reading_repo.get_latest_by_station(station.id)
        if reading is not None:
            candidates.append((station, reading))

    result = analyze_route(
        origin_lat=origin_lat,
        origin_lon=origin_lon,
        dest_lat=dest_lat,
        dest_lon=dest_lon,
        stations_with_readings=candidates,
        num_samples=num_samples,
    )

    return APIResponse(
        data=RouteAnalysisResponse(
            total_distance_km=result.total_distance_km,
            samples=[
                RouteSampleResponse(
                    sequence=s.sequence,
                    latitude=s.latitude,
                    longitude=s.longitude,
                    distance_from_origin_km=round(s.distance_from_origin_km, 2),
                    nearest_station_name=s.nearest_station_name,
                    nearest_station_distance_km=s.nearest_station_distance_km,
                    aqi=s.aqi,
                    aqi_category=(
                        get_aqi_category(s.aqi)[0] if s.aqi is not None else None
                    ),
                    freshness=s.freshness.value,
                    observed_at=s.observed_at,
                )
                for s in result.samples
            ],
            average_aqi=result.average_aqi,
            peak_aqi=result.peak_aqi,
            peak_sample_index=result.peak_sample_index,
            overall_exposure=result.overall_exposure,
            high_pollution_segments=result.high_pollution_segments,
            alternative_route_note=result.alternative_route_note,
            routing_data_source=result.routing_data_source,
        )
    )


@router.get("/traffic-pollution", response_model=APIResponse[TrafficPollutionResponse])
async def traffic_pollution_analysis(
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_db)],
    city: str = Query(default="Pune"),
    ward_id: str | None = Query(default=None),
    hours: int = Query(default=48, ge=6, le=168),
) -> APIResponse[TrafficPollutionResponse]:
    """Traffic-pollution association analysis.

    Important: no live traffic API is integrated in this deployment. Traffic
    level here comes from app/services/traffic_provider.py — a time-of-day
    demo model by default, or a CSV file when TRAFFIC_PROVIDER=csv. The
    response's `traffic_data_source` field always says which, and the
    observation text never claims a live feed or a causal relationship —
    only an association, per the standard used throughout this platform.
    """
    start_time = datetime.now(timezone.utc) - timedelta(hours=hours)
    end_time = datetime.now(timezone.utc)

    # Correctly scoped to city (and optionally ward) — the generic
    # AQIReadingRepository.get_history city-wide branch does not filter by
    # city at all (pre-existing bug), so this endpoint uses its own query.
    if ward_id:
        stmt = text(
            """
            SELECT
                time_bucket('1 hour', r.timestamp) AS bucket,
                AVG(r.aqi) AS aqi, AVG(r.pm25) AS pm25,
                AVG(r.pm10) AS pm10, AVG(r.no2) AS no2,
                COUNT(*) AS reading_count
            FROM aqi_readings r
            JOIN monitoring_stations s ON r.station_id = s.id
            WHERE s.city = :city AND s.ward_id = :ward_id
              AND r.timestamp BETWEEN :start_time AND :end_time
              AND r.is_deleted = false AND r.quality_flag != 'invalid'
            GROUP BY bucket ORDER BY bucket
            """
        )
        params = {
            "city": city,
            "ward_id": ward_id,
            "start_time": start_time,
            "end_time": end_time,
        }
    else:
        stmt = text(
            """
            SELECT
                time_bucket('1 hour', r.timestamp) AS bucket,
                AVG(r.aqi) AS aqi, AVG(r.pm25) AS pm25,
                AVG(r.pm10) AS pm10, AVG(r.no2) AS no2,
                COUNT(*) AS reading_count
            FROM aqi_readings r
            JOIN monitoring_stations s ON r.station_id = s.id
            WHERE s.city = :city
              AND r.timestamp BETWEEN :start_time AND :end_time
              AND r.is_deleted = false AND r.quality_flag != 'invalid'
            GROUP BY bucket ORDER BY bucket
            """
        )
        params = {"city": city, "start_time": start_time, "end_time": end_time}

    result = await session.execute(stmt, params)
    hourly_readings = [dict(row._mapping) for row in result]

    analysis = analyze_traffic_pollution(
        hourly_readings=hourly_readings, ward_id=ward_id
    )

    return APIResponse(
        data=TrafficPollutionResponse(
            city=city,
            ward_id=ward_id,
            window_hours=hours,
            period_stats=[
                TrafficPeriodStatsResponse(
                    traffic_level=s.traffic_level.value,
                    reading_count=s.reading_count,
                    avg_aqi=s.avg_aqi,
                    avg_pm25=s.avg_pm25,
                    avg_pm10=s.avg_pm10,
                    avg_no2=s.avg_no2,
                )
                for s in analysis.period_stats
            ],
            high_vs_low_aqi_ratio=analysis.high_vs_low_aqi_ratio,
            observation=analysis.observation,
            traffic_data_source=analysis.traffic_data_source.value,
            traffic_data_note=analysis.traffic_data_note,
            sample_size=analysis.sample_size,
        )
    )


@router.post("/compare-routes", response_model=APIResponse[RouteComparisonResponse])
async def compare_routes_endpoint(
    request: CompareRoutesRequest,
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> APIResponse[RouteComparisonResponse]:
    """Smart Mobility Intelligence — compare 2+ named routes by estimated
    pollution exposure. See app/services/route_comparison.py: distance is a
    genuine geometric calculation over the waypoints you supply, duration is
    only ever echoed back if you supply it, and exposure is explicitly
    labeled an estimate from nearest-station data, not a live route sensor.
    """
    station_repo = MonitoringStationRepository(session)
    reading_repo = AQIReadingRepository(session)

    stations = await station_repo.get_active_by_city(request.city)
    candidates = []
    for station in stations:
        reading = await reading_repo.get_latest_by_station(station.id)
        if reading is not None:
            candidates.append((station, reading))

    route_candidates = [
        RouteCandidate(
            name=r.name,
            waypoints=[
                Waypoint(latitude=w.latitude, longitude=w.longitude)
                for w in r.waypoints
            ],
            duration_minutes=r.duration_minutes,
        )
        for r in request.routes
    ]

    result = compare_routes(
        route_candidates, candidates, num_samples=request.num_samples
    )

    return APIResponse(
        data=RouteComparisonResponse(
            routes=[
                RouteExposureResultResponse(
                    name=r.name,
                    total_distance_km=r.total_distance_km,
                    duration_minutes=r.duration_minutes,
                    estimated_aqi_exposure=r.estimated_aqi_exposure,
                    peak_aqi=r.peak_aqi,
                    samples_used=r.samples_used,
                    freshness_summary=r.freshness_summary,
                    estimated_co2_kg=r.estimated_co2_kg,
                    traffic_level=r.traffic_level,
                    traffic_data_source=r.traffic_data_source,
                )
                for r in result.routes
            ],
            recommended_route_name=result.recommended_route_name,
            recommendation_text=result.recommendation_text,
            routing_data_source=result.routing_data_source,
            exposure_disclaimer=result.exposure_disclaimer,
            lowest_co2_route_name=result.lowest_co2_route_name,
            fastest_route_name=result.fastest_route_name,
            balanced_route_name=result.balanced_route_name,
            co2_disclaimer=result.co2_disclaimer,
            traffic_disclaimer=result.traffic_disclaimer,
            category_note=result.category_note,
        )
    )
