"""Controlled comparison of two deployed Nugen-aligned models.

Runs identical prompts through both models and records content, confidence,
token usage, and latency for offline scoring. Usage:

    backend/.venv/Scripts/python.exe scripts/nugen_model_compare.py MODEL_A MODEL_B
"""

import asyncio
import json
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.services.nugen import NugenClient  # noqa: E402

SYSTEM = (
    "You are an air-quality intelligence assistant aligned to the Smart City "
    "Air Quality Intelligence Platform (Pune, India). Explain conditions using "
    "ONLY the measurements supplied. Label every figure Observed, Predicted, "
    "Estimated, or Unavailable. Use CPCB/NAAQS bands (Good 0-50, Satisfactory "
    "51-100, Moderate 101-200, Poor 201-300, Very Poor 301-400, Severe 401-500). "
    "Structure: (1) condition summary, (2) health guidance for the audience, "
    "(3) actionable recommendations."
)

SCENARIOS = [
    ("good-aqi", "City: Pune\nMeasurements (Observed): AQI=42, PM2.5=18, PM10=30, NO2=15\nAudience: citizen\nQuestion: Explain today's air quality."),
    ("moderate-aqi", "City: Pune\nMeasurements (Observed): AQI=165, PM2.5=72, PM10=95, NO2=38\nAudience: citizen\nQuestion: Is it safe to jog this morning?"),
    ("poor-aqi", "City: Pune, Ward W07 Hadapsar\nMeasurements (Observed): AQI=245, PM2.5=98, PM10=141, NO2=52\nAudience: citizen\nQuestion: Is it safe for my elderly mother to take a morning walk?"),
    ("severe-aqi", "City: Pune\nMeasurements (Observed): AQI=415, PM2.5=190, PM10=250, NO2=88, CO=3.1\nAudience: citizen\nQuestion: What should my family do today?"),
    ("pm-interpretation", "City: Pune\nMeasurements (Observed): PM2.5=98, PM10=141, AQI=245\nAudience: citizen\nQuestion: Which pollutant is worse right now and what does each mean for health?"),
    ("admin-recs", "City: Pune, Ward W04\nMeasurements (Observed): AQI=278, PM2.5=112, PM10=180, SO2=65\nContext: 3 construction-dust complaints open in W04\nAudience: admin\nQuestion: What pollution-control actions should the ward office take this week?"),
    ("missing-data", "City: Pune\nMeasurements (Observed): none supplied\nAudience: citizen\nQuestion: What is the AQI in Shivajinagar right now?"),
    ("outdoor-activity", "City: Pune\nMeasurements (Observed): AQI=310, PM2.5=135, O3=110\nAudience: citizen\nQuestion: Can my son play cricket outdoors this afternoon?"),
]


async def run_one(client: NugenClient, model: str, prompt: str) -> dict:
    t0 = time.monotonic()
    try:
        r = await client.chat_completion(
            [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}],
            model=model,
            max_tokens=500,
            temperature=0.4,
        )
        return {
            "ok": True,
            "latency_s": round(time.monotonic() - t0, 2),
            "model": r.model,
            "confidence": r.confidence_score,
            "prompt_tokens": r.prompt_tokens,
            "completion_tokens": r.completion_tokens,
            "content": r.content,
        }
    except Exception as e:  # noqa: BLE001 - record, don't abort suite
        return {
            "ok": False,
            "latency_s": round(time.monotonic() - t0, 2),
            "error": f"{type(e).__name__}: {e}",
        }


async def main() -> None:
    model_a, model_b = sys.argv[1], sys.argv[2]
    client = NugenClient()
    results = {}
    for name, prompt in SCENARIOS:
        ra = await run_one(client, model_a, prompt)
        rb = await run_one(client, model_b, prompt)
        results[name] = {"prompt": prompt, model_a: ra, model_b: rb}
        print(f"{name}: A={ra['latency_s']}s conf={ra.get('confidence')} | B={rb['latency_s']}s conf={rb.get('confidence')}", flush=True)
    await client.aclose()
    out = REPO_ROOT / "docs" / "nugen" / "model_comparison_results.json"
    out.write_text(json.dumps({model_a: "A", model_b: "B", "results": results}, indent=1))
    print("saved:", out)


if __name__ == "__main__":
    asyncio.run(main())
