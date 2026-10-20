"""Write the OpenAPI document: ``python -m heatmap_api.openapi apps/web/openapi.json``."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from heatmap_api.main import app


def main() -> None:
    spec = json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n"
    if len(sys.argv) > 1:
        Path(sys.argv[1]).write_text(spec)
    else:
        sys.stdout.write(spec)


if __name__ == "__main__":
    main()
