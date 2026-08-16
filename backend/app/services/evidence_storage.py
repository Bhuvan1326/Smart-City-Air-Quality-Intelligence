"""
Evidence photo storage — plain local disk.

Free (no S3/GCS bill) and sufficient for a single-server or NFS-backed
deployment. The interface is deliberately narrow (`save_photo` /
`build_url`) so swapping in object storage later (for horizontal scaling)
only touches this one file, not any callers.
"""

from __future__ import annotations

import base64
import binascii
import uuid
from pathlib import Path

from app.core.config import settings
from app.core.sanitization import UnsafeInputError

_ALLOWED_IMAGE_PREFIXES = {
    "data:image/jpeg;base64,": "jpg",
    "data:image/jpg;base64,": "jpg",
    "data:image/png;base64,": "png",
    "data:image/webp;base64,": "webp",
}


def _decode_data_url(data_url: str) -> tuple[bytes, str]:
    for prefix, ext in _ALLOWED_IMAGE_PREFIXES.items():
        if data_url.startswith(prefix):
            b64_payload = data_url[len(prefix) :]
            try:
                raw = base64.b64decode(b64_payload, validate=True)
            except (binascii.Error, ValueError) as e:
                raise UnsafeInputError(f"Malformed base64 image payload: {e}") from e
            return raw, ext
    raise UnsafeInputError(
        "Unsupported or missing image data URL prefix (expected jpeg/png/webp)"
    )


class EvidenceStorage:
    def __init__(self) -> None:
        self.root = Path(settings.MEDIA_ROOT)

    def save_photo(self, action_id: str, data_url: str) -> str:
        """
        Decodes a base64 data-URL photo, validates size/type, writes it to
        disk under MEDIA_ROOT/evidence/{action_id}/, and returns the public
        URL path (MEDIA_URL_PREFIX-relative) to store in
        EnforcementAction.evidence_urls.
        """
        raw, ext = _decode_data_url(data_url)

        max_bytes = int(settings.MAX_EVIDENCE_PHOTO_MB * 1024 * 1024)
        if len(raw) > max_bytes:
            raise UnsafeInputError(
                f"Evidence photo exceeds the {settings.MAX_EVIDENCE_PHOTO_MB}MB limit"
            )

        action_dir = self.root / "evidence" / str(action_id)
        action_dir.mkdir(parents=True, exist_ok=True)

        filename = f"{uuid.uuid4()}.{ext}"
        file_path = action_dir / filename
        file_path.write_bytes(raw)

        return f"{settings.MEDIA_URL_PREFIX}/evidence/{action_id}/{filename}"
