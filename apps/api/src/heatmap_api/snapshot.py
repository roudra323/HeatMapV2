"""Export API responses as static JSON for the web app's demo mode.

    uv run python -m heatmap_api.snapshot apps/web/public/demo

Runs the API in-process against ``HEATMAP_DATABASE_URL`` (normally a database
loaded with ``heatmap demo``), so the files hold exactly what the API returns.
Lists are exported whole and filtered, sorted and paged by the web app
(``apps/web/src/lib/demo.ts``). Every wallet the UI can reach gets one file
with all of its responses.
"""

from __future__ import annotations

import json
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from heatmap_api.main import app

WINDOWS = ("7d", "30d", "90d", "all")
DEPTHS = (1, 2)
PAGE = 500  # the API's largest page


def _get(client: TestClient, path: str, **query: Any) -> dict[str, Any]:
    res = client.get(path, params=query)
    return {"status": res.status_code, "body": res.json() if res.content else None}


def _all(client: TestClient, path: str, **query: Any) -> list[Any]:
    items: list[Any] = []
    while True:
        res = client.get(path, params={**query, "limit": PAGE, "offset": len(items)})
        if res.status_code != 200:
            return items
        page = res.json()
        items += page["items"]
        if len(items) >= page["total"] or not page["items"]:
            return items


def _ok(client: TestClient, path: str, **query: Any) -> Any:
    res = client.get(path, params=query)
    res.raise_for_status()
    return res.json()


def _wallet(client: TestClient, address: str) -> dict[str, Any] | None:
    base = f"/v1/wallets/{address}"
    profiles = {w: _get(client, base, window=w) for w in WINDOWS}
    trades = _all(client, f"{base}/trades")
    transfers = _all(client, f"{base}/transfers")
    if all(p["status"] == 404 for p in profiles.values()) and not trades and not transfers:
        return None
    return {
        "profile": profiles,
        "heatmap": _get(client, f"{base}/heatmap", days=365),
        "timeline": _get(client, f"{base}/timeline", bucket="week", days=365),
        "neighbors": {str(d): _get(client, f"{base}/neighbors", depth=d, limit=30) for d in DEPTHS},
        "similar": _get(client, f"{base}/similar", limit=8),
        "trades": trades,
        "transfers": transfers,
    }


def export(out: Path) -> dict[str, int]:
    client = TestClient(app)
    if out.exists():
        shutil.rmtree(out)
    (out / "wallets").mkdir(parents=True)

    def write(name: str, data: Any) -> None:
        (out / name).write_text(json.dumps(data, separators=(",", ":")))

    traders = _all(client, "/v1/traders", include_bots=True, sort="volume")
    watchlist = _all(client, "/v1/watchlist")
    write("meta.json", {"generated_at": datetime.now(UTC).isoformat(), "chain": "ethereum"})
    write("chains.json", _ok(client, "/v1/chains"))
    write("traders.json", traders)
    write("watchlist.json", watchlist)
    write("tags.json", _ok(client, "/v1/tags"))
    write("clusters.json", _ok(client, "/v1/clusters"))
    write("cluster-points.json", _ok(client, "/v1/clusters/points"))
    for by in ("cluster", "tag"):
        write(f"segments-{by}.json", _ok(client, "/v1/heatmaps/segments", by=by))

    listed = sorted({t["address"] for t in traders} | {w["address"] for w in watchlist})
    queue, seen, wallets = list(listed), set(listed), 0
    # Wallets in the listed wallets' neighbour graphs are one click away: export those too.
    for i, address in enumerate(queue):
        data = _wallet(client, address)
        if data is None:
            continue
        write(f"wallets/{address}.json", data)
        wallets += 1
        if i >= len(listed):
            continue
        for network in data["neighbors"].values():
            nodes = network["body"]["nodes"] if network["status"] == 200 else []
            for node in nodes:
                # hubs (routers, exchanges) hold huge histories and are not wallets anyone tracks
                if not node["is_hub"] and node["address"] not in seen:
                    seen.add(node["address"])
                    queue.append(node["address"])
    return {"traders": len(traders), "watchlist": len(watchlist), "wallets": wallets}


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit("usage: python -m heatmap_api.snapshot OUT_DIR")
    print(json.dumps(export(Path(sys.argv[1]))))


if __name__ == "__main__":
    main()
