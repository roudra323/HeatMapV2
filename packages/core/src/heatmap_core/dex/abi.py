"""Small ABI helpers and Multicall3 batching for read-only contract calls."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from eth_abi.abi import decode, encode
from eth_abi.exceptions import DecodingError
from eth_utils.crypto import keccak

from heatmap_core.config import Chain

# Calls per aggregate3 request; each is a cheap view call.
MULTICALL_BATCH = 300


def selector(signature: str) -> bytes:
    return keccak(text=signature)[:4]


def topic(signature: str) -> str:
    return "0x" + keccak(text=signature).hex()


class ContractReader(Protocol):
    """What contract reads need from the provider layer (``ProviderRouter`` implements it)."""

    def eth_call(self, chain: Chain, to: str, data: str) -> str: ...


@dataclass(frozen=True)
class Call:
    target: str
    data: bytes


AGGREGATE3 = selector("aggregate3((address,bool,bytes)[])")


def multicall(reader: ContractReader, chain: Chain, calls: Sequence[Call]) -> list[bytes | None]:
    """Run ``calls`` through Multicall3; a failed or empty call yields None."""
    results: list[bytes | None] = []
    for start in range(0, len(calls), MULTICALL_BATCH):
        batch = calls[start : start + MULTICALL_BATCH]
        payload = encode(["(address,bool,bytes)[]"], [[(c.target, True, c.data) for c in batch]])
        raw = reader.eth_call(chain, chain.config.multicall3, "0x" + (AGGREGATE3 + payload).hex())
        (decoded,) = decode(["(bool,bytes)[]"], bytes.fromhex(raw.removeprefix("0x")))
        results.extend(data if ok and data else None for ok, data in decoded)
    return results


def decode_address(data: bytes | None) -> str | None:
    if data is None or len(data) < 32:
        return None
    return "0x" + data[12:32].hex()


def decode_uint(data: bytes | None) -> int | None:
    if data is None or len(data) < 32:
        return None
    return int.from_bytes(data[:32], "big")


def decode_text(data: bytes | None) -> str | None:
    """A ``string`` return value, or a ``bytes32`` one as some old tokens (MKR) use."""
    if not data:
        return None
    try:
        (value,) = decode(["string"], data)
        text = str(value)
    except (DecodingError, OverflowError, ValueError):
        text = data[:32].rstrip(b"\x00").decode("utf-8", "ignore")
    text = text.replace("\x00", "").strip()
    return text or None


def decode_values(types: list[str], data: bytes | None) -> tuple[Any, ...] | None:
    if data is None:
        return None
    try:
        return tuple(decode(types, data))
    except (DecodingError, OverflowError, ValueError):
        return None
