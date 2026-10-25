"""Etherscan V2 adapter (one endpoint, ``chainid`` selects the network)."""

from __future__ import annotations

from datetime import UTC, datetime
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

ACTIONS: tuple[tuple[str, TransferCategory], ...] = (
    ("txlist", TransferCategory.EXTERNAL),
    ("txlistinternal", TransferCategory.INTERNAL),
    ("tokentx", TransferCategory.ERC20),
    ("tokennfttx", TransferCategory.ERC721),
    ("token1155tx", TransferCategory.ERC1155),
)
PAGE_SIZE = 1000
EMPTY_MESSAGES = ("no transactions found", "no records found")


class EtherscanProvider:
    name = "etherscan"

    def __init__(self, client: httpx.Client, base_url: str | None = None) -> None:
        self._client = client
        self._base_url = base_url or "https://api.etherscan.io/v2/api"

    def supports(self, chain: Chain) -> bool:
        return True

    def _get(self, key: str, chain: Chain, params: dict[str, Any]) -> Any:
        query = {"chainid": chain.chain_id, "apikey": key, **params}
        body = send_json(self._client, "GET", self._base_url, params=query)
        if not isinstance(body, dict):
            raise TransientProviderError("unexpected response")
        if "jsonrpc" in body:  # proxy module
            if body.get("error"):
                raise _map_message(str(body["error"].get("message", body["error"])))
            return body.get("result")
        if str(body.get("status")) == "1":
            return body.get("result")
        result = body.get("result")
        message = f"{body.get('message', '')} {result if isinstance(result, str) else ''}"
        if any(m in message.lower() for m in EMPTY_MESSAGES):
            return []
        raise _map_message(message.strip())

    def fetch_transfers_page(self, key: str, request: TransferRequest) -> TransferPage:
        """Pages by block range: each page ends before its last (possibly partial) block.

        Etherscan caps ``page * offset`` at 10,000, so instead of page numbers we
        move ``startblock`` forward. Rows from the last block of a full page are
        dropped and fetched again with the next page, so no block is split.
        """
        cursor = request.cursor or {"action": 0, "startblock": request.from_block, "page": 1}
        action_idx = int(cursor["action"])
        start_block = int(cursor["startblock"])
        page = int(cursor.get("page", 1))
        action, category = ACTIONS[action_idx]

        rows = self._get(
            key,
            request.chain,
            {
                "module": "account",
                "action": action,
                "address": request.address,
                "startblock": start_block,
                "endblock": request.to_block,
                "page": page,
                "offset": PAGE_SIZE,
                "sort": "asc",
            },
        )
        rows = rows if isinstance(rows, list) else []

        next_action = (
            {"action": action_idx + 1, "startblock": request.from_block, "page": 1}
            if action_idx + 1 < len(ACTIONS)
            else None
        )
        if len(rows) < PAGE_SIZE:
            keep, next_cursor = rows, next_action
        else:
            last_block = int(rows[-1]["blockNumber"])
            keep = [r for r in rows if int(r["blockNumber"]) < last_block]
            if keep:
                next_cursor = {"action": action_idx, "startblock": last_block, "page": 1}
            else:  # one block holds a whole page: fall back to page numbers
                keep = rows
                next_cursor = {"action": action_idx, "startblock": start_block, "page": page + 1}

        transfers = [
            t for row in keep if (t := _parse_row(row, category, request.chain)) is not None
        ]
        return TransferPage(transfers=transfers, next_cursor=next_cursor)

    def latest_block(self, key: str, chain: Chain) -> int:
        result = self._get(key, chain, {"module": "proxy", "action": "eth_blockNumber"})
        return int(str(result), 16)

    def get_code(self, key: str, chain: Chain, address: str) -> str:
        result = self._get(
            key,
            chain,
            {"module": "proxy", "action": "eth_getCode", "address": address, "tag": "latest"},
        )
        return str(result)

    def get_transaction_count(self, key: str, chain: Chain, address: str) -> int:
        result = self._get(
            key,
            chain,
            {
                "module": "proxy",
                "action": "eth_getTransactionCount",
                "address": address,
                "tag": "latest",
            },
        )
        return int(str(result), 16)

    def get_logs(
        self, key: str, chain: Chain, from_block: int, to_block: int, topics: list[Any]
    ) -> list[dict[str, Any]]:
        # The logs module takes one topic0 per request and pages at 1,000 rows.
        raise UnsupportedError("etherscan does not serve multi-topic log scans")

    def get_block(self, key: str, chain: Chain, number: int) -> dict[str, Any]:
        result = self._get(
            key,
            chain,
            {
                "module": "proxy",
                "action": "eth_getBlockByNumber",
                "tag": hex(number),
                "boolean": "true",
            },
        )
        if not isinstance(result, dict):
            raise TransientProviderError(f"block {number} not available yet")
        return result

    def eth_call(self, key: str, chain: Chain, to: str, data: str) -> str:
        result = self._get(
            key,
            chain,
            {"module": "proxy", "action": "eth_call", "to": to, "data": data, "tag": "latest"},
        )
        return str(result)


def _map_message(message: str) -> Exception:
    lowered = message.lower()
    if "daily" in lowered and "limit" in lowered:
        return QuotaExceededError(message)
    if "rate limit" in lowered or "max calls per sec" in lowered:
        return RateLimitedError(message)
    if "invalid api key" in lowered or "missing/invalid api key" in lowered:
        return AuthError(message)
    return TransientProviderError(message or "etherscan error")


def _addr(value: str | None) -> str:
    return normalize_address(value) if value else NULL_ADDRESS


def _parse_row(row: dict[str, Any], category: TransferCategory, chain: Chain) -> RawTransfer | None:
    if str(row.get("isError", "0")) == "1":
        return None  # reverted calls move no value

    to_address = row.get("to") or row.get("contractAddress")
    common: dict[str, Any] = {
        "chain_id": chain.chain_id,
        "tx_hash": str(row["hash"]).lower(),
        "block_number": int(row["blockNumber"]),
        "block_time": datetime.fromtimestamp(int(row["timeStamp"]), tz=UTC),
        "category": category,
        "from_address": _addr(row.get("from")),
        "to_address": _addr(to_address),
        "provider": EtherscanProvider.name,
        "log_index": int(row["logIndex"]) if row.get("logIndex") not in (None, "") else None,
    }

    if category.is_native:
        return RawTransfer(
            **common,
            token_address=NATIVE_TOKEN,
            raw_amount=int(row.get("value") or 0),
            decimals=chain.config.native_decimals,
            symbol=chain.config.native_symbol,
        )

    token: dict[str, Any] = {
        "token_address": _addr(row.get("contractAddress")),
        "symbol": row.get("tokenSymbol") or None,
        "token_name": row.get("tokenName") or None,
    }
    if category is TransferCategory.ERC20:
        decimals = row.get("tokenDecimal")
        return RawTransfer(
            **common,
            **token,
            raw_amount=int(row.get("value") or 0),
            decimals=int(decimals) if decimals not in (None, "") else None,
        )
    if category is TransferCategory.ERC721:
        return RawTransfer(
            **common, **token, token_id=str(row.get("tokenID")), raw_amount=1, decimals=0
        )
    return RawTransfer(
        **common,
        **token,
        token_id=str(row.get("tokenID")),
        raw_amount=int(row.get("tokenValue") or 0),
        decimals=0,
    )
