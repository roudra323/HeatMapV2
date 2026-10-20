from datetime import UTC, datetime

from heatmap_core.primitives import NATIVE_TOKEN, TransferCategory
from heatmap_core.providers import RawTransfer, assign_uids


def make(provider: str, amount: int = 1) -> RawTransfer:
    return RawTransfer(
        chain_id=1,
        tx_hash="0x01",
        block_number=1,
        block_time=datetime(2026, 1, 1, tzinfo=UTC),
        category=TransferCategory.ERC20,
        from_address="0x" + "a" * 40,
        to_address="0x" + "b" * 40,
        token_address=NATIVE_TOKEN,
        raw_amount=amount,
        provider=provider,
    )


def test_uid_independent_of_provider() -> None:
    (a,) = assign_uids([make("alchemy")])
    (b,) = assign_uids([make("etherscan")])
    assert a.uid == b.uid


def test_identical_transfers_in_one_tx_get_distinct_uids() -> None:
    uids = [t.uid for t in assign_uids([make("x"), make("x"), make("x", amount=2)])]
    assert len(set(uids)) == 3
    assert uids[0].endswith("-0") and uids[1].endswith("-1")
