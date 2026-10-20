"""Provider protocol and the normalised transfer record every adapter returns."""

from __future__ import annotations

import hashlib
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol

from heatmap_core.config import Chain
from heatmap_core.primitives import TransferCategory


@dataclass
class RawTransfer:
    chain_id: int
    tx_hash: str
    block_number: int
    block_time: datetime
    category: TransferCategory
    from_address: str
    to_address: str
    token_address: str
    raw_amount: int
    provider: str
    token_id: str | None = None
    decimals: int | None = None
    symbol: str | None = None
    token_name: str | None = None
    log_index: int | None = None
    uid: str = ""

    def content_key(self) -> str:
        """Identity built only from on-chain facts every provider agrees on."""
        return "|".join(
            [
                str(self.chain_id),
                self.tx_hash,
                self.category.value,
                self.from_address,
                self.to_address,
                self.token_address,
                self.token_id or "",
                str(self.raw_amount),
            ]
        )


def assign_uids(transfers: list[RawTransfer]) -> list[RawTransfer]:
    """Give each transfer a provider-independent id.

    Identical transfers inside one transaction (same parties, token and amount)
    are told apart by an ordinal; because they are identical, which one gets
    which ordinal does not matter.
    """
    seen: Counter[str] = Counter()
    for transfer in transfers:
        key = transfer.content_key()
        ordinal = seen[key]
        seen[key] += 1
        digest = hashlib.sha256(key.encode()).hexdigest()[:40]
        transfer.uid = f"{digest}-{ordinal}"
    return transfers


@dataclass
class TransferPage:
    transfers: list[RawTransfer]
    next_cursor: dict[str, Any] | None = None


@dataclass
class TransferRequest:
    chain: Chain
    address: str
    from_block: int
    to_block: int
    cursor: dict[str, Any] | None = field(default=None)


class TransferProvider(Protocol):
    """A data source. Adapters are stateless with respect to keys: the router passes one in."""

    name: str

    def supports(self, chain: Chain) -> bool: ...

    def fetch_transfers_page(self, key: str, request: TransferRequest) -> TransferPage:
        """Return one page of transfers in which ``address`` is sender or recipient.

        ``request.cursor`` is ``None`` for the first page and otherwise a value
        this same provider returned as ``next_cursor``. A provider must not
        return the same transfer twice across the pages of one request.
        """
        ...

    def latest_block(self, key: str, chain: Chain) -> int: ...

    def get_code(self, key: str, chain: Chain, address: str) -> str: ...
