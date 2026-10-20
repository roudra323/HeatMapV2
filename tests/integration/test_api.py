from collections.abc import Iterator
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from heatmap_api.main import create_app
from heatmap_core.config import Settings
from heatmap_core.db.session import session_scope
from heatmap_core.ingestion.watchlist import add_seed
from heatmap_core.pipeline import (
    compute_behaviour,
    label_wallets,
    normalize,
    refresh_graph,
    seed_reference_data,
    sync_tracked_wallets,
)
from tests.integration.test_pipeline import BINANCE, SEEDS, START, build_source
from tests.support import addr, ethereum

SETTINGS = Settings(
    chains={"ethereum": {"chain_id": 1}},
    expansion={"min_interactions": 2, "window_days": 100_000},
    features={"windows": ["30d", "all"], "min_transfers": 2},
    pricing={"enabled": False},
)


@pytest.fixture
def client(engine: Engine) -> Iterator[TestClient]:
    with TestClient(create_app(SETTINGS, engine)) as c:
        yield c


@pytest.fixture
def populated(engine: Engine) -> None:
    chain = ethereum()
    seed_reference_data(engine, chain)
    with session_scope(engine) as s:
        for seed in SEEDS:
            add_seed(s, 1, seed)
    source = build_source()
    for _ in range(2):
        sync_tracked_wallets(engine, source, chain)
        normalize(engine, chain, SETTINGS, None)
        refresh_graph(engine, chain, SETTINGS)
    compute_behaviour(engine, chain, SETTINGS, START + timedelta(days=20))
    compute_behaviour(engine, chain, SETTINGS, START + timedelta(days=21))
    label_wallets(engine, chain, SETTINGS)


def test_health_and_chains(client: TestClient) -> None:
    assert client.get("/health").json() == {"status": "ok", "database": "ok"}
    assert client.get("/v1/chains").json()[0]["chain_id"] == 1


def test_watchlist_crud(client: TestClient) -> None:
    address = "0xD8DA6BF26964AF9D7EED9E03E53415D37AA96045"
    created = client.post("/v1/watchlist", json={"address": address, "note": "vitalik"})
    assert created.status_code == 201
    assert created.json()["address"] == address.lower()
    assert created.json()["origin"] == "seed"

    page = client.get("/v1/watchlist").json()
    assert page["total"] == 1 and page["items"][0]["last_block"] is None

    assert client.delete(f"/v1/watchlist/{address}").status_code == 204
    assert client.get("/v1/watchlist", params={"active": True}).json()["total"] == 0
    assert client.delete(f"/v1/watchlist/{addr(99)}").status_code == 404
    assert client.post("/v1/watchlist", json={"address": "0x123"}).status_code == 422


def test_unknown_chain_and_wallet(client: TestClient) -> None:
    assert client.get("/v1/watchlist", params={"chain": "solana"}).status_code == 404
    assert client.get(f"/v1/wallets/{addr(1234)}").status_code == 404
    assert client.get("/v1/wallets/not-an-address").status_code == 422


@pytest.mark.usefixtures("populated")
def test_wallet_profile(client: TestClient) -> None:
    body = client.get(f"/v1/wallets/{SEEDS[0]}").json()
    assert body["watch"]["origin"] == "seed" and body["watch"]["last_block"] > 0
    assert body["funded_by"] == addr(0xF0)
    assert body["summary"]["transfer_count"] > 0
    assert {t["label"] for t in body["tags"]} >= {"stablecoin_heavy", "sybil_suspect"}
    assert body["cluster"]["kind"] == "cluster"
    assert body["drift"]["kind"] == "drift"

    hub = client.get(f"/v1/wallets/{BINANCE}").json()
    assert hub["entity"] == {"name": "Binance 14", "category": "cex", "is_hub": True}


@pytest.mark.usefixtures("populated")
def test_wallet_detail_endpoints(client: TestClient) -> None:
    seed = SEEDS[0]
    features = client.get(f"/v1/wallets/{seed}/features", params={"history": 5}).json()
    assert [f["snapshot_at"][:10] for f in features] == ["2026-01-22", "2026-01-21"]
    assert len(features[0]["features"]["hour_hist"]) == 24

    transfers = client.get(f"/v1/wallets/{seed}/transfers", params={"limit": 3}).json()
    assert transfers["total"] == 8 and len(transfers["items"]) == 3

    network = client.get(f"/v1/wallets/{seed}/neighbors", params={"depth": 2}).json()
    nodes = {n["address"]: n for n in network["nodes"]}
    assert nodes[seed]["depth"] == 0 and nodes[addr(0x100)]["tracked"]
    assert nodes[BINANCE]["is_hub"]

    similar = client.get(f"/v1/wallets/{seed}/similar", params={"limit": 3}).json()
    assert len(similar) == 3 and similar[0]["address"] in SEEDS

    heatmap = client.get(f"/v1/wallets/{seed}/heatmap", params={"days": 3650}).json()
    assert len(heatmap["values"]) == 7 and len(heatmap["values"][0]) == 24
    assert heatmap["meta"]["total"] == 8

    timeline = client.get(
        f"/v1/wallets/{seed}/timeline", params={"bucket": "day", "days": 3650}
    ).json()
    assert sum(b["transfers_in"] + b["transfers_out"] for b in timeline) == 8


@pytest.mark.usefixtures("populated")
def test_analytics_endpoints(client: TestClient) -> None:
    clusters = client.get("/v1/clusters").json()
    assert sum(c["size"] for c in clusters) == 7
    assert len(client.get("/v1/clusters/points").json()) == 7
    assert client.get("/v1/tags").json()["sybil_suspect"] == 5
    segments = client.get("/v1/heatmaps/segments", params={"by": "tag"}).json()
    assert "stablecoin_heavy" in segments["rows"]
    assert len(segments["values"][0]) == len(segments["columns"])


def test_openapi_schema(client: TestClient) -> None:
    paths = client.get("/openapi.json").json()["paths"]
    assert "/v1/wallets/{address}/neighbors" in paths
