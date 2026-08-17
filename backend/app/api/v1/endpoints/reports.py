import io
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_db
from app.schemas.base import APIResponse

router = APIRouter(prefix="/reports", tags=["Reports"])


@router.get("", response_model=APIResponse[list[dict]])
async def list_reports(
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_db)],
    city: str = Query(default="Pune"),
) -> APIResponse[list[dict]]:
    """Return available report types and recent generated reports."""
    since = datetime.now(UTC) - timedelta(days=30)

    actions_result = await session.execute(
        text(
            """
        SELECT ea.id, ea.title, ea.city, ea.ward_id, ea.status,
               ea.created_at, ea.resolved_at, ea.priority_score,
               u.full_name AS officer_name
        FROM enforcement_actions ea
        JOIN users u ON ea.officer_id = u.id
        WHERE ea.city = :city AND ea.created_at >= :since
          AND ea.is_deleted = false
        ORDER BY ea.created_at DESC LIMIT 20
    """
        ),
        {"city": city, "since": since},
    )

    reports = []
    for row in actions_result:
        reports.append(
            {
                "id": str(row.id),
                "type": "enforcement_action",
                "title": row.title,
                "city": row.city,
                "ward_id": row.ward_id,
                "status": row.status,
                "officer": row.officer_name,
                "priority_score": row.priority_score,
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "resolved_at": row.resolved_at.isoformat() if row.resolved_at else None,
            }
        )

    return APIResponse(data=reports)


@router.post("/export")
async def export_report(
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_db)],
    report_type: str = Query(default="enforcement_summary"),
    city: str = Query(default="Pune"),
    days: int = Query(default=7, ge=1, le=90),
) -> StreamingResponse:
    """Generate and stream a PDF report."""
    since = datetime.now(UTC) - timedelta(days=days)

    if report_type == "enforcement_summary":
        result = await session.execute(
            text(
                """
            SELECT ea.title, ea.ward_id, ea.action_type, ea.status,
                   ea.priority_score, ea.created_at, ea.outcome_score,
                   u.full_name AS officer_name,
                   es.name AS source_name, es.source_type
            FROM enforcement_actions ea
            JOIN users u ON ea.officer_id = u.id
            LEFT JOIN emission_sources es ON ea.source_id = es.id
            WHERE ea.city = :city AND ea.created_at >= :since
              AND ea.is_deleted = false
            ORDER BY ea.priority_score DESC
        """
            ),
            {"city": city, "since": since},
        )
        rows = result.fetchall()
        pdf_bytes = _generate_enforcement_pdf(city, days, rows)
    elif report_type == "aqi_summary":
        result = await session.execute(
            text(
                """
            SELECT
                time_bucket('1 day', r.timestamp) AS day,
                s.ward_id,
                AVG(r.aqi) AS avg_aqi,
                MAX(r.aqi) AS max_aqi,
                AVG(r.pm25) AS avg_pm25
            FROM aqi_readings r
            JOIN monitoring_stations s ON r.station_id = s.id
            WHERE s.city = :city AND r.timestamp >= :since
              AND r.is_deleted = false AND r.quality_flag != 'invalid'
            GROUP BY day, s.ward_id
            ORDER BY day, s.ward_id
        """
            ),
            {"city": city, "since": since},
        )
        rows = result.fetchall()
        pdf_bytes = _generate_aqi_pdf(city, days, rows)
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown report type"
        )

    filename = f"{report_type}_{city}_{datetime.now(UTC).strftime('%Y%m%d')}.pdf"
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _generate_enforcement_pdf(city: str, days: int, rows) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import (
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=2 * cm, bottomMargin=2 * cm)
    styles = getSampleStyleSheet()
    elements = []

    elements.append(Paragraph(f"Enforcement Action Report — {city}", styles["Title"]))
    elements.append(
        Paragraph(
            f"Period: Last {days} days | Generated: {datetime.now(UTC).strftime('%d %b %Y %H:%M UTC')}",
            styles["Normal"],
        )
    )
    elements.append(Spacer(1, 0.5 * cm))

    if rows:
        data = [["Title", "Ward", "Type", "Status", "Priority", "Officer"]]
        for row in rows:
            data.append(
                [
                    (
                        str(row.title)[:45] + "..."
                        if len(str(row.title)) > 45
                        else str(row.title)
                    ),
                    str(row.ward_id or ""),
                    str(row.action_type or ""),
                    str(row.status or ""),
                    f"{row.priority_score:.1f}" if row.priority_score else "—",
                    str(row.officer_name or ""),
                ]
            )

        table = Table(
            data, colWidths=[5.5 * cm, 1.5 * cm, 2.5 * cm, 2.5 * cm, 1.8 * cm, 3 * cm]
        )
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e3a5f")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTSIZE", (0, 0), (-1, 0), 9),
                    ("FONTSIZE", (0, 1), (-1, -1), 8),
                    (
                        "ROWBACKGROUNDS",
                        (0, 1),
                        (-1, -1),
                        [colors.white, colors.HexColor("#f0f4f8")],
                    ),
                    ("GRID", (0, 0), (-1, -1), 0.3, colors.grey),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("PADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        elements.append(table)
    else:
        elements.append(
            Paragraph("No enforcement actions found for this period.", styles["Normal"])
        )

    doc.build(elements)
    return buffer.getvalue()


def _generate_aqi_pdf(city: str, days: int, rows) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import (
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=2 * cm, bottomMargin=2 * cm)
    styles = getSampleStyleSheet()
    elements = []

    elements.append(Paragraph(f"AQI Summary Report — {city}", styles["Title"]))
    elements.append(
        Paragraph(
            f"Period: Last {days} days | Generated: {datetime.now(UTC).strftime('%d %b %Y %H:%M UTC')}",
            styles["Normal"],
        )
    )
    elements.append(Spacer(1, 0.5 * cm))

    if rows:
        data = [["Date", "Ward", "Avg AQI", "Max AQI", "Avg PM2.5"]]
        for row in rows:
            day_str = (
                row.day.strftime("%d %b")
                if hasattr(row.day, "strftime")
                else str(row.day)[:10]
            )
            data.append(
                [
                    day_str,
                    str(row.ward_id or ""),
                    f"{row.avg_aqi:.0f}" if row.avg_aqi else "—",
                    f"{row.max_aqi:.0f}" if row.max_aqi else "—",
                    f"{row.avg_pm25:.1f}" if row.avg_pm25 else "—",
                ]
            )

        table = Table(data, colWidths=[3 * cm, 2.5 * cm, 3 * cm, 3 * cm, 4 * cm])
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e3a5f")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                    (
                        "ROWBACKGROUNDS",
                        (0, 1),
                        (-1, -1),
                        [colors.white, colors.HexColor("#f0f4f8")],
                    ),
                    ("GRID", (0, 0), (-1, -1), 0.3, colors.grey),
                    ("PADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        elements.append(table)
    else:
        elements.append(
            Paragraph("No AQI data found for this period.", styles["Normal"])
        )

    doc.build(elements)
    return buffer.getvalue()
