import pytest

from heatmap_core.config.settings import TrackingConfig
from heatmap_core.ingestion.sync import kind_from_code
from heatmap_core.ingestion.vetting import rejection
from heatmap_core.primitives import AddressKind

DELEGATE = "ab" * 20


@pytest.mark.parametrize(
    ("code", "kind"),
    [
        ("0x", AddressKind.EOA),
        ("0x0", AddressKind.EOA),
        ("", AddressKind.EOA),
        (f"0xef0100{DELEGATE}", AddressKind.EOA),  # EIP-7702 delegated EOA
        (f"0xEF0100{DELEGATE.upper()}", AddressKind.EOA),
        (f"0xef0100{DELEGATE}00", AddressKind.CONTRACT),  # longer: real code
        ("0x6080604052", AddressKind.CONTRACT),
    ],
)
def test_kind_from_code(code: str, kind: AddressKind) -> None:
    assert kind_from_code(code) == kind


def test_rejection_reasons() -> None:
    cfg = TrackingConfig(max_sent_txs=100)
    assert rejection(AddressKind.CONTRACT, None, cfg) == "a contract, not a wallet"
    assert rejection(AddressKind.EOA, 100, cfg) is None
    assert rejection(AddressKind.EOA, 1_234, cfg) == (
        "sent 1,234 transactions (exchange, service or bot)"
    )
