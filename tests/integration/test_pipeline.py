"""End-to-end: seed -> sync -> normalize -> graph -> features -> models."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from heatmap_core.config import Settings
from heatmap_core.db.models import WalletFeatureSnapshot, WalletLabel
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
from heatmap_core.primitives import TransferCategory
from tests.support import FakeSource, addr, ethereum, raw

USDC = "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48"
BINANCE = "0x28c6c06298d514db089934071355e5743bf21d60"
START = datetime(2026, 1, 1, tzinfo=UTC)
FUNDER = addr(0xF0)  # private funder shared by every seed
SEEDS = [addr(i) for i in range(1, 6)]


def build_source() -> FakeSource:
    transfers = []
    block = 1
    seeds = SEEDS
    for seed in seeds:
        transfers.append(raw(block, FUNDER, seed, time=START))
        transfers.append(raw(block + 1, BINANCE, seed, time=START + timedelta(hours=1)))
        block += 2
        for k in range(6):
            transfers.append(
                raw(
                    block,
                    seed,
                    addr(0x100 + k % 2),
                    category=TransferCategory.ERC20,
                    token=USDC,
                    symbol="USDC",
                    decimals=6,
                    amount=50_000_000,
                    time=START + timedelta(days=k, hours=seeds.index(seed)),
                )
            )
            block += 1
    # neighbour 0x100 also trades on its own
    for k in range(3):
        transfers.append(raw(block, addr(0x100), addr(0x200), time=START + timedelta(days=10 + k)))
        block += 1
    return FakeSource(transfers, head=10_000)


def test_full_pipeline(engine: Engine, session: Session) -> None:
    chain = ethereum()
    settings = Settings(
        expansion={"min_interactions": 2, "window_days": 100_000},
        features={"windows": ["30d", "all"], "min_transfers": 2},
        pricing={"enabled": False},
    )
    seed_reference_data(engine, chain)
    with session_scope(engine) as s:
        for seed in SEEDS:
            add_seed(s, 1, seed)
    source = build_source()

    assert sync_tracked_wallets(engine, source, chain).synced == 5
    normalize(engine, chain, settings, None)
    graph = refresh_graph(engine, chain, settings)
    assert graph["neighbours_added"] == 2  # the two USDC recipients; Binance is below min

    # neighbours are synced on the next run
    assert sync_tracked_wallets(engine, source, chain).synced == 7
    normalize(engine, chain, settings, None)
    refresh_graph(engine, chain, settings)

    first = compute_behaviour(engine, chain, settings, START + timedelta(days=20))
    assert first.wallets_by_window["all"] == 7
    snapshot = session.scalars(
        select(WalletFeatureSnapshot).where(
            WalletFeatureSnapshot.address == addr(1), WalletFeatureSnapshot.window == "all"
        )
    ).one()
    f = snapshot.features
    assert f["share_stablecoin"] > 0.7 and f["funded_by"] == FUNDER
    assert f["funder_cluster_size"] == 5
    # all seeds were funded by FUNDER inside one co-timing bucket
    assert f["co_timed_wallets"] == 4 and f["max_counterparty_jaccard"] == 1.0
    assert snapshot.volume_usd is not None and float(snapshot.volume_usd) == 300.0

    compute_behaviour(engine, chain, settings, START + timedelta(days=21))
    result = label_wallets(engine, chain, settings)
    assert result.snapshot_at == START + timedelta(days=21)

    labels = session.scalars(select(WalletLabel).where(WalletLabel.address == addr(1))).all()
    kinds = {(lab.kind, lab.label) for lab in labels}
    assert ("tag", "stablecoin_heavy") in kinds
    assert ("tag", "sybil_suspect") in kinds  # shared funder + identical counterparties
    assert any(k == "cluster" for k, _ in kinds)
    assert any(k == "drift" for k, _ in kinds)

    # re-running models for the same snapshot replaces, not duplicates
    before = len(session.scalars(select(WalletLabel)).all())
    label_wallets(engine, chain, settings)
    session.expire_all()
    assert len(session.scalars(select(WalletLabel)).all()) == before
