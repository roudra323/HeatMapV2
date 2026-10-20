import re

from heatmap_core.entities.labels import _read_seed


def test_ethereum_seed_files_ship_with_the_package() -> None:
    labels = _read_seed("labels_ethereum.csv")
    tokens = _read_seed("tokens_ethereum.csv")
    assert len(labels) > 20 and len(tokens) > 10
    for row in labels + tokens:
        assert re.fullmatch(r"0x[0-9a-f]{40}", row["address"]), row
