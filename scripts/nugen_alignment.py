from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.services.nugen import NugenClient, NugenError  # noqa: E402

DOMAIN_DIR = REPO_ROOT / "docs" / "nugen" / "domain"
ALIGNMENT_NAME = "airiq-air-quality-intelligence"
SMOKE_MESSAGES = [
    {
        "role": "system",
        "content": "You are an air-quality analyst for the Pune platform. "
        "Cite data labels (Observed/Predicted/Estimated) and CPCB AQI bands.",
    },
    {
        "role": "user",
        "content": "City: Pune\nMeasurements (Observed): AQI=165, PM2.5=72, "
        "NO2=38\nAudience: citizen\nQuestion: Is it safe to jog this morning?",
    },
]


def _pick_base_model(models: list[dict]) -> dict | None:
    ready = [m for m in models if m.get("alignment_ready")]
    if not ready:
        return None

    def size(m: dict) -> float:
        try:
            return float(str(m.get("parameters", "99")).rstrip("Bb")) or 99.0
        except ValueError:
            return 99.0

    return sorted(ready, key=size)[0]


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-model")
    parser.add_argument("--smoke-only", action="store_true")
    parser.add_argument("--timeout-minutes", type=int, default=120)
    args = parser.parse_args()

    client = NugenClient()
    if not client.configured:
        print("ERROR: NUGEN_API_KEY is not set (check .env or environment).")
        return 2

    if args.smoke_only:
        from app.core.config import settings

        model_id = settings.NUGEN_ALIGNED_MODEL_ID
        if not model_id:
            print("ERROR: NUGEN_ALIGNED_MODEL_ID not set for --smoke-only.")
            return 2
        return await _smoke(client, model_id)

    # 1. Base models
    models = await client.list_base_models()
    print(f"base models: {len(models)}")
    for m in models:
        print(
            f"  {m.get('model_id')}  ready={m.get('alignment_ready')}"
            f"  on_request={m.get('available_on_request')}"
        )
    base_id = args.base_model or (m := _pick_base_model(models)) and m["model_id"]
    if not base_id:
        print("ERROR: no alignment-ready base model on this account.")
        return 2
    print(f"selected base model: {base_id}")

    # 2. Existing alignment projects — reuse rather than duplicate
    projects = await client.list_alignment_projects()
    reusable = next(
        (
            p
            for p in projects
            if p.get("name") == ALIGNMENT_NAME
            and p.get("status") in ("QUEUED", "PROCESSING", "READY")
        ),
        None,
    )
    if reusable:
        alignment_id = reusable.get("alignment_id") or reusable.get("id")
        print(f"reusing alignment project {alignment_id} ({reusable.get('status')})")
    else:
        # 3. Upload domain documents
        files = [
            (p.name, p.read_bytes()) for p in sorted(DOMAIN_DIR.glob("*.md"))
        ]
        if not files:
            print(f"ERROR: no domain docs in {DOMAIN_DIR}")
            return 2
        doc_ids = await client.upload_documents(
            files, names=[f[0] for f in files]
        )
        print(f"uploaded {len(doc_ids)} documents: {doc_ids}")

        # 4. Create alignment
        resp = await client.create_alignment(
            name=ALIGNMENT_NAME,
            base_model_id=base_id,
            document_ids=doc_ids,
            description="Air-quality intelligence: CPCB/NAAQS bands, "
            "pollutant health guidance, Pune platform domain rules.",
        )
        alignment_id = resp.get("alignment_id")
        print(f"alignment project created: {alignment_id} ({resp.get('status')})")

    # 5. Poll
    deadline = time.time() + args.timeout_minutes * 60
    status = "QUEUED"
    while time.time() < deadline:
        info = await client.alignment_status(alignment_id)
        status = info.get("status", status)
        progress = info.get("progress") or info.get("score") or ""
        print(f"alignment {alignment_id}: {status} {progress}")
        if status in ("READY", "FAILED", "STOPPED"):
            break
        await asyncio.sleep(30)
    if status != "READY":
        print(f"ERROR: alignment ended in {status}")
        return 2

    # 6. Find the aligned model id
    aligned = await client.list_aligned_models()
    model = next(
        (m for m in aligned if alignment_id in str(m)), None
    ) or (aligned[-1] if aligned else None)
    if not model:
        print("ERROR: alignment READY but no aligned model listed yet — "
              "re-run after a minute.")
        return 2
    model_id = model.get("model_id")
    print(f"aligned model: {model_id} (deployment={model.get('deployment_status')})")

    # 7. Deploy
    if model.get("deployment_status") != "DEPLOYED":
        await client.deploy_model(model_id)
        for _ in range(40):
            st = await client.deployment_status(model_id)
            print(f"deployment: {st.get('status')} {st.get('error') or ''}")
            if st.get("status") in ("DEPLOYED", "UNDEPLOYED"):
                break
            await asyncio.sleep(15)
        if st.get("status") != "DEPLOYED":
            print(f"ERROR: deployment ended in {st.get('status')}")
            return 2

    # 8. Smoke inference
    rc = await _smoke(client, model_id)
    if rc == 0:
        print(f"\nSet in .env:  NUGEN_ALIGNED_MODEL_ID={model_id}")
    return rc


async def _smoke(client: NugenClient, model_id: str) -> int:
    try:
        result = await client.chat_completion(
            SMOKE_MESSAGES, model=model_id, max_tokens=300
        )
    except NugenError as e:
        print(f"SMOKE FAILED: {e}")
        return 1
    print("=== smoke inference (deployed aligned model) ===")
    print(f"model: {result.model}  confidence: {result.confidence_score}")
    print(result.content[:800])
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
