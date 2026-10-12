"""Print the backend OpenAPI document as deterministic JSON (no services needed).

    python -m app.tools.dump_openapi > openapi.json

Used by the frontend/backend contract drift check (frontend/scripts/contract-check.mjs).
"""

import json
import sys

from app.main import app


def main() -> None:
    json.dump(app.openapi(), sys.stdout, indent=1, sort_keys=True)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
