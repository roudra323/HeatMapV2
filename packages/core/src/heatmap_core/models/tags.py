"""Explainable behaviour tags from feature snapshots.

Each rule returns ``(score, reason)`` when it fires; scores are in [0, 1] and
say how strongly the evidence exceeds the threshold.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

Features = dict[str, Any]
RuleResult = tuple[float, str] | None


def _f(features: Features, name: str, default: float = 0.0) -> float:
    value = features.get(name)
    return float(value) if isinstance(value, int | float) else default


def _strength(value: float, threshold: float, full: float) -> float:
    if full <= threshold:
        return 1.0
    return max(0.0, min(1.0, 0.5 + 0.5 * (value - threshold) / (full - threshold)))


def _share_rule(feature: str, threshold: float, label: str) -> Callable[[Features], RuleResult]:
    def rule(f: Features) -> RuleResult:
        share = _f(f, feature)
        if share >= threshold:
            return _strength(share, threshold, 1.0), f"{share:.0%} of transfers are {label}"
        return None

    return rule


def whale(f: Features) -> RuleResult:
    volume = _f(f, "volume_usd")
    if volume >= 1_000_000:
        return _strength(volume, 1_000_000, 50_000_000), f"${volume:,.0f} moved"
    return None


def bot_like(f: Features) -> RuleResult:
    regularity = _f(f, "gap_regularity")
    per_day = _f(f, "tx_per_active_day")
    tx = _f(f, "tx_count")
    if tx >= 50 and (regularity >= 0.6 or per_day >= 100):
        return (
            max(_strength(regularity, 0.6, 1.0), _strength(per_day, 100, 1000)),
            f"{regularity:.0%} of gaps are near-identical, {per_day:.0f} tx per active day",
        )
    return None


def dormant(f: Features) -> RuleResult:
    days = _f(f, "days_since_last")
    if days >= 90:
        return _strength(days, 90, 365), f"inactive for {days:.0f} days"
    return None


def new_wallet(f: Features) -> RuleResult:
    lifespan = _f(f, "lifespan_days", default=1e9)
    if lifespan < 30:
        return 1.0 - lifespan / 30 * 0.5, f"first and last activity {lifespan:.0f} days apart"
    return None


def distributor(f: Features) -> RuleResult:
    out_degree = _f(f, "out_degree")
    if out_degree >= 50 and _f(f, "out_share") >= 0.8:
        return _strength(out_degree, 50, 500), f"sends to {out_degree:.0f} distinct addresses"
    return None


def collector(f: Features) -> RuleResult:
    in_degree = _f(f, "in_degree")
    if in_degree >= 50 and _f(f, "out_share") <= 0.2:
        return _strength(in_degree, 50, 500), f"receives from {in_degree:.0f} distinct addresses"
    return None


def sybil_suspect(f: Features) -> RuleResult:
    funders = _f(f, "funder_cluster_size")
    jaccard = _f(f, "max_counterparty_jaccard")
    co_timed = _f(f, "co_timed_wallets")
    signals = []
    if funders >= 5:
        signals.append(f"shares its first funder with {funders - 1:.0f} tracked wallets")
    if jaccard >= 0.5:
        signals.append(f"{jaccard:.0%} counterparty overlap with {f.get('most_similar_wallet')}")
    if co_timed >= 3:
        signals.append(f"acts in lockstep with {co_timed:.0f} tracked wallets")
    if len(signals) >= 2:
        return min(1.0, 0.4 * len(signals)), "; ".join(signals)
    return None


def mixer_exposure(f: Features) -> RuleResult:
    share = _f(f, "share_mixer")
    if share > 0:
        return min(1.0, 0.5 + share * 5), f"{share:.1%} of transfers touch a mixer"
    return None


@dataclass(frozen=True)
class TagRule:
    name: str
    evaluate: Callable[[Features], RuleResult]


RULES: tuple[TagRule, ...] = (
    TagRule("stablecoin_heavy", _share_rule("share_stablecoin", 0.5, "stablecoins")),
    TagRule("nft_trader", _share_rule("share_nft", 0.3, "NFTs")),
    TagRule("meme_trader", _share_rule("share_meme", 0.3, "meme tokens")),
    TagRule("liquid_staker", _share_rule("share_liquid_staking", 0.2, "liquid staking tokens")),
    TagRule("dex_trader", _share_rule("share_dex_router", 0.2, "with DEX routers")),
    TagRule("cex_user", _share_rule("share_cex", 0.2, "with exchanges")),
    TagRule("bridge_user", _share_rule("share_bridge", 0.05, "with bridges")),
    TagRule("lending_user", _share_rule("share_lending", 0.05, "with lending markets")),
    TagRule("whale", whale),
    TagRule("bot_like", bot_like),
    TagRule("dormant", dormant),
    TagRule("new_wallet", new_wallet),
    TagRule("distributor", distributor),
    TagRule("collector", collector),
    TagRule("sybil_suspect", sybil_suspect),
    TagRule("mixer_exposure", mixer_exposure),
)


def tag_wallet(features: Features) -> list[tuple[str, float, str]]:
    tags = []
    for rule in RULES:
        outcome = rule.evaluate(features)
        if outcome is not None:
            score, reason = outcome
            tags.append((rule.name, round(score, 4), reason))
    return tags
