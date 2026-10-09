"""Print an OpenAPI inventory for manual MCP review; never update the allowlist."""

import json

from voice_api.main import app
from voice_api.mcp_server import MANIFEST


def main():
    current = {
        f"{method.upper()} {path}"
        for path, methods in app.openapi()["paths"].items()
        for method in methods
    }
    reviewed = json.loads(MANIFEST.read_text(encoding="utf-8"))
    print(
        json.dumps(
            {
                "unreviewed": sorted(current - reviewed.keys()),
                "removed": sorted(reviewed.keys() - current),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
