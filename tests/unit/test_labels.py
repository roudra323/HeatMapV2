from pathlib import Path

import pytest

from heatmap_core.entities.labels import classify_category, read_label_file
from heatmap_core.primitives import EntityCategory


@pytest.mark.parametrize(
    ("texts", "expected"),
    [
        (("cex",), EntityCategory.CEX),
        (("Exchange",), EntityCategory.CEX),
        ((None, "Binance Hot Wallet 3"), EntityCategory.CEX),
        (("DEX Aggregator",), EntityCategory.DEX_ROUTER),
        (("", "Uniswap V3: Router 2"), EntityCategory.DEX_ROUTER),
        (("Bridge",), EntityCategory.BRIDGE),
        ((None, "Tornado.Cash: Router"), EntityCategory.MIXER),  # mixer wins over router
        (("nft marketplace",), EntityCategory.NFT_MARKETPLACE),
        (("fund",), EntityCategory.OTHER),
    ],
)
def test_classify_category(texts: tuple[str | None, ...], expected: EntityCategory) -> None:
    assert classify_category(*texts) == expected


def test_read_label_file_csv_and_json(tmp_path: Path) -> None:
    csv_file = tmp_path / "labels.csv"
    csv_file.write_text("Address,Label\n0xabc,Foo\n")
    assert read_label_file(csv_file) == [{"Address": "0xabc", "Label": "Foo"}]

    json_file = tmp_path / "labels.json"
    json_file.write_text('[{"address": "0xabc"}, "junk"]')
    assert read_label_file(json_file) == [{"address": "0xabc"}]

    json_file.write_text('{"0xabc": "Foo"}')
    with pytest.raises(ValueError, match="JSON list"):
        read_label_file(json_file)
