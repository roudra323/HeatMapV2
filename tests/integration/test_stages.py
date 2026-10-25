"""Stage locking, scoped syncs, vetting, counterparty classification and funding sources."""

from sqlalchemy import Engine, select, update
from sqlalchemy.orm import Session

from heatmap_core.config import Settings
from heatmap_core.config.settings import TrackingConfig
from heatmap_core.db.models import Transfer, Wallet, WalletFeatureSnapshot, WatchlistEntry
from heatmap_core.db.session import session_scope
from heatmap_core.entities.labels import load_seed_tokens
from heatmap_core.ingestion.sync import classify_counterparties, sync_wallet
from heatmap_core.ingestion.watchlist import add_seed
from heatmap_core.normalize.run import update_funding_sources
from heatmap_core.pipeline import (
    compute_behaviour,
    normalize,
    refresh_graph,
    stage_lock,
    sync_tracked_wallets,
)
from heatmap_core.primitives import NULL_ADDRESS, TransferCategory, WatchOrigin
from tests.support import FakeSource, addr, ethereum, raw

WALLET = addr(1)
USDC = "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48"


def test_sync_is_skipped_while_another_run_holds_the_lock(engine: Engine) -> None:
    with session_scope(engine) as s:
        add_seed(s, 1, WALLET)
    source = FakeSource([raw(1, addr(2), WALLET)], head=10)

    with stage_lock(engine, "sync", 1) as acquired:
        assert acquired
        result = sync_tracked_wallets(engine, source, ethereum())
    assert result.skipped and source.calls == []

    # Released afterwards; other chains and stages were never blocked.
    assert not sync_tracked_wallets(engine, source, ethereum()).skipped
    with stage_lock(engine, "sync", 1) as a, stage_lock(engine, "sync", 2) as b:
        assert a and b


def test_only_new_syncs_wallets_without_a_cursor(engine: Engine) -> None:
    other = addr(2)
    with session_scope(engine) as s:
        add_seed(s, 1, WALLET)
    source = FakeSource([raw(1, addr(3), WALLET), raw(2, addr(3), other)], head=10)
    sync_wallet(engine, source, ethereum(), WALLET)
    with session_scope(engine) as s:
        add_seed(s, 1, other)
    source.calls.clear()

    result = sync_tracked_wallets(engine, source, ethereum(), only_new=True)

    assert result.synced == 1
    assert {address for address, _, _ in source.calls} == {other}


def test_counterparties_classified_from_data_then_get_code(
    engine: Engine, session: Session
) -> None:
    router, eoa, contract, spammer = addr(0x10), addr(0x11), addr(0x12), addr(0x13)
    with session_scope(engine) as s:
        add_seed(s, 1, WALLET)
        load_seed_tokens(s, ethereum())
    source = FakeSource(
        [
            # Internal transfers prove nothing: EIP-7702 delegated EOAs send them too.
            raw(1, router, WALLET, category=TransferCategory.INTERNAL),
            raw(2, WALLET, USDC, category=TransferCategory.ERC20, token=USDC),  # token contract
            raw(3, WALLET, eoa),
            raw(4, WALLET, eoa),
            raw(5, WALLET, contract),
            raw(6, NULL_ADDRESS, WALLET),
            raw(7, spammer, WALLET),
        ],
        head=10,
    )
    source.contracts = {contract, router}
    sync_wallet(engine, source, ethereum(), WALLET)
    with session_scope(engine) as s:
        s.execute(update(Transfer).where(Transfer.from_address == spammer).values(is_spam=True))

    classified = classify_counterparties(engine, source, ethereum(), budget=1)

    kinds = dict(session.execute(select(Wallet.address, Wallet.kind)).tuples().all())
    assert kinds[USDC] == "contract"
    # budget 1: the most frequent unknown counterparty first, the rest next run
    assert kinds[eoa] == "eoa"
    assert kinds[router] == "unknown" and kinds[contract] == "unknown"
    assert kinds[NULL_ADDRESS] == "unknown" and kinds[spammer] == "unknown"
    assert classified == 2

    classify_counterparties(engine, source, ethereum(), budget=10)
    session.expire_all()
    for address in (router, contract):
        assert session.get(Wallet, (1, address)).kind == "contract"  # type: ignore[union-attr]


def test_funding_source_follows_spam_flags(engine: Engine, session: Session) -> None:
    first, second = addr(0xF1), addr(0xF2)
    with session_scope(engine) as s:
        add_seed(s, 1, WALLET)
    source = FakeSource([raw(1, first, WALLET), raw(2, second, WALLET)], head=10)
    sync_wallet(engine, source, ethereum(), WALLET)
    with session_scope(engine) as s:
        s.execute(update(Transfer).values(normalized_at=Transfer.ingested_at))
        assert update_funding_sources(s, 1) == 1
    assert session.get(Wallet, (1, WALLET)).funded_by == first  # type: ignore[union-attr]

    with session_scope(engine) as s:
        s.execute(update(Transfer).where(Transfer.from_address == first).values(is_spam=True))
        assert update_funding_sources(s, 1) == 1
        assert update_funding_sources(s, 1) == 0
    session.expire_all()
    assert session.get(Wallet, (1, WALLET)).funded_by == second  # type: ignore[union-attr]

    with session_scope(engine) as s:
        s.execute(update(Transfer).values(is_spam=True))
        update_funding_sources(s, 1)
    session.expire_all()
    assert session.get(Wallet, (1, WALLET)).funded_by is None  # type: ignore[union-attr]


def test_features_skip_tracked_wallets_that_are_hubs(engine: Engine, session: Session) -> None:
    busy, person = addr(0xB0), addr(0xB1)
    with session_scope(engine) as s:
        add_seed(s, 1, busy)
        add_seed(s, 1, person)
    # busy pays four different wallets; person only deals with busy
    transfers = [raw(n, busy, addr(0x900 + n)) for n in range(1, 5)]
    transfers += [raw(5, person, busy), raw(6, busy, person), raw(7, person, busy)]
    source = FakeSource(transfers, head=10)
    for wallet in (busy, person):
        sync_wallet(engine, source, ethereum(), wallet)
    settings = Settings(
        expansion={"hub_degree_threshold": 3, "min_interactions": 1},
        features={"min_transfers": 1, "windows": ["all"]},
        pricing={"enabled": False},
    )
    normalize(engine, ethereum(), settings, None)
    refresh_graph(engine, ethereum(), settings)

    compute_behaviour(engine, ethereum(), settings)

    rows = session.scalars(select(WalletFeatureSnapshot.address)).all()
    assert rows == [person]  # busy has 5 counterparties > 3: a hub, not a person


def test_automatic_wallets_are_vetted_before_their_first_sync(
    engine: Engine, session: Session
) -> None:
    seed, trader, pool, exchange, delegated = (addr(n) for n in range(0xD0, 0xD5))
    with session_scope(engine) as s:
        add_seed(s, 1, seed)  # added by hand: never checked
        s.add(WatchlistEntry(chain_id=1, address=trader, origin=WatchOrigin.TRADER))
        for address in (pool, exchange, delegated):
            s.add(
                WatchlistEntry(
                    chain_id=1,
                    address=address,
                    origin=WatchOrigin.NEIGHBOUR,
                    hop=1,
                    note="via test" if address == exchange else None,
                )
            )
    wallets = (seed, trader, pool, exchange, delegated)
    source = FakeSource([raw(n, addr(0x99), w) for n, w in enumerate(wallets, start=1)], head=10)
    source.contracts = {pool}
    source.codes = {delegated: "0xef0100" + "ab" * 20}  # EIP-7702: an EOA with delegated code
    source.sent = {seed: 50_000, trader: 300, exchange: 20_000, delegated: 12}
    tracking = TrackingConfig(max_sent_txs=10_000)

    result = sync_tracked_wallets(engine, source, ethereum(), tracking=tracking)

    assert (result.vetted, result.rejected, result.synced) == (4, 2, 3)
    assert {address for address, _, _ in source.calls} == {seed, trader, delegated}
    entries = {e.address: e for e in session.scalars(select(WatchlistEntry))}
    assert not entries[pool].active
    assert entries[pool].note == "Not tracked: a contract, not a wallet"
    assert not entries[exchange].active
    assert entries[exchange].note == (
        "via test · Not tracked: sent 20,000 transactions (exchange, service or bot)"
    )
    assert entries[seed].active and seed not in source.checked
    kinds = {w.address: (w.kind, w.sent_txs) for w in session.scalars(select(Wallet))}
    assert kinds[delegated] == ("eoa", 12) and kinds[trader] == ("eoa", 300)
    assert kinds[pool] == ("contract", None)

    source.checked.clear()
    again = sync_tracked_wallets(engine, source, ethereum(), tracking=tracking)
    assert again.vetted == 0 and source.checked == []  # each wallet is checked once


def test_unvetted_wallets_wait_while_the_provider_is_down(engine: Engine) -> None:
    neighbour = addr(0xE1)
    with session_scope(engine) as s:
        add_seed(s, 1, WALLET)
        s.add(WatchlistEntry(chain_id=1, address=neighbour, origin=WatchOrigin.NEIGHBOUR, hop=1))
    source = FakeSource([raw(1, addr(2), WALLET), raw(2, addr(2), neighbour)], head=10)
    source.down = True

    result = sync_tracked_wallets(engine, source, ethereum(), tracking=TrackingConfig())

    assert result.vetted == 0 and result.synced == 1
    assert {address for address, _, _ in source.calls} == {WALLET}

    source.down = False
    result = sync_tracked_wallets(
        engine, source, ethereum(), only_new=True, tracking=TrackingConfig()
    )
    assert (result.vetted, result.rejected, result.synced) == (1, 0, 1)
    assert {address for address, _, _ in source.calls} == {WALLET, neighbour}
