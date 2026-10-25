"""An in-memory chain that serves swap logs, blocks and Multicall3 reads."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime
from typing import Any

from eth_abi.abi import decode, encode
from eth_utils.crypto import keccak

from heatmap_core.config import Chain
from heatmap_core.dex.abi import AGGREGATE3, selector
from heatmap_core.dex.events import V2_SWAP, V3_SWAP, V4_SWAP
from tests.support import ethereum

POOL_MANAGER = "0x000000000004444c5dc75cb358380d2e3de08a90"
POSITION_MANAGER = "0xbd216513d74c8cf14cf4747e6aaa6420ff64ee9e"
WETH = "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2"
USDC = "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48"
UNI_V2_FACTORY = "0x5c69bee701ef814a2b6a3edd4b1652cb9cc5aa6f"
UNI_V3_FACTORY = "0x1f98431c8ad98523631ae4a59f267346ea31f984"
UNIVERSAL_ROUTER = "0x66a9893cc07d91d95644aedd05d03f95e1dba8af"
COW_SETTLEMENT = "0x9008d19f58aabd9ed0d60971565aa8510560ab41"
V4_KEY_TYPES = ["address", "address", "uint24", "int24", "address"]


def dex_chain() -> Chain:
    return ethereum(
        uniswap_v4_pool_manager=POOL_MANAGER,
        uniswap_v4_position_manager=POSITION_MANAGER,
        wrapped_native=WETH,
    )


def v4_pool_id(key: tuple[str, str, int, int, str]) -> str:
    return "0x" + keccak(encode(V4_KEY_TYPES, list(key))).hex()


def word(address: str) -> bytes:
    return encode(["address"], [address])


class FakeDexChain:
    def __init__(self, head: int) -> None:
        self.head = head
        self.logs: list[dict[str, Any]] = []
        self.blocks: dict[int, dict[str, Any]] = {}
        self.reads: dict[tuple[str, bytes], bytes] = {}
        self.calls: Counter[str] = Counter()
        self._log_index: dict[int, int] = defaultdict(int)

    # chain contents -------------------------------------------------------
    def block(self, number: int, when: datetime) -> None:
        self.blocks[number] = {
            "number": hex(number),
            "timestamp": hex(int(when.timestamp())),
            "transactions": [],
        }

    def tx(self, number: int, tx_hash: str, sender: str, to: str) -> None:
        self.blocks[number]["transactions"].append({"hash": tx_hash, "from": sender, "to": to})

    def _log(self, number: int, tx_hash: str, emitter: str, topics: list[str], data: bytes) -> None:
        index = self._log_index[number]
        self._log_index[number] += 1
        self.logs.append(
            {
                "address": emitter,
                "topics": topics,
                "data": "0x" + data.hex(),
                "blockNumber": hex(number),
                "transactionHash": tx_hash,
                "logIndex": hex(index),
                "removed": False,
            }
        )

    def v2_swap(
        self, number: int, tx_hash: str, pool: str, amounts: tuple[int, int, int, int]
    ) -> None:
        topics = [V2_SWAP, "0x" + word(UNIVERSAL_ROUTER).hex(), "0x" + word(pool).hex()]
        self._log(number, tx_hash, pool, topics, encode(["uint256"] * 4, list(amounts)))

    def v3_swap(self, number: int, tx_hash: str, pool: str, a0: int, a1: int) -> None:
        data = encode(
            ["int256", "int256", "uint160", "uint128", "int24"], [a0, a1, 2**96, 10**18, 0]
        )
        topics = [V3_SWAP, "0x" + word(UNIVERSAL_ROUTER).hex(), "0x" + word(pool).hex()]
        self._log(number, tx_hash, pool, topics, data)

    def v4_swap(
        self, number: int, tx_hash: str, pool_id: str, a0: int, a1: int, emitter: str = POOL_MANAGER
    ) -> None:
        data = encode(
            ["int128", "int128", "uint160", "uint128", "int24", "uint24"],
            [a0, a1, 2**96, 10**18, 0, 500],
        )
        topics = [V4_SWAP, pool_id, "0x" + word(UNIVERSAL_ROUTER).hex()]
        self._log(number, tx_hash, emitter, topics, data)

    def answer(self, target: str, signature: str, args: bytes, result: bytes) -> None:
        self.reads[(target.lower(), selector(signature) + args)] = result

    # DexSource ------------------------------------------------------------
    def latest_block(self, chain: Chain) -> int:
        return self.head

    def get_logs(
        self, chain: Chain, from_block: int, to_block: int, topics: list[Any]
    ) -> list[dict[str, Any]]:
        self.calls["get_logs"] += 1
        return [
            entry
            for entry in self.logs
            if from_block <= int(entry["blockNumber"], 16) <= to_block
            and entry["topics"][0] in topics[0]
        ]

    def get_block(self, chain: Chain, number: int) -> dict[str, Any]:
        self.calls["get_block"] += 1
        return self.blocks[number]

    def eth_call(self, chain: Chain, to: str, data: str) -> str:
        self.calls["eth_call"] += 1
        raw = bytes.fromhex(data.removeprefix("0x"))
        assert to == chain.config.multicall3 and raw[:4] == AGGREGATE3
        (calls,) = decode(["(address,bool,bytes)[]"], raw[4:])
        results = []
        for target, _allow_failure, call_data in calls:
            answer = self.reads.get((str(target).lower(), bytes(call_data)))
            results.append((answer is not None, answer or b""))
        return "0x" + encode(["(bool,bytes)[]"], [results]).hex()
