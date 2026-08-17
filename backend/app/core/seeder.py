"""
Demo data seeder for Pune — runs on startup in development mode.
Uses only free/open data sources. No paid API keys required for demo.
"""

import random
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.logging import logger
from app.core.security import hash_password


async def seed_all():
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    AsyncSession = async_sessionmaker(engine, expire_on_commit=False)

    async with AsyncSession() as session:
        already = await session.scalar(
            text("SELECT COUNT(*) FROM users WHERE is_deleted = false")
        )
        if already and already > 0:
            logger.info("seed.skipped", reason="data already exists")
            await engine.dispose()
            return

        logger.info("seed.starting")
        await _seed_users(session)
        await _seed_stations(session)
        await _seed_emission_sources(session)
        station_ids = await _seed_aqi_readings(session)
        await _seed_forecasts(session)
        await _seed_attributions(session)
        await _seed_anomalies(session, station_ids)
        await _seed_enforcement(session)
        await _seed_outcomes(session)
        await _seed_policy_snapshots(session)
        await _seed_alerts(session)
        await session.commit()
        logger.info("seed.complete")

    await engine.dispose()


async def _seed_users(session):
    from app.models.user import User, UserRole

    users = [
        User(
            email="admin@pune.gov.in",
            hashed_password=hash_password("Admin@123"),
            full_name="Priya Sharma",
            role=UserRole.CITY_ADMINISTRATOR,
            city="Pune",
            preferred_language="en",
            is_active=True,
        ),
        User(
            email="officer@mpcb.gov.in",
            hashed_password=hash_password("Officer@123"),
            full_name="Rajesh Patil",
            role=UserRole.POLLUTION_CONTROL_OFFICER,
            city="Pune",
            preferred_language="mr",
            is_active=True,
        ),
        User(
            email="inspector@pune.gov.in",
            hashed_password=hash_password("Inspector@123"),
            full_name="Amit Desai",
            role=UserRole.FIELD_INSPECTOR,
            city="Pune",
            ward_id="W07",
            preferred_language="en",
            is_active=True,
        ),
        User(
            email="citizen@pune.in",
            hashed_password=hash_password("Citizen@123"),
            full_name="Sunita Kulkarni",
            role=UserRole.CITIZEN,
            city="Pune",
            ward_id="W02",
            preferred_language="mr",
            is_active=True,
        ),
    ]
    session.add_all(users)
    await session.flush()
    logger.info("seed.users", count=len(users))


async def _seed_stations(session):
    from geoalchemy2.elements import WKTElement

    from app.models.monitoring import MonitoringStation

    stations_data = [
        ("PUNE_001", "Karve Road CAAQMS", "W01", 18.5074, 73.8077),
        ("PUNE_002", "Shivajinagar CAAQMS", "W02", 18.5308, 73.8475),
        ("PUNE_003", "Hadapsar CAAQMS", "W03", 18.5089, 73.9259),
        ("PUNE_004", "Pimpri CAAQMS", "W04", 18.6298, 73.7997),
        ("PUNE_005", "Katraj CAAQMS", "W05", 18.4530, 73.8618),
        ("PUNE_006", "Wakad CAAQMS", "W06", 18.5989, 73.7601),
        ("PUNE_007", "Kothrud CAAQMS", "W07", 18.4968, 73.8126),
        ("PUNE_008", "Yerawada CAAQMS", "W08", 18.5559, 73.9007),
        # Mumbai
        ("MUM_001", "Andheri CAAQMS", "K/W", 19.1136, 72.8697),
        ("MUM_002", "Bandra CAAQMS", "H/W", 19.0596, 72.8295),
        ("MUM_003", "Worli CAAQMS", "G/S", 19.0177, 72.8139),
    ]

    stations = []
    for code, name, ward, lat, lon in stations_data:
        city = "Pune" if code.startswith("PUNE") else "Mumbai"
        geom = WKTElement(f"POINT({lon} {lat})", srid=4326)
        stations.append(
            MonitoringStation(
                name=name,
                station_code=code,
                city=city,
                ward_id=ward,
                operator="MPCB / CPCB",
                latitude=lat,
                longitude=lon,
                geometry=geom,
                is_active=True,
                station_type="CAAQMS",
                installed_at=datetime(2021, 4, 1, tzinfo=UTC),
                maintenance_score=random.uniform(0.75, 0.98),
            )
        )

    session.add_all(stations)
    await session.flush()
    logger.info("seed.stations", count=len(stations))


async def _seed_emission_sources(session):
    from geoalchemy2.elements import WKTElement

    from app.models.emission_source import (
        EmissionSource,
        EmissionSourceType,
        PermitStatus,
    )

    sources_data = [
        (
            "Pimpri Chinchwad Industrial Cluster",
            EmissionSourceType.INDUSTRIAL,
            "W04",
            18.6298,
            73.7997,
            PermitStatus.VALID,
            0,
        ),
        (
            "Hadapsar Industrial Estate",
            EmissionSourceType.INDUSTRIAL,
            "W03",
            18.5089,
            73.9259,
            PermitStatus.EXPIRED,
            3,
        ),
        (
            "Shivajinagar Construction Site A",
            EmissionSourceType.CONSTRUCTION,
            "W02",
            18.5350,
            73.8510,
            PermitStatus.VALID,
            1,
        ),
        (
            "Karve Road Traffic Corridor",
            EmissionSourceType.VEHICULAR,
            "W01",
            18.5074,
            73.8077,
            PermitStatus.NONE,
            0,
        ),
        (
            "Katraj Waste Burning Site",
            EmissionSourceType.BIOMASS,
            "W05",
            18.4530,
            73.8618,
            PermitStatus.NONE,
            5,
        ),
        (
            "Wakad Metro Construction",
            EmissionSourceType.CONSTRUCTION,
            "W06",
            18.5989,
            73.7601,
            PermitStatus.VALID,
            0,
        ),
        (
            "Yerawada Brick Kiln",
            EmissionSourceType.INDUSTRIAL,
            "W08",
            18.5600,
            73.9050,
            PermitStatus.SUSPENDED,
            7,
        ),
        (
            "Kothrud Residential Burning",
            EmissionSourceType.BIOMASS,
            "W07",
            18.4968,
            73.8126,
            PermitStatus.NONE,
            2,
        ),
    ]

    sources = []
    for name, stype, ward, lat, lon, permit, violations in sources_data:
        geom = WKTElement(f"POINT({lon} {lat})", srid=4326)
        sources.append(
            EmissionSource(
                name=name,
                source_type=stype,
                city="Pune",
                ward_id=ward,
                latitude=lat,
                longitude=lon,
                geometry=geom,
                permit_status=permit,
                violation_count=violations,
                operator_name=f"{name} Operator",
                is_active=True,
                last_inspected_at=datetime.now(UTC)
                - timedelta(days=random.randint(10, 90)),
                emission_rate_kg_hr=random.uniform(5, 120),
                carbon_estimate_ton_yr=random.uniform(50, 800),
            )
        )

    session.add_all(sources)
    await session.flush()
    logger.info("seed.emission_sources", count=len(sources))


async def _seed_aqi_readings(session) -> list:
    from app.models.monitoring import AQIReading

    result = await session.execute(
        select(text("id, latitude, longitude, ward_id, station_code"))
        .select_from(text("monitoring_stations"))
        .where(text("city = 'Pune' AND is_deleted = false"))
    )
    stations = result.fetchall()

    WARD_BASELINES = {
        "W01": 68,
        "W02": 72,
        "W03": 95,
        "W04": 105,
        "W05": 62,
        "W06": 58,
        "W07": 78,
        "W08": 70,
    }

    readings = []
    now = datetime.now(UTC)
    # 7 days of hourly readings
    for hours_back in range(168, 0, -1):
        ts = now - timedelta(hours=hours_back)
        hour = ts.hour
        dow = ts.weekday()
        traffic = (
            1.5 if (7 <= hour <= 10 or 17 <= hour <= 20) else (0.6 if hour < 5 else 1.0)
        )
        if dow >= 5:
            traffic *= 0.8

        for s in stations:
            baseline = WARD_BASELINES.get(s.ward_id, 70)
            pm25 = baseline * traffic * random.uniform(0.85, 1.15)
            pm10 = pm25 * random.uniform(1.6, 2.1)
            no2 = 25 + traffic * 18 * random.uniform(0.8, 1.2)

            def calc_aqi(p: float) -> int:
                for c_lo, c_hi, i_lo, i_hi in [
                    (0, 30, 0, 50),
                    (30, 60, 51, 100),
                    (60, 90, 101, 200),
                    (90, 120, 201, 300),
                    (120, 250, 301, 400),
                ]:
                    if c_lo <= p <= c_hi:
                        return int(((i_hi - i_lo) / (c_hi - c_lo)) * (p - c_lo) + i_lo)
                return 400

            readings.append(
                AQIReading(
                    station_id=s.id,
                    pm25=round(pm25, 2),
                    pm10=round(pm10, 2),
                    no2=round(no2, 2),
                    so2=round(random.uniform(5, 20), 2),
                    co=round(0.8 + traffic * 0.5 * random.uniform(0.8, 1.2), 2),
                    o3=round(max(0, 35 - traffic * 8 + random.uniform(-8, 8)), 2),
                    aqi=calc_aqi(pm25),
                    temperature=round(24 + random.uniform(-4, 8), 1),
                    humidity=round(55 + random.uniform(-20, 25), 1),
                    wind_speed=round(random.uniform(0.5, 7.0), 1),
                    wind_direction=round(random.uniform(0, 360), 1),
                    timestamp=ts,
                    latitude=s.latitude,
                    longitude=s.longitude,
                    quality_flag="good",
                )
            )

    # Add current readings
    for s in stations:
        baseline = WARD_BASELINES.get(s.ward_id, 70)
        hour = now.hour
        traffic = (
            1.5 if (7 <= hour <= 10 or 17 <= hour <= 20) else (0.6 if hour < 5 else 1.0)
        )
        pm25 = baseline * traffic * random.uniform(0.9, 1.1)

        def calc_aqi(p: float) -> int:
            for c_lo, c_hi, i_lo, i_hi in [
                (0, 30, 0, 50),
                (30, 60, 51, 100),
                (60, 90, 101, 200),
                (90, 120, 201, 300),
                (120, 250, 301, 400),
            ]:
                if c_lo <= p <= c_hi:
                    return int(((i_hi - i_lo) / (c_hi - c_lo)) * (p - c_lo) + i_lo)
            return 400

        readings.append(
            AQIReading(
                station_id=s.id,
                pm25=round(pm25, 2),
                pm10=round(pm25 * 1.8, 2),
                no2=round(25 + traffic * 18, 2),
                so2=round(random.uniform(5, 20), 2),
                co=round(0.8 + traffic * 0.5, 2),
                o3=round(max(0, 35 - traffic * 8), 2),
                aqi=calc_aqi(pm25),
                temperature=round(26 + random.uniform(-2, 4), 1),
                humidity=round(58 + random.uniform(-10, 15), 1),
                wind_speed=round(random.uniform(1.0, 5.0), 1),
                wind_direction=round(random.uniform(0, 360), 1),
                timestamp=now,
                latitude=s.latitude,
                longitude=s.longitude,
                quality_flag="good",
            )
        )

    # Bulk insert in chunks
    chunk_size = 200
    for i in range(0, len(readings), chunk_size):
        session.add_all(readings[i : i + chunk_size])
        await session.flush()

    logger.info("seed.aqi_readings", count=len(readings))
    return [s.id for s in stations]


async def _seed_forecasts(session):
    from geoalchemy2.elements import WKTElement

    from app.models.enforcement import ForecastGrid

    WARD_COORDS = {
        "W01": (18.5074, 73.8077),
        "W02": (18.5308, 73.8475),
        "W03": (18.5089, 73.9259),
        "W04": (18.6298, 73.7997),
        "W05": (18.4530, 73.8618),
        "W06": (18.5989, 73.7601),
        "W07": (18.4968, 73.8126),
        "W08": (18.5559, 73.9007),
    }
    BASELINES = {
        "W01": 68,
        "W02": 72,
        "W03": 95,
        "W04": 105,
        "W05": 62,
        "W06": 58,
        "W07": 78,
        "W08": 70,
    }
    now = datetime.now(UTC)
    grids = []

    for ward, (lat, lon) in WARD_COORDS.items():
        delta = 0.01
        geom = WKTElement(
            f"POLYGON(({lon-delta} {lat-delta},{lon+delta} {lat-delta},"
            f"{lon+delta} {lat+delta},{lon-delta} {lat+delta},{lon-delta} {lat-delta}))",
            srid=4326,
        )
        base = BASELINES.get(ward, 75)
        for h in range(1, 73):
            ft = now + timedelta(hours=h)
            hour = ft.hour
            traffic = (
                1.5
                if (7 <= hour <= 10 or 17 <= hour <= 20)
                else (0.6 if hour < 5 else 1.0)
            )
            if ft.weekday() >= 5:
                traffic *= 0.8
            aqi = max(10, int(base * traffic * random.uniform(0.9, 1.1)))
            confidence = max(0.55, 0.92 - h * 0.005)
            margin = int(aqi * (1 - confidence) * 1.5)
            grids.append(
                ForecastGrid(
                    city="Pune",
                    ward_id=ward,
                    grid_geometry=geom,
                    forecast_timestamp=ft,
                    generated_at=now,
                    aqi_forecast=aqi,
                    pm25_forecast=round(aqi * 0.55, 1),
                    pm10_forecast=round(aqi * 1.1, 1),
                    confidence_score=round(confidence, 3),
                    confidence_lower=max(0, aqi - margin),
                    confidence_upper=aqi + margin,
                    model_version="statistical-v1.0",
                    contributing_factors={
                        "traffic": 0.35,
                        "weather": 0.25,
                        "industrial": 0.20,
                        "seasonal": 0.20,
                    },
                    feature_importance={
                        "current_aqi": 0.38,
                        "hour_of_day": 0.22,
                        "ward_type": 0.18,
                        "day_of_week": 0.12,
                        "weather": 0.10,
                    },
                )
            )

    for i in range(0, len(grids), 200):
        session.add_all(grids[i : i + 200])
        await session.flush()
    logger.info("seed.forecasts", count=len(grids))


async def _seed_attributions(session):
    from geoalchemy2.elements import WKTElement

    from app.models.analytics import PollutionAttribution

    WARD_COORDS = {
        "W01": (18.5074, 73.8077),
        "W02": (18.5308, 73.8475),
        "W03": (18.5089, 73.9259),
        "W04": (18.6298, 73.7997),
        "W05": (18.4530, 73.8618),
        "W06": (18.5989, 73.7601),
        "W07": (18.4968, 73.8126),
        "W08": (18.5559, 73.9007),
    }
    # Same ward AQI baselines used to seed forecast grids, reused here so
    # confidence tracks each ward's actual pollution level instead of being
    # blind to it (see the AttributionAgent confidence fix below).
    AQI_BASELINES = {
        "W01": 68,
        "W02": 72,
        "W03": 95,
        "W04": 105,
        "W05": 62,
        "W06": 58,
        "W07": 78,
        "W08": 70,
    }

    now = datetime.now(UTC)
    records = []

    for hours_back in range(48, 0, -6):
        ts = now - timedelta(hours=hours_back)
        hour = ts.hour
        is_peak = 7 <= hour <= 10 or 17 <= hour <= 20
        dow = ts.weekday()
        is_weekend = dow >= 5

        for ward, (lat, lon) in WARD_COORDS.items():
            is_ind = ward in ("W03", "W04")
            industrial = (0.38 if is_ind else 0.12) * (0.8 if dow >= 5 else 1.0)
            vehicular = (0.40 if is_peak else 0.22) * (0.85 if dow >= 5 else 1.0)
            construction = 0.15 if dow < 5 else 0.08
            biomass = 0.08 if (5 <= hour <= 9) else 0.04
            dust = 0.10
            domestic = 0.06 if (6 <= hour <= 9 or 18 <= hour <= 21) else 0.03
            total = industrial + vehicular + construction + biomass + dust + domestic
            s = 1.0 / total

            # Mirrors app.workers.tasks.attribution._attribute_sources: a
            # continuous, multi-signal confidence estimate (AQI-level signal
            # strength, industrial-ward stability, peak-hour traffic
            # clarity, weekend unpredictability) rather than a value that
            # only ever takes one of two constants regardless of ward or
            # time.
            ward_aqi = AQI_BASELINES.get(ward, 75)
            aqi_signal = min(1.0, max(0.0, (ward_aqi - 50) / 150))
            confidence = 0.58 + 0.22 * aqi_signal
            if is_ind:
                confidence += 0.05
            if is_peak and not is_ind:
                confidence += 0.03
            if is_weekend:
                confidence -= 0.04
            confidence = min(0.90, max(0.55, confidence))

            delta = 0.01
            geom = WKTElement(
                f"POLYGON(({lon-delta} {lat-delta},{lon+delta} {lat-delta},"
                f"{lon+delta} {lat+delta},{lon-delta} {lat+delta},{lon-delta} {lat-delta}))",
                srid=4326,
            )
            records.append(
                PollutionAttribution(
                    ward_id=ward,
                    city="Pune",
                    timestamp=ts,
                    vehicular_pct=round(vehicular * s * 100, 1),
                    industrial_pct=round(industrial * s * 100, 1),
                    construction_pct=round(construction * s * 100, 1),
                    biomass_pct=round(biomass * s * 100, 1),
                    secondary_aerosol_pct=0.0,
                    dust_pct=round(dust * s * 100, 1),
                    domestic_pct=round(domestic * s * 100, 1),
                    overall_confidence=round(confidence, 3),
                    contributing_sources={"thermal_hotspot": is_ind},
                    satellite_evidence={
                        "ndvi_anomaly": False,
                        "thermal_hotspot": is_ind,
                    },
                    model_version="receptor-model-v1.2",
                    geometry=geom,
                )
            )

    session.add_all(records)
    await session.flush()
    logger.info("seed.attributions", count=len(records))


async def _seed_anomalies(session, station_ids: list):
    from geoalchemy2.elements import WKTElement

    from app.models.analytics import AnomalyEvent
    from app.models.monitoring import MonitoringStation

    result = await session.execute(
        select(MonitoringStation).where(
            MonitoringStation.city == "Pune",
            MonitoringStation.is_deleted == False,
        )
    )
    stations = result.scalars().all()
    now = datetime.now(UTC)

    events = [
        # The demo Ward 7 spike
        AnomalyEvent(
            station_id=next(s.id for s in stations if s.ward_id == "W07"),
            ward_id="W07",
            city="Pune",
            detected_at=now - timedelta(hours=1),
            aqi_spike_value=285,
            baseline_aqi=78,
            probable_cause="Construction activity spike combined with evening traffic peak",
            cause_category="construction",
            confidence_score=0.87,
            is_resolved=False,
            geometry=WKTElement("POINT(73.8126 18.4968)", srid=4326),
            root_cause_timeline={
                "baseline_aqi": 78,
                "spike_aqi": 285,
                "z_score": 4.8,
                "sequence": [
                    {
                        "time": (now - timedelta(hours=3)).isoformat(),
                        "event": "Construction site resumed operations after lunch break",
                        "aqi": 95,
                    },
                    {
                        "time": (now - timedelta(hours=2)).isoformat(),
                        "event": "Evening traffic peak began on Paud Road",
                        "aqi": 145,
                    },
                    {
                        "time": (now - timedelta(hours=1, minutes=30)).isoformat(),
                        "event": "Wind shifted to SE — concentrated dispersion toward station",
                        "aqi": 210,
                    },
                    {
                        "time": (now - timedelta(hours=1)).isoformat(),
                        "event": "AQI spike detected — threshold exceeded",
                        "aqi": 285,
                    },
                ],
            },
            contributing_sources={
                "construction": {"confidence": 0.87, "source": "Kothrud Metro Site"},
                "vehicular": {"confidence": 0.71, "source": "Paud Road corridor"},
            },
        ),
        AnomalyEvent(
            station_id=next(s.id for s in stations if s.ward_id == "W04"),
            ward_id="W04",
            city="Pune",
            detected_at=now - timedelta(hours=6),
            aqi_spike_value=310,
            baseline_aqi=105,
            probable_cause="Industrial stack emissions from Pimpri industrial cluster — shift change",
            cause_category="industrial",
            confidence_score=0.91,
            is_resolved=True,
            geometry=WKTElement("POINT(73.7997 18.6298)", srid=4326),
            root_cause_timeline={"baseline_aqi": 105, "spike_aqi": 310, "z_score": 5.2},
        ),
    ]
    session.add_all(events)
    await session.flush()
    logger.info("seed.anomalies", count=len(events))


async def _seed_enforcement(session):
    from geoalchemy2.elements import WKTElement

    from app.models.enforcement import ActionStatus, ActionType, EnforcementAction

    result = await session.execute(
        select(text("id"))
        .select_from(text("users"))
        .where(text("role = 'field_inspector'"))
    )
    inspector_id = result.scalar()
    result2 = await session.execute(
        select(text("id"))
        .select_from(text("users"))
        .where(text("role = 'pollution_control_officer'"))
    )
    officer_id = result2.scalar()

    result3 = await session.execute(
        select(text("id"))
        .select_from(text("emission_sources"))
        .where(text("city = 'Pune'"))
        .limit(4)
    )
    source_ids = [row[0] for row in result3.fetchall()]

    now = datetime.now(UTC)
    actions = [
        EnforcementAction(
            officer_id=inspector_id or officer_id,
            source_id=source_ids[0] if source_ids else None,
            ward_id="W07",
            city="Pune",
            action_type=ActionType.INSPECTION,
            status=ActionStatus.ASSIGNED,
            priority_score=92.5,
            title="Emergency inspection — Kothrud construction site AQI spike",
            description="AQI spike of 285 detected in W07. Construction dust identified as primary contributor (87% confidence). Immediate on-site inspection required.",
            latitude=18.4968,
            longitude=73.8126,
            geometry=WKTElement("POINT(73.8126 18.4968)", srid=4326),
            ai_reasoning={
                "trigger": "anomaly_detection",
                "aqi_spike": 285,
                "confidence": 0.87,
                "primary_source": "construction",
                "recommended_action": "Issue stop-work notice and dust suppression order",
                "supporting_evidence": ["sensor_W07_CAAQMS", "attribution_model_v1.2"],
            },
        ),
        EnforcementAction(
            officer_id=officer_id or inspector_id,
            source_id=source_ids[1] if len(source_ids) > 1 else None,
            ward_id="W08",
            city="Pune",
            action_type=ActionType.NOTICE,
            status=ActionStatus.COMPLETED,
            priority_score=78.0,
            title="Notice issued — Yerawada Brick Kiln permit violation",
            description="Operating with suspended permit. Stack emissions above NAAQS limits for SO2.",
            latitude=18.5600,
            longitude=73.9050,
            geometry=WKTElement("POINT(73.9050 18.5600)", srid=4326),
            outcome_score=65.0,
            resolved_at=now - timedelta(hours=18),
            ai_reasoning={
                "trigger": "permit_check",
                "violation_type": "expired_permit",
                "confidence": 0.95,
            },
        ),
        EnforcementAction(
            officer_id=inspector_id or officer_id,
            source_id=source_ids[2] if len(source_ids) > 2 else None,
            ward_id="W04",
            city="Pune",
            action_type=ActionType.SHUTDOWN,
            status=ActionStatus.PENDING,
            priority_score=88.0,
            title="Shutdown order — Hadapsar Industrial Estate repeat offender",
            description="Third violation in 90 days. Expired permit, no dust control measures in place.",
            latitude=18.5089,
            longitude=73.9259,
            geometry=WKTElement("POINT(73.9259 18.5089)", srid=4326),
            ai_reasoning={
                "trigger": "violation_history",
                "violation_count": 3,
                "confidence": 0.93,
            },
        ),
        EnforcementAction(
            officer_id=inspector_id or officer_id,
            source_id=source_ids[3] if len(source_ids) > 3 else None,
            ward_id="W05",
            city="Pune",
            action_type=ActionType.WARNING,
            status=ActionStatus.IN_PROGRESS,
            priority_score=61.0,
            title="Warning — Katraj waste burning detected via satellite",
            description="Biomass burning detected in W05. Contributing ~8% to area AQI. Field verification required.",
            latitude=18.4530,
            longitude=73.8618,
            geometry=WKTElement("POINT(73.8618 18.4530)", srid=4326),
            ai_reasoning={"trigger": "satellite_thermal", "confidence": 0.72},
        ),
    ]

    session.add_all(actions)
    await session.flush()
    logger.info("seed.enforcement", count=len(actions))


async def _seed_outcomes(session):
    from app.models.enforcement import InterventionOutcome

    result = await session.execute(
        select(text("id"))
        .select_from(text("enforcement_actions"))
        .where(text("status = 'completed' AND city = 'Pune'"))
        .limit(1)
    )
    action_id = result.scalar()
    if not action_id:
        return

    result2 = await session.execute(
        select(text("id"))
        .select_from(text("users"))
        .where(text("role = 'pollution_control_officer'"))
    )
    verifier_id = result2.scalar()

    outcome = InterventionOutcome(
        action_id=action_id,
        aqi_before=195.0,
        aqi_after=128.0,
        delta_score=67.0,
        pm25_before=88.5,
        pm25_after=52.3,
        measurement_period_hours=24,
        verified_by=verifier_id,
        verification_method="CAAQMS 24h rolling average comparison",
        carbon_saved_kg=240.0,
        confidence_score=0.84,
    )
    session.add(outcome)
    await session.flush()
    logger.info("seed.outcomes")


async def _seed_policy_snapshots(session):
    from app.models.analytics import PolicySnapshot

    now = datetime.now(UTC)
    policies = [
        PolicySnapshot(
            city="Pune",
            policy_type="odd_even_vehicles",
            description="Odd-even vehicle restriction on Karve Road and FC Road 7–10 AM, 5–8 PM",
            implemented_at=now - timedelta(days=45),
            impact_score=72.0,
            comparable_city_ref="Delhi",
            aqi_delta=-28.5,
            pm25_delta=-14.2,
            measurement_days=30,
            metadata={
                "coverage_roads": ["Karve Road", "FC Road"],
                "hours": "7-10, 17-20",
            },
        ),
        PolicySnapshot(
            city="Mumbai",
            policy_type="construction_dust_control",
            description="Mandatory green netting and water sprinklers for all construction sites > 500 sqm",
            implemented_at=now - timedelta(days=90),
            impact_score=58.0,
            comparable_city_ref="Pune",
            aqi_delta=-18.0,
            pm25_delta=-9.5,
            measurement_days=60,
            metadata={"compliance_rate": 0.72},
        ),
        PolicySnapshot(
            city="Delhi",
            policy_type="graded_response_action_plan",
            description="GRAP Stage III — ban on BS3 petrol and BS4 diesel vehicles",
            implemented_at=now - timedelta(days=120),
            impact_score=85.0,
            comparable_city_ref="Pune",
            aqi_delta=-45.0,
            pm25_delta=-22.0,
            measurement_days=15,
            metadata={"vehicle_categories_banned": ["BS3 petrol", "BS4 diesel"]},
        ),
    ]
    session.add_all(policies)
    await session.flush()
    logger.info("seed.policy_snapshots", count=len(policies))


async def _seed_alerts(session):
    from app.models.enforcement import CitizenAlert

    now = datetime.now(UTC)
    alerts = [
        CitizenAlert(
            ward_id="W07",
            city="Pune",
            language="mr",
            channel="push",
            risk_level="very_high",
            message_title="अत्यंत अस्वास्थ्यकर हवा — बाहेर जाणे टाळा",
            message_text="वॉर्ड W07 मध्ये AQI 285 पर्यंत पोहोचला आहे. मोकळ्या हवेत व्यायाम टाळा. श्वास घेण्यास त्रास झाल्यास त्वरित वैद्यकीय मदत घ्या.",
            vulnerability_groups_targeted=["elderly", "children", "asthma_patients"],
            aqi_value=285,
            delivery_status="sent",
            sent_at=now - timedelta(hours=1),
            ai_generated=True,
        ),
        CitizenAlert(
            ward_id="W07",
            city="Pune",
            language="en",
            channel="push",
            risk_level="very_high",
            message_title="Very Unhealthy Air — Avoid Going Outside",
            message_text="AQI in Ward W07 has reached 285 — this is harmful to everyone. Avoid outdoor exercise. Schools should consider keeping students indoors.",
            vulnerability_groups_targeted=["elderly", "children", "schools"],
            aqi_value=285,
            delivery_status="sent",
            sent_at=now - timedelta(hours=1),
            ai_generated=True,
        ),
        CitizenAlert(
            ward_id="W04",
            city="Pune",
            language="hi",
            channel="push",
            risk_level="severe",
            message_title="खतरनाक वायु गुणवत्ता — वार्ड W04 आपातकाल",
            message_text="वार्ड W04 में AQI 310 है। बाहर न जाएं। दरवाजे और खिड़कियां बंद करें।",
            vulnerability_groups_targeted=[
                "outdoor_workers",
                "industrial_area_residents",
            ],
            aqi_value=310,
            delivery_status="sent",
            sent_at=now - timedelta(hours=6),
            ai_generated=True,
        ),
    ]
    session.add_all(alerts)
    await session.flush()
    logger.info("seed.alerts", count=len(alerts))
