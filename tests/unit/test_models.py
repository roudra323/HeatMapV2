import numpy as np

from heatmap_core.models.anomaly import score_anomalies
from heatmap_core.models.clustering import cluster_wallets
from heatmap_core.models.drift import detect_drift
from heatmap_core.models.matrix import build_matrix
from heatmap_core.models.tags import tag_wallet


def tags(features: dict[str, object]) -> dict[str, str]:
    return {name: reason for name, _, reason in tag_wallet(features)}


def test_tags_fire_with_reasons() -> None:
    result = tags(
        {
            "share_stablecoin": 0.8,
            "volume_usd": 2_500_000,
            "days_since_last": 200,
            "lifespan_days": 400,
            "funder_cluster_size": 6,
            "max_counterparty_jaccard": 0.7,
            "most_similar_wallet": "0xabc",
            "co_timed_wallets": 0,
        }
    )
    assert set(result) == {"stablecoin_heavy", "whale", "dormant", "sybil_suspect"}
    assert result["stablecoin_heavy"] == "80% of transfers are stablecoins"
    assert "0xabc" in result["sybil_suspect"]


def test_single_sybil_signal_is_not_enough() -> None:
    assert "sybil_suspect" not in tags({"funder_cluster_size": 10, "lifespan_days": 100})


def test_tag_scores_are_bounded() -> None:
    for _, score, _ in tag_wallet({"share_cex": 1.0, "volume_usd": 1e12, "lifespan_days": 0}):
        assert 0 <= score <= 1


def population(n: int, seed: int = 0) -> list[dict[str, object]]:
    rng = np.random.default_rng(seed)
    rows: list[dict[str, object]] = []
    for i in range(n):
        group = i % 2
        rows.append(
            {
                "transfer_count": float(rng.integers(5, 15) if group else rng.integers(500, 900)),
                "share_stablecoin": float(rng.uniform(0.8, 1.0) if group else rng.uniform(0, 0.1)),
                "share_nft": float(rng.uniform(0, 0.1) if group else rng.uniform(0.6, 0.9)),
                "community_id": 3,  # identifiers never enter the matrix
            }
        )
    return rows


def test_matrix_excludes_identifiers_and_logs_counts() -> None:
    rows = population(4)
    matrix = build_matrix([f"w{i}" for i in range(4)], rows)
    assert "community_id" not in matrix.columns
    assert matrix.scaled.shape == (4, 3)


def test_clusters_separate_distinct_behaviours() -> None:
    rows = population(60)
    addresses = [f"w{i}" for i in range(60)]
    result = cluster_wallets(build_matrix(addresses, rows), min_cluster_size=5)
    labels = {a.address: a.cluster for a in result.assignments}
    evens = {labels[f"w{i}"] for i in range(0, 60, 2)} - {-1}
    odds = {labels[f"w{i}"] for i in range(1, 60, 2)} - {-1}
    assert evens and odds and evens.isdisjoint(odds)
    assert all(result.profiles.values())


def test_cluster_size_scales_down_for_small_populations() -> None:
    rows = population(30)
    result = cluster_wallets(build_matrix([f"w{i}" for i in range(30)], rows), min_cluster_size=50)
    assert len(result.profiles) >= 2


def test_small_population_falls_back_to_single_cluster() -> None:
    result = cluster_wallets(build_matrix(["a", "b"], population(2)), min_cluster_size=5)
    assert {a.cluster for a in result.assignments} == {0}


def test_anomaly_flags_extreme_wallet() -> None:
    rows = population(40)
    rows.append({"transfer_count": 1e7, "share_stablecoin": 0.5, "share_nft": 0.5})
    addresses = [f"w{i}" for i in range(41)]
    scores = {s.address: s for s in score_anomalies(build_matrix(addresses, rows), 0.05)}
    assert scores["w40"].is_anomaly
    assert scores["w40"].score == max(s.score for s in scores.values())
    assert any("transfer_count" in d for d in scores["w40"].drivers)


def test_drift_detects_changed_wallet() -> None:
    before = {f"w{i}": {"share_nft": 0.1, "transfer_count": 10.0 + i} for i in range(10)}
    after = {k: dict(v) for k, v in before.items()}
    after["w0"] = {"share_nft": 0.95, "transfer_count": 5000.0}
    drifts = {d.address: d for d in detect_drift(before, after, threshold=1.0)}
    assert drifts["w0"].changed
    assert not drifts["w5"].changed
    assert drifts["w0"].top_changes[0].endswith("up")
