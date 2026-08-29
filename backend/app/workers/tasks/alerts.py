import asyncio

from app.core.config import settings
from app.core.logging import logger
from app.workers.celery_app import celery_app

# Health advisory templates per language and risk level
# Written in natural advisory tone — not government circular style
TEMPLATES = {
    "en": {
        "high": {
            "title": "Poor Air Quality in Your Area — Take Precautions",
            "body": "Air quality in Ward {ward} has deteriorated (AQI {aqi}). If you need to go outside, wear an N95 mask. Keep windows closed between 7–10 AM and 5–8 PM. Those with asthma, heart conditions, or elderly family members should stay indoors.",
        },
        "very_high": {
            "title": "Very Unhealthy Air — Avoid Going Outside",
            "body": "AQI in Ward {ward} has reached {aqi} — this is harmful to everyone. Avoid outdoor exercise. Schools should consider keeping students indoors. Seek medical help immediately if you experience breathing difficulty.",
        },
        "severe": {
            "title": "Hazardous Air Quality Emergency — Ward {ward}",
            "body": "AQI {aqi} detected in Ward {ward}. This is a health emergency. Do not go outside. Seal doors and windows. Contact MPCB helpline 1800-233-4444 if breathing difficulties arise.",
        },
    },
    "mr": {
        "high": {
            "title": "तुमच्या परिसरात हवेची गुणवत्ता खराब — सावधगिरी बाळगा",
            "body": "वॉर्ड {ward} मध्ये हवेची गुणवत्ता खालावली आहे (AQI {aqi}). बाहेर जाताना N95 मास्क वापरा. सकाळी ७-१० आणि संध्याकाळी ५-८ दरम्यान खिडक्या बंद ठेवा. दमा, हृदयविकार असलेल्यांनी घरातच राहावे.",
        },
        "very_high": {
            "title": "अत्यंत अस्वास्थ्यकर हवा — बाहेर जाणे टाळा",
            "body": "वॉर्ड {ward} मध्ये AQI {aqi} पर्यंत पोहोचला आहे. मोकळ्या हवेत व्यायाम टाळा. श्वास घेण्यास त्रास झाल्यास त्वरित वैद्यकीय मदत घ्या.",
        },
        "severe": {
            "title": "धोकादायक हवा — वॉर्ड {ward} आपत्कालीन सूचना",
            "body": "वॉर्ड {ward} मध्ये AQI {aqi}. बाहेर जाऊ नका. दरवाजे आणि खिडक्या बंद करा. MPCB हेल्पलाइन 1800-233-4444 वर संपर्क करा.",
        },
    },
    "hi": {
        "high": {
            "title": "आपके क्षेत्र में खराब वायु गुणवत्ता — सावधान रहें",
            "body": "वार्ड {ward} में AQI {aqi} है। बाहर जाते समय N95 मास्क पहनें। अस्थमा या हृदय रोगियों को घर में रहना चाहिए।",
        },
        "very_high": {
            "title": "अत्यंत अस्वास्थ्यकर हवा — बाहर न जाएं",
            "body": "वार्ड {ward} में AQI {aqi} पहुंच गया है। बाहरी व्यायाम से बचें। सांस लेने में तकलीफ होने पर तुरंत चिकित्सा सहायता लें।",
        },
        "severe": {
            "title": "खतरनाक वायु गुणवत्ता — वार्ड {ward} आपातकाल",
            "body": "वार्ड {ward} में AQI {aqi}। बाहर न जाएं। दरवाजे और खिड़कियां बंद करें। MPCB हेल्पलाइन 1800-233-4444 पर संपर्क करें।",
        },
    },
}


def _get_risk_level(aqi: int) -> str:
    if aqi <= 100:
        return None
    elif aqi <= 150:
        return "moderate"
    elif aqi <= 200:
        return "high"
    elif aqi <= 300:
        return "very_high"
    else:
        return "severe"


def _get_vulnerability_groups(ward: str) -> list[str]:
    # In production, crossed with actual ward vulnerability layer DB
    groups = ["elderly", "children"]
    if ward in ("W01", "W02", "W08"):
        groups.append("schools")
    if ward in ("W03", "W04"):
        groups.extend(["outdoor_workers", "industrial_area_residents"])
    return groups


@celery_app.task(name="app.workers.tasks.alerts.generate_ward_alerts", bind=True)
def generate_ward_alerts(self):
    asyncio.run(_alerts_async())


async def _alerts_async():
    from app.models.enforcement import CitizenAlert
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    AsyncSession = async_sessionmaker(engine, expire_on_commit=False)

    async with AsyncSession() as session:
        result = await session.execute(
            text(
                """
            SELECT s.ward_id, AVG(r.aqi) AS avg_aqi
            FROM aqi_readings r
            JOIN monitoring_stations s ON r.station_id = s.id
            WHERE s.city = 'Pune'
              AND r.timestamp > NOW() - INTERVAL '30 minutes'
              AND r.is_deleted = false AND r.quality_flag != 'invalid'
              AND s.ward_id IS NOT NULL
            GROUP BY s.ward_id
        """
            )
        )
        ward_aqi = {row.ward_id: int(row.avg_aqi) for row in result}

        alerts_created = 0

        for ward, aqi in ward_aqi.items():
            risk = _get_risk_level(aqi)
            if risk is None or risk == "moderate":
                continue

            # Skip if alert sent for this ward in last 2 hours
            existing = await session.execute(
                text(
                    """
                SELECT id FROM citizen_alerts
                WHERE ward_id = :ward AND city = 'Pune'
                  AND created_at > NOW() - INTERVAL '2 hours'
                  AND is_deleted = false LIMIT 1
            """
                ),
                {"ward": ward},
            )
            if existing.scalar():
                continue

            vulnerability_groups = _get_vulnerability_groups(ward)

            for lang, templates in TEMPLATES.items():
                if risk not in templates:
                    level_key = "high"  # fallback
                else:
                    level_key = risk

                tmpl = templates[level_key]
                title = tmpl["title"].format(ward=ward, aqi=aqi)
                body = tmpl["body"].format(ward=ward, aqi=aqi)

                alert = CitizenAlert(
                    ward_id=ward,
                    city="Pune",
                    language=lang,
                    channel="push",
                    risk_level=risk,
                    message_title=title,
                    message_text=body,
                    vulnerability_groups_targeted=vulnerability_groups,
                    aqi_value=aqi,
                    delivery_status="pending",
                    ai_generated=True,
                )
                session.add(alert)
                alerts_created += 1

        await session.commit()
        logger.info("alerts.generated", city="Pune", count=alerts_created)

    await engine.dispose()
