"""Spam and address-poisoning heuristics.

Token-level rules (a token is spam everywhere):
- ``non_ascii_symbol``: homoglyph look-alikes such as "ETH" spelt with Cyrillic letters.
- ``promo_text``: URLs or claim/airdrop bait in the name or symbol.
- ``impersonates:<SYM>``: reuses a verified token's symbol from another contract.

Transfer-level rules:
- ``spam_token``: the token is spam.
- ``zero_value``: fungible transfer of 0 not sent by the tracked wallet
  (the classic ``transferFrom(victim, attacker, 0)`` poisoning).
- ``lookalike_address``: counterparty shares the first and last 4 hex chars
  with an address the wallet really transacted with, but is a different address.
- ``mass_airdrop``: unverified token sent to many recipients in one transaction.

Verified tokens are never flagged at token level.
"""

from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal

from heatmap_core.config.settings import SpamConfig
from heatmap_core.primitives import NATIVE_TOKEN, TransferCategory

_PROMO = re.compile(
    r"(https?://|www\.|\.(com|org|io|net|xyz|app|site|top|fi)\b|t\.me/|"
    r"\bclaim\b|\bvisit\b|\bairdrop\b|\breward|\bvoucher\b|\bgift\b)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class TokenInfo:
    address: str
    symbol: str | None
    name: str | None
    is_verified: bool


@dataclass
class TransferInfo:
    id: int
    tx_hash: str
    category: str
    from_address: str
    to_address: str
    token_address: str
    raw_amount: Decimal


def _ascii_fold(text: str) -> str:
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()


def token_spam_reason(
    token: TokenInfo, verified_symbols: dict[str, str], config: SpamConfig
) -> str | None:
    if token.is_verified or token.address == NATIVE_TOKEN:
        return None
    symbol = token.symbol or ""
    name = token.name or ""
    if config.flag_non_ascii_symbols and any(ord(c) > 127 for c in symbol):
        return "non_ascii_symbol"
    if _PROMO.search(symbol) or _PROMO.search(name):
        return "promo_text"
    folded = _ascii_fold(symbol).strip().upper()
    impersonated = verified_symbols.get(folded)
    if impersonated is not None and impersonated != token.address:
        return f"impersonates:{folded}"
    return None


def lookalike(a: str, b: str) -> bool:
    return a != b and a[2:6] == b[2:6] and a[-4:] == b[-4:]


def transfer_spam_reasons(
    transfers: Iterable[TransferInfo],
    tracked: set[str],
    spam_tokens: set[str],
    verified_tokens: set[str],
    real_counterparties: dict[str, set[str]],
    config: SpamConfig,
    recipient_counts: dict[tuple[str, str], int] | None = None,
) -> dict[int, str]:
    """Return ``{transfer_id: reason}`` for spam transfers.

    ``real_counterparties`` maps a tracked wallet to addresses it sent value to,
    which is what poisoners imitate. ``recipient_counts`` maps
    ``(tx_hash, token)`` to the number of distinct recipients known for it;
    when omitted it is counted from ``transfers``.
    """
    reasons: dict[int, str] = {}
    items = list(transfers)

    if recipient_counts is None:
        recipients: dict[tuple[str, str], set[str]] = defaultdict(set)
        for t in items:
            recipients[(t.tx_hash, t.token_address)].add(t.to_address)
        recipient_counts = {k: len(v) for k, v in recipients.items()}

    for t in items:
        category = TransferCategory(t.category)
        if t.token_address in spam_tokens:
            reasons[t.id] = "spam_token"
            continue
        if (
            config.flag_zero_value
            and not category.is_native
            and not category.is_nft
            and t.raw_amount == 0
            and t.from_address not in tracked
        ):
            reasons[t.id] = "zero_value"
            continue
        if (
            t.token_address not in verified_tokens
            and recipient_counts.get((t.tx_hash, t.token_address), 0)
            >= config.airdrop_min_recipients
        ):
            reasons[t.id] = "mass_airdrop"
            continue
        for wallet, other in ((t.to_address, t.from_address), (t.from_address, t.to_address)):
            if wallet in tracked and any(
                lookalike(other, real) for real in real_counterparties.get(wallet, ())
            ):
                reasons[t.id] = "lookalike_address"
                break
    return reasons
