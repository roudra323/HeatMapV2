"""Alchemy adapter (``alchemy_getAssetTransfers`` + standard JSON-RPC)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import httpx

from heatmap_core.config import Chain
from heatmap_core.primitives import (
    NATIVE_TOKEN,
    NULL_ADDRESS,
    TransferCategory,
    normalize_address,
)
from heatmap_core.providers._http import send_json
from heatmap_core.providers.base import RawTransfer, TransferPage, TransferRequest
from heatmap_core.providers.errors import (
    AuthError,
    QuotaExceededError,
    RateLimitedError,
    TransientProviderError,
    UnsupportedError,
)

# Networks where Alchemy serves the "internal" category.
INTERNAL_SUPPORTED = {"eth-mainnet", "eth-sepolia", "eth-holesky", "polygon-mainnet"}
DIRECTIONS = ("fromAddress", "toAddress")
PAGE_SIZE = 1000


class AlchemyProvider:
    name = "alchemy"

    def __init__(self, client: httpx.Client, base_url: str | None = None) -> None:
        self._client = client
        self._base_url = base_url or "https://{network}.g.alchemy.com/v2/{key}"

    def supports(self, chain: Chain) -> bool:
        return chain.config.alchemy_network is not None

    def _url(self, key: str, chain: Chain) -> str:
        network = chain.config.alchemy_network
        if network is None:
            raise UnsupportedError(f"alchemy has no network configured for {chain.name}")
        return self._base_url.format(network=network, key=key)

    def _rpc(self, key: str, chain: Chain, method: str, params: list[Any]) -> Any:
        payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
        body = send_json(self._client, "POST", self._url(key, chain), json=payload)
        if not isinstance(body, dict):
            raise TransientProviderError("unexpected JSON-RPC response")
        error = body.get("error")
        if error:
            raise _map_rpc_error(error)
        return body.get("result")

    def _categories(self, chain: Chain) -> list[str]:
        categories = ["external", "erc20", "erc721", "erc1155"]
        if chain.config.alchemy_network in INTERNAL_SUPPORTED:
            categories.insert(1, "internal")
        return categories

    def fetch_transfers_page(self, key: str, request: TransferRequest) -> TransferPage:
        cursor = request.cursor or {"direction": 0, "page_key": None}
        direction = int(cursor["direction"])
        params: dict[str, Any] = {
            "fromBlock": hex(request.from_block),
            "toBlock": hex(request.to_block),
            DIRECTIONS[direction]: request.address,
            "category": self._categories(request.chain),
            "withMetadata": True,
            "excludeZeroValue": False,
            "maxCount": hex(PAGE_SIZE),
            "order": "asc",
        }
        if cursor.get("page_key"):
            params["pageKey"] = cursor["page_key"]

        result = self._rpc(key, request.chain, "alchemy_getAssetTransfers", [params])
        if not isinstance(result, dict):
            raise TransientProviderError("missing result")

        transfers: list[RawTransfer] = []
        for item in result.get("transfers", []):
            # A self-transfer appears in both directions; keep it from the first only.
            if (
                direction == 1
                and (item.get("from") or "").lower() == request.address
                and (item.get("to") or "").lower() == request.address
            ):
                continue
            transfers.extend(_parse_transfer(item, request.chain.chain_id))

        page_key = result.get("pageKey")
        next_cursor: dict[str, Any] | None
        if page_key:
            next_cursor = {"direction": direction, "page_key": page_key}
        elif direction + 1 < len(DIRECTIONS):
            next_cursor = {"direction": direction + 1, "page_key": None}
        else:
            next_cursor = None
        return TransferPage(transfers=transfers, next_cursor=next_cursor)

    def latest_block(self, key: str, chain: Chain) -> int:
        return int(self._rpc(key, chain, "eth_blockNumber", []), 16)

    def get_code(self, key: str, chain: Chain, address: str) -> str:
        return str(self._rpc(key, chain, "eth_getCode", [address, "latest"]))

    def get_transaction_count(self, key: str, chain: Chain, address: str) -> int:
        return int(self._rpc(key, chain, "eth_getTransactionCount", [address, "latest"]), 16)

    def get_logs(
        self, key: str, chain: Chain, from_block: int, to_block: int, topics: list[Any]
    ) -> list[dict[str, Any]]:
        params = {"fromBlock": hex(from_block), "toBlock": hex(to_block), "topics": topics}
        result = self._rpc(key, chain, "eth_getLogs", [params])
        if not isinstance(result, list):
            raise TransientProviderError("eth_getLogs returned no list")
        return result

    def get_block(self, key: str, chain: Chain, number: int) -> dict[str, Any]:
        result = self._rpc(key, chain, "eth_getBlockByNumber", [hex(number), True])
        if not isinstance(result, dict):
            raise TransientProviderError(f"block {number} not available yet")
        return result

    def eth_call(self, key: str, chain: Chain, to: str, data: str) -> str:
        return str(self._rpc(key, chain, "eth_call", [{"to": to, "data": data}, "latest"]))


def _map_rpc_error(error: Any) -> Exception:
    code = error.get("code") if isinstance(error, dict) else None
    message = str(error.get("message", error) if isinstance(error, dict) else error)
    lowered = message.lower()
    # The per-second limit says "compute units per second capacity", so check it
    # before the monthly "capacity limit" or the key is benched for the whole day.
    if "per second" in lowered or "rate limit" in lowered or "throughput" in lowered:
        return RateLimitedError(message)
    if "capacity" in lowered or "monthly" in lowered or "quota" in lowered:
        return QuotaExceededError(message)
    if code == 429:
        return RateLimitedError(message)
    if code in (401, 403) or "api key" in lowered or "unauthorized" in lowered:
        return AuthError(message)
    if code == -32602:
        return UnsupportedError(message)
    return TransientProviderError(message)


def _hex_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    text = str(value)
    return int(text, 16) if text.startswith("0x") else int(text)


def _log_index(unique_id: str | None) -> int | None:
    # uniqueId looks like "<hash>:log:<index>" for token transfers.
    if unique_id and ":log:" in unique_id:
        try:
            return int(unique_id.rsplit(":", 1)[1])
        except ValueError:
            return None
    return None


def _parse_transfer(item: dict[str, Any], chain_id: int) -> list[RawTransfer]:
    category = TransferCategory(item["category"])
    raw = item.get("rawContract") or {}
    token_address = raw.get("address")
    common: dict[str, Any] = {
        "chain_id": chain_id,
        "tx_hash": item["hash"].lower(),
        "block_number": int(item["blockNum"], 16),
        "block_time": datetime.fromisoformat(
            item["metadata"]["blockTimestamp"].replace("Z", "+00:00")
        ),
        "category": category,
        "from_address": normalize_address(item["from"]),
        # Contract creations have no recipient.
        "to_address": normalize_address(item["to"]) if item.get("to") else NULL_ADDRESS,
        "token_address": normalize_address(token_address) if token_address else NATIVE_TOKEN,
        "provider": AlchemyProvider.name,
        "symbol": item.get("asset"),
        "log_index": _log_index(item.get("uniqueId")),
    }

    if category is TransferCategory.ERC1155:
        return [
            RawTransfer(
                **common,
                token_id=str(_hex_int(meta.get("tokenId"))),
                raw_amount=_hex_int(meta.get("value")) or 0,
                decimals=0,
            )
            for meta in item.get("erc1155Metadata") or []
        ]
    if category is TransferCategory.ERC721:
        token_id = _hex_int(item.get("erc721TokenId") or item.get("tokenId"))
        return [
            RawTransfer(
                **common,
                token_id=str(token_id) if token_id is not None else None,
                raw_amount=1,
                decimals=0,
            )
        ]
    return [
        RawTransfer(
            **common,
            raw_amount=_hex_int(raw.get("value")) or 0,
            decimals=_hex_int(raw.get("decimal")) if raw.get("decimal") else None,
        )
    ]
