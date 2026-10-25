"""Swap events of Uniswap v2, v3 and v4 (and forks that reuse the same events).

Every swap is reduced to the pool's view: ``delta0``/``delta1`` are what the
pool received of token0/token1 (positive: the trader paid it in, negative: the
trader took it out). v2 reports gross in/out amounts, v3 reports the pool's
view directly, and v4 reports the swapper's view, so its signs are flipped.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from eth_abi.abi import decode
from eth_abi.exceptions import DecodingError

from heatmap_core.dex.abi import topic

V2_SWAP = topic("Swap(address,uint256,uint256,uint256,uint256,address)")
V3_SWAP = topic("Swap(address,address,int256,int256,uint160,uint128,int24)")
V4_SWAP = topic("Swap(bytes32,address,int128,int128,uint160,uint128,int24,uint24)")
SWAP_TOPICS = [V2_SWAP, V3_SWAP, V4_SWAP]


@dataclass(frozen=True)
class SwapLog:
    kind: str  # "v2" | "v3" | "v4"
    pool_id: str  # pool address, or the PoolId for v4
    block_number: int
    tx_hash: str
    log_index: int
    delta0: int
    delta1: int


def parse_swap_log(log: dict[str, Any], v4_pool_manager: str | None) -> SwapLog | None:
    """Decode one ``eth_getLogs`` entry; returns None for anything that is not a real swap.

    A v4 Swap only counts when the configured PoolManager emitted it, since any
    contract can emit an event with the same signature.
    """
    topics = log.get("topics") or []
    if log.get("removed") or not topics:
        return None
    emitter = str(log["address"]).lower()
    try:
        data = bytes.fromhex(str(log["data"]).removeprefix("0x"))
        if topics[0] == V2_SWAP:
            a0_in, a1_in, a0_out, a1_out = decode(["uint256"] * 4, data[:128])
            kind, pool_id, delta0, delta1 = "v2", emitter, a0_in - a0_out, a1_in - a1_out
        elif topics[0] == V3_SWAP:
            a0, a1 = decode(["int256", "int256"], data[:64])
            kind, pool_id, delta0, delta1 = "v3", emitter, a0, a1
        elif topics[0] == V4_SWAP and len(topics) > 1:
            if v4_pool_manager is None or emitter != v4_pool_manager.lower():
                return None
            a0, a1 = decode(["int128", "int128"], data[:64])
            kind, pool_id, delta0, delta1 = "v4", str(topics[1]).lower(), -a0, -a1
        else:
            return None
    except (DecodingError, OverflowError, ValueError):
        return None
    return SwapLog(
        kind=kind,
        pool_id=pool_id,
        block_number=int(log["blockNumber"], 16),
        tx_hash=str(log["transactionHash"]).lower(),
        log_index=int(log["logIndex"], 16),
        delta0=delta0,
        delta1=delta1,
    )


def trade_sides(
    delta0: int, delta1: int, token0: str, token1: str
) -> tuple[str, int, str, int] | None:
    """``(token_in, amount_in, token_out, amount_out)`` from the pool's deltas.

    Returns None unless exactly one token went in and the other came out.
    """
    if delta0 > 0 and delta1 < 0:
        return token0, delta0, token1, -delta1
    if delta1 > 0 and delta0 < 0:
        return token1, delta1, token0, -delta0
    return None
