"""Generate the dashboard contract from Pydantic/FastAPI, without loading credentials into it."""

import json
from pathlib import Path

from voice_api.main import app


def main() -> None:
    target = Path(__file__).resolve().parents[1] / "data" / "openapi.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(app.openapi(), indent=2), encoding="utf-8")
    print("Generated data/openapi.json")


if __name__ == "__main__":
    main()
