import re

from heatmap_core.entities.labels import read_seed


def test_ethereum_seed_files_ship_with_the_package() -> None:
    labels = read_seed("labels_ethereum.csv")
    tokens = read_seed("tokens_ethereum.csv")
    factories = read_seed("dex_factories_ethereum.csv")
    assert len(labels) > 20 and len(tokens) > 10 and len(factories) >= 3
    assert {f["version"] for f in factories} == {"v2", "v3"}
    for row in labels + tokens + factories:
        assert re.fullmatch(r"0x[0-9a-f]{40}", row["address"]), row
