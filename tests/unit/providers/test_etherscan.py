from __future__ import annotations

from typing import Any

import httpx
import pytest
import respx

from heatmap_core.primitives import NATIVE_TOKEN, NULL_ADDRESS, TransferCategory
from heatmap_core.providers import (
    AuthError,
    EtherscanProvider,
    QuotaExceededError,
    RateLimitedError,
    TransferRequest,
)
from heatmap_core.providers import etherscan as etherscan_module
from tests.support import ethereum

URL = "https://api.etherscan.io/v2/api"
WALLET = "0x" + "a" * 40
OTHER = "0x" + "b" * 40
TOKEN = "0x" + "c" * 40


def row(block: int, **overrides: Any) -> dict[str, Any]:
    base = {
        "blockNumber": str(block),
        "timeStamp": "1767225600",
        "hash": f"0x{block:064x}",
        "from": WALLET,
        "to": OTHER,
        "value": "5",
        "contractAddress": "",
        "isError": "0",
    }
    base.update(overrides)
    return base


def ok(rows: list[dict[str, Any]]) -> httpx.Response:
    return httpx.Response(200, json={"status": "1", "message": "OK", "result": rows})


def request(cursor: dict[str, Any] | None = None) -> TransferRequest:
    return TransferRequest(
        chain=ethereum(), address=WALLET, from_block=0, to_block=1000, cursor=cursor
    )


@respx.mock
def test_external_rows_and_next_action() -> None:
    route = respx.get(URL).mock(return_value=ok([row(1), row(2, isError="1"), row(3, to="")]))
    page = EtherscanProvider(httpx.Client()).fetch_transfers_page("k1", request())

    params = route.calls.last.request.url.params
    assert params["action"] == "txlist" and params["chainid"] == "1" and params["apikey"] == "k1"
    assert [t.block_number for t in page.transfers] == [1, 3]  # reverted tx skipped
    assert page.transfers[0].token_address == NATIVE_TOKEN
    assert page.transfers[0].category is TransferCategory.EXTERNAL
    assert page.transfers[1].to_address == NULL_ADDRESS
    assert page.next_cursor == {"action": 1, "startblock": 0, "page": 1}


@respx.mock
def test_full_page_drops_last_block_and_moves_startblock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(etherscan_module, "PAGE_SIZE", 3)
    respx.get(URL).mock(return_value=ok([row(10), row(11), row(11)]))
    page = EtherscanProvider(httpx.Client()).fetch_transfers_page(
        "k1", request({"action": 2, "startblock": 5, "page": 1})
    )
    assert [t.block_number for t in page.transfers] == [10]
    assert page.next_cursor == {"action": 2, "startblock": 11, "page": 1}


@respx.mock
def test_full_page_in_single_block_uses_page_numbers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(etherscan_module, "PAGE_SIZE", 2)
    respx.get(URL).mock(return_value=ok([row(7), row(7, value="6")]))
    page = EtherscanProvider(httpx.Client()).fetch_transfers_page(
        "k1", request({"action": 0, "startblock": 7, "page": 1})
    )
    assert len(page.transfers) == 2
    assert page.next_cursor == {"action": 0, "startblock": 7, "page": 2}


@respx.mock
def test_token_rows() -> None:
    erc20 = row(
        1,
        contractAddress=TOKEN,
        tokenSymbol="USDC",
        tokenName="USD Coin",
        tokenDecimal="6",
        logIndex="4",
    )
    respx.get(URL).mock(return_value=ok([erc20]))
    page = EtherscanProvider(httpx.Client()).fetch_transfers_page(
        "k1", request({"action": 2, "startblock": 0})
    )
    (t,) = page.transfers
    assert (t.token_address, t.symbol, t.decimals, t.log_index) == (TOKEN, "USDC", 6, 4)

    respx.get(URL).mock(
        return_value=ok([row(1, contractAddress=TOKEN, tokenID="9", tokenValue="3")])
    )
    page = EtherscanProvider(httpx.Client()).fetch_transfers_page(
        "k1", request({"action": 4, "startblock": 0})
    )
    (t,) = page.transfers
    assert (t.category, t.token_id, t.raw_amount) == (TransferCategory.ERC1155, "9", 3)
    assert page.next_cursor is None


@respx.mock
def test_no_transactions_is_empty() -> None:
    respx.get(URL).mock(
        return_value=httpx.Response(
            200, json={"status": "0", "message": "No transactions found", "result": []}
        )
    )
    page = EtherscanProvider(httpx.Client()).fetch_transfers_page("k1", request())
    assert page.transfers == []


@respx.mock
@pytest.mark.parametrize(
    ("result", "error"),
    [
        ("Max calls per sec rate limit reached (5/sec)", RateLimitedError),
        ("Max daily limit reached", QuotaExceededError),
        ("Invalid API Key", AuthError),
    ],
)
def test_error_mapping(result: str, error: type[Exception]) -> None:
    respx.get(URL).mock(
        return_value=httpx.Response(200, json={"status": "0", "message": "NOTOK", "result": result})
    )
    with pytest.raises(error):
        EtherscanProvider(httpx.Client()).fetch_transfers_page("k1", request())


@respx.mock
def test_latest_block_via_proxy() -> None:
    respx.get(URL).mock(
        return_value=httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": "0x10"})
    )
    assert EtherscanProvider(httpx.Client()).latest_block("k1", ethereum()) == 16
