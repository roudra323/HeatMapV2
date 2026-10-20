from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from heatmap_core.config import Settings
from heatmap_core.db.models import Edge, WalletCommunity, WatchlistEntry
from heatmap_core.db.session import session_scope
from heatmap_core.entities.labels import load_seed_labels, load_seed_tokens
from heatmap_core.graph.communities import detect_communities
from heatmap_core.graph.edges import rebuild_edges
from heatmap_core.graph.ego import ego_network
from heatmap_core.graph.expansion import expand_neighbours
from heatmap_core.ingestion.sync import sync_wallet
from heatmap_core.ingestion.watchlist import active_addresses, add_seed
from heatmap_core.normalize.run import normalize_pending
from heatmap_core.primitives import TransferCategory
from tests.support import FakeSource, addr, ethereum, raw

SEED = addr(1)
A, B, C, D = addr(0xA), addr(0xB), addr(0xC), addr(0xD)
BINANCE = "0x28c6c06298d514db089934071355e5743bf21d60"
SPAM_TOKEN = addr(0x5BA)


def scenario() -> FakeSource:
    t = []
    block = 1
    for counterparty, n in ((A, 3), (B, 2), (C, 1), (BINANCE, 5)):
        for _ in range(n):
            t.append(raw(block, SEED, counterparty))
            block += 1
    for _ in range(4):  # spam token sender should never become a neighbour
        t.append(
            raw(
                block,
                addr(0xE),
                SEED,
                category=TransferCategory.ERC20,
                token=SPAM_TOKEN,
                symbol="ЕТН",
                decimals=18,
            )
        )
        block += 1
    for _ in range(2):  # A's own counterparty, reachable at hop 2
        t.append(raw(block, A, D))
        block += 1
    return FakeSource(t, head=500)


def settings(**expansion: object) -> Settings:
    return Settings(
        expansion={
            "min_interactions": 2,
            "top_n_per_wallet": 10,
            "window_days": 100_000,
            **expansion,
        }
    )


def run_pipeline(engine: Engine, source: FakeSource, cfg: Settings) -> None:
    chain = ethereum()
    with session_scope(engine) as s:
        wallets = active_addresses(s, 1)
    for wallet in wallets:
        sync_wallet(engine, source, chain, wallet)
    normalize_pending(engine, chain, cfg)
    rebuild_edges(engine, 1)


def setup(engine: Engine) -> None:
    with session_scope(engine) as s:
        load_seed_labels(s, ethereum())
        load_seed_tokens(s, ethereum())
        add_seed(s, 1, SEED)


def test_edges_exclude_spam(engine: Engine, session: Session) -> None:
    setup(engine)
    run_pipeline(engine, scenario(), settings())
    edges = {(e.src, e.dst): e.tx_count for e in session.scalars(select(Edge))}
    assert edges[(SEED, A)] == 3
    assert (addr(0xE), SEED) not in edges


def test_expansion_skips_hubs_spam_and_weak_links(engine: Engine, session: Session) -> None:
    setup(engine)
    source = scenario()
    cfg = settings()
    run_pipeline(engine, source, cfg)

    result = expand_neighbours(engine, ethereum(), cfg)

    assert set(result.added) == {A, B}
    assert BINANCE in result.skipped_hubs
    entry = session.get(WatchlistEntry, (1, A))
    assert entry is not None and (entry.hop, entry.via_address, entry.origin) == (
        1,
        SEED,
        "neighbour",
    )
    # max_hops=1: running again after syncing neighbours adds nothing new
    run_pipeline(engine, source, cfg)
    assert expand_neighbours(engine, ethereum(), cfg).added == []


def test_second_hop_and_budget(engine: Engine, session: Session) -> None:
    setup(engine)
    source = scenario()
    cfg = settings(max_hops=2)
    run_pipeline(engine, source, cfg)
    expand_neighbours(engine, ethereum(), cfg)
    run_pipeline(engine, source, cfg)  # syncs A and B
    result = expand_neighbours(engine, ethereum(), cfg)
    assert result.added == [D]
    d = session.get(WatchlistEntry, (1, D))
    assert d is not None and (d.hop, d.via_address) == (2, A)


def test_budget_caps_neighbours(engine: Engine) -> None:
    setup(engine)
    cfg = settings(max_total_neighbours=1)
    run_pipeline(engine, scenario(), cfg)
    result = expand_neighbours(engine, ethereum(), cfg)
    assert result.added == [A] and result.capped


def test_ego_network_and_communities(engine: Engine, session: Session) -> None:
    setup(engine)
    cfg = settings()
    source = scenario()
    run_pipeline(engine, source, cfg)
    expand_neighbours(engine, ethereum(), cfg)
    run_pipeline(engine, source, cfg)

    assert detect_communities(engine, 1) >= 1
    assert session.get(WalletCommunity, (1, BINANCE)) is None  # hubs excluded

    network = ego_network(session, 1, SEED, depth=2)
    nodes = {n.address: n for n in network.nodes}
    assert nodes[SEED].depth == 0
    assert nodes[BINANCE].is_hub and nodes[BINANCE].label == "Binance 14"
    assert nodes[A].tracked and nodes[A].hop == 1
    assert nodes[D].depth == 2
    assert {(e.src, e.dst) for e in network.edges} >= {(SEED, A), (A, D)}
