from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from heatmap_core.db.models import SyncCursor, Token, Transfer, Wallet
from heatmap_core.ingestion.sync import classify_addresses, sync_wallet
from heatmap_core.primitives import AddressKind, TransferCategory
from tests.support import FakeSource, addr, ethereum, raw

WALLET = addr(1)
TOKEN = addr(0xA0)


def count(session: Session) -> int:
    return session.scalar(select(func.count()).select_from(Transfer)) or 0


def test_initial_sync_stores_transfers_tokens_wallets(engine: Engine, session: Session) -> None:
    source = FakeSource(
        [
            raw(10, addr(2), WALLET),
            raw(
                20,
                WALLET,
                addr(3),
                category=TransferCategory.ERC20,
                token=TOKEN,
                symbol="USDC",
                decimals=6,
                amount=2_500_000,
            ),
            raw(30, addr(4), addr(5)),  # unrelated
        ],
        head=100,
    )
    result = sync_wallet(engine, source, ethereum(), WALLET)

    assert (result.fetched, result.inserted) == (2, 2)
    assert count(session) == 2
    usdc = session.scalars(select(Transfer).where(Transfer.token_address == TOKEN)).one()
    assert str(usdc.amount) == "2.500000000000000000"
    token = session.get(Token, (1, TOKEN))
    assert token is not None and token.symbol == "USDC" and token.decimals == 6
    wallet = session.get(Wallet, (1, WALLET))
    assert wallet is not None and wallet.first_seen_at < wallet.last_seen_at
    cursor = session.get(SyncCursor, (1, WALLET))
    assert cursor is not None and cursor.last_block == 100


def test_resync_is_idempotent_and_incremental(engine: Engine, session: Session) -> None:
    source = FakeSource([raw(10, addr(2), WALLET)], head=100)
    sync_wallet(engine, source, ethereum(), WALLET)
    source.transfers.append(raw(150, WALLET, addr(3)))
    source.head = 200

    result = sync_wallet(engine, source, ethereum(), WALLET)

    # re-scans the reorg window (10 blocks) before the cursor, then moves on
    assert source.calls[-1] == (WALLET, 91, 200)
    assert result.inserted == 1
    assert count(session) == 2


def test_reorged_transfer_is_removed(engine: Engine, session: Session) -> None:
    source = FakeSource([raw(95, addr(2), WALLET), raw(50, addr(2), WALLET)], head=100)
    sync_wallet(engine, source, ethereum(), WALLET)
    source.transfers = [t for t in source.transfers if t.block_number != 95]  # orphaned block

    result = sync_wallet(engine, source, ethereum(), WALLET)

    assert result.removed == 1
    assert [t.block_number for t in session.scalars(select(Transfer))] == [50]


def test_chunks_commit_cursor_progressively(engine: Engine, session: Session) -> None:
    source = FakeSource([raw(5, addr(2), WALLET), raw(25, addr(2), WALLET)], head=30)
    sync_wallet(engine, source, ethereum(sync_block_chunk=10), WALLET)
    assert [c[1:] for c in source.calls] == [(0, 9), (10, 19), (20, 29), (30, 30)]
    assert count(session) == 2


def test_confirmations_hold_back_recent_blocks(engine: Engine, session: Session) -> None:
    source = FakeSource([raw(95, addr(2), WALLET)], head=100)
    sync_wallet(engine, source, ethereum(confirmations=12), WALLET)
    assert count(session) == 0
    cursor = session.get(SyncCursor, (1, WALLET))
    assert cursor is not None and cursor.last_block == 88


def test_classify_addresses(engine: Engine, session: Session) -> None:
    source = FakeSource()
    source.contracts.add(addr(9))
    kinds = classify_addresses(engine, source, ethereum(), [addr(8), addr(9)])
    assert kinds == {addr(8): AddressKind.EOA, addr(9): AddressKind.CONTRACT}
    # already classified addresses are not queried again
    assert classify_addresses(engine, source, ethereum(), [addr(8)]) == {}
