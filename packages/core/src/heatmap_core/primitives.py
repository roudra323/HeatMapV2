"""Chain-agnostic primitives shared across modules."""

from __future__ import annotations

import re
from enum import StrEnum

NULL_ADDRESS = "0x0000000000000000000000000000000000000000"
# Conventional pseudo-address for a chain's native asset (ETH on Ethereum).
NATIVE_TOKEN = "0xeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"

_ADDRESS_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")


class InvalidAddressError(ValueError):
    pass


def normalize_address(address: str) -> str:
    """Return the lowercase form of an EVM address, validating its shape."""
    value = address.strip()
    if not _ADDRESS_RE.match(value):
        raise InvalidAddressError(f"not an EVM address: {address!r}")
    return value.lower()


def is_address(value: str | None) -> bool:
    return bool(value) and bool(_ADDRESS_RE.match(value or ""))


class TransferCategory(StrEnum):
    EXTERNAL = "external"
    INTERNAL = "internal"
    ERC20 = "erc20"
    ERC721 = "erc721"
    ERC1155 = "erc1155"

    @property
    def is_nft(self) -> bool:
        return self in (TransferCategory.ERC721, TransferCategory.ERC1155)

    @property
    def is_native(self) -> bool:
        return self in (TransferCategory.EXTERNAL, TransferCategory.INTERNAL)


class AddressKind(StrEnum):
    UNKNOWN = "unknown"
    EOA = "eoa"
    CONTRACT = "contract"


class EntityCategory(StrEnum):
    CEX = "cex"
    DEX_ROUTER = "dex_router"
    BRIDGE = "bridge"
    TOKEN = "token"
    NFT_MARKETPLACE = "nft_marketplace"
    LENDING = "lending"
    MIXER = "mixer"
    PROTOCOL = "protocol"
    SYSTEM = "system"
    SETTLEMENT = "settlement"  # intent/solver settlement: the signer is not the trader
    OTHER = "other"


class TokenCategory(StrEnum):
    NATIVE = "native"
    STABLECOIN = "stablecoin"
    WRAPPED = "wrapped"
    LIQUID_STAKING = "liquid_staking"
    DEFI = "defi"
    MEME = "meme"
    NFT = "nft"
    OTHER = "other"


class WatchOrigin(StrEnum):
    SEED = "seed"
    NEIGHBOUR = "neighbour"
    TRADER = "trader"  # promoted from DEX trade discovery


class LabelKind(StrEnum):
    TAG = "tag"
    CLUSTER = "cluster"
    ANOMALY = "anomaly"
    DRIFT = "drift"
