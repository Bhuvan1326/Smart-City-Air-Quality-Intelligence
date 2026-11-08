from __future__ import annotations

import re
from dataclasses import dataclass, field

_PM_NUMBERS = [
    ("PM2.5", "pm25", r"pm\s*2\.?5|pm-2\.?5"),
    ("PM10", "pm10", r"pm\s*10|pm-10"),
    ("NO2", "no2", r"no2|nitrogen dioxide"),
    ("SO2", "so2", r"so2|sulfur dioxide|sulphur dioxide"),
    ("CO", "co", r"\bco\b|carbon monoxide"),
    ("O3", "o3", r"o3|ozone"),
]
_NUM = r"(?<![\w.])(\d+(?:\.\d+)?)"
_PM_CANONICAL_UNIT = "µg/m³"

MISSING_DATA_FALLBACK = (
    "Current air-quality measurements are unavailable for this location. "
    "Current AQI and pollutant concentrations cannot be determined without "
    "valid measurement data. CPCB AQI bands for reference: Good 0-50, "
    "Satisfactory 51-100, Moderate 101-200, Poor 201-300, Very Poor 301-400, "
    "Severe 401-500."
)

_SENTENCE_BOUNDARY = re.compile(r"\n|; |! |\? |\. (?=[A-Z*#\-])")


@dataclass
class ValidationResult:
    text: str
    notes: list[str] = field(default_factory=list)
    fallback_used: bool = False


_NAME_ANY = re.compile(
    r"pm\s*2\.?5|pm-2\.?5|pm\s*10|pm-10|no2|nitrogen dioxide|so2|"
    r"sulfur dioxide|sulphur dioxide|\bco\b|carbon monoxide|o3|ozone|aqi",
    re.IGNORECASE,
)
_GAP = r"([^\d\n]{0,40}?)"


def _claim_spans(text: str, name_pattern: str):
    name = rf"(?:{name_pattern})"
    for m in re.finditer(name + _GAP + _NUM, text, re.IGNORECASE):
        gap = m.group(1)
        if not _NAME_ANY.search(gap):
            yield m.span(2), float(m.group(2))


def _aqi_claim_span(text: str):
    m = re.search(r"aqi" + _GAP + _NUM, text, re.IGNORECASE)
    if m and not _NAME_ANY.search(m.group(1)):
        return m.span(2), float(m.group(2))
    return None, None


def _sentence_span(text: str, pos: int):
    start = 0
    for m in _SENTENCE_BOUNDARY.finditer(text[:pos]):
        start = m.end()
    m = _SENTENCE_BOUNDARY.search(text, pos)
    end = m.start() if m else len(text)
    return start, end


def _replace_number(text: str, span, new_value: float) -> str:
    return text[: span[0]] + f"{new_value:g}" + text[span[1] :]


def _deterministic_summary(
    supplied: dict[str, float], aqi: float | None, band: str | None
) -> str:
    parts = ["Current air-quality conditions (Observed):"]
    if aqi is not None:
        aqi_text = f"AQI {aqi:g}"
        if band:
            aqi_text += f" ({band})"
        parts.append(f"- {aqi_text}")
    for display, field_name, _ in _PM_NUMBERS:
        val = supplied.get(field_name)
        unit = "mg/m³" if display == "CO" else _PM_CANONICAL_UNIT
        if val is not None:
            parts.append(f"- {display}: {val:g} {unit}")
    missing = [d for d, f, _ in _PM_NUMBERS if f not in supplied]
    if aqi is None:
        missing.insert(0, "AQI")
    if missing:
        parts.append("Unavailable measurements: " + ", ".join(missing) + ".")
    return "\n".join(parts)


def _scan_claims(text, supplied, aqi_supplied):
    removals, fixes, notes = [], [], []
    if aqi_supplied is not None:
        span, val = _aqi_claim_span(text)
        if span and abs(val - aqi_supplied) > 0.5:
            fixes.append((span, aqi_supplied))
            notes.append(f"AQI {val:g} replaced with validated {aqi_supplied:g}")
    for display, field_name, pat in _PM_NUMBERS:
        supplied_val = supplied.get(field_name)
        for span, val in _claim_spans(text, pat):
            if supplied_val is None:
                removals.append(_sentence_span(text, span[0]))
                notes.append(f"unsupported {display} {val:g} claim removed")
            elif abs(val - supplied_val) > 0.5:
                fixes.append((span, supplied_val))
                notes.append(
                    f"{display} {val:g} replaced with validated " f"{supplied_val:g}"
                )
    for m in re.finditer(
        r"(?:pm\s*2\.?5|pm\s*10|no2|so2|o3)[^\d\n]{0,40}?" + _NUM + r"\s*mg/m\S*",
        text,
        re.IGNORECASE,
    ):
        unit_span = m.span(0)
        i = text.find("mg/m", unit_span[0], unit_span[1])
        if i >= 0:
            fixes.append(((i, i + 4), "µg/m"))
            notes.append("mg/m³ replaced with canonical µg/m³")
    m = re.search(r"aqi[^\d]{0,30}?" + _NUM + r"\s*(µg|ug|mg)/m\S*", text, re.I)
    if m:
        i = m.string.find("/", m.start(), m.end())
        if i >= 0:
            j = m.start(0)
            k = text.rfind("µg", j, i)
            if k < 0:
                k = text.rfind("ug", j, i)
            if k < 0:
                k = text.rfind("mg", j, i)
            if k >= 0:
                end = i + 2
                while end < len(text) and text[end].isdigit():
                    end += 1
                removals.append((k, end))
                notes.append("concentration unit removed from AQI")
    return removals, fixes, notes


def validate_insight_response(
    text: str,
    supplied: dict[str, float],
    aqi_supplied: float | None,
    band: str | None = None,
) -> ValidationResult:
    notes: list[str] = []

    if not supplied and aqi_supplied is None:
        has_claim = _aqi_claim_span(text)[0] is not None or any(
            list(_claim_spans(text, pat)) for _, _, pat in _PM_NUMBERS
        )
        if has_claim:
            return ValidationResult(
                text=MISSING_DATA_FALLBACK,
                notes=["invented measurements removed; unavailable notice used"],
                fallback_used=True,
            )
        return ValidationResult(text=text, notes=notes)

    removals, fixes, notes = _scan_claims(text, supplied, aqi_supplied)

    edits = [(s, v) for s, v in fixes] + [(s, None) for s in removals]
    edits.sort(key=lambda e: e[0][0])
    merged: list[tuple] = []
    for span, val in edits:
        if merged and span[0] < merged[-1][0][1]:
            continue
        merged.append((span, val))
    for (start, end), val in reversed(merged):
        if val is None:
            text = text[:start] + text[end:]
        else:
            replacement = f"{val:g}" if isinstance(val, float) else val
            text = text[:start] + replacement + text[end:]

    removals2, fixes2, _ = _scan_claims(text, supplied, aqi_supplied)
    if removals2 or fixes2 or not text.strip():
        notes.append("response replaced with deterministic validated summary")
        return ValidationResult(
            text=_deterministic_summary(supplied, aqi_supplied, band),
            notes=notes,
            fallback_used=True,
        )
    return ValidationResult(text=text, notes=notes)
