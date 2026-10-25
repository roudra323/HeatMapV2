from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
import respx

from heatmap_core.primitives import NATIVE_TOKEN, TransferCategory
from heatmap_core.providers import (
    AlchemyProvider,
    QuotaExceededError,
    RateLimitedError,
    TransferRequest,
)
from tests.support import ethereum

URL = "https://eth-mainnet.g.alchemy.com/v2/k1"
WALLET = "0x" + "a" * 40
OTHER = "0x" + "b" * 40
TOKEN = "0x" + "c" * 40
META = {"blockTimestamp": "2026-01-02T03:04:05.000Z"}


def item(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "blockNum": "0x10",
        "uniqueId": "0xabc:external",
        "hash": "0xABC",
        "from": WALLET,
        "to": OTHER,
        "category": "external",
        "asset": "ETH",
        "rawContract": {"value": "0xde0b6b3a7640000", "address": None, "decimal": "0x12"},
        "metadata": META,
    }
    base.update(overrides)
    return base


def request(cursor: dict[str, Any] | None = None) -> TransferRequest:
    return TransferRequest(
        chain=ethereum(), address=WALLET, from_block=0, to_block=100, cursor=cursor
    )


@respx.mock
def test_parses_all_categories() -> None:
    transfers = [
        item(),
        item(
            category="erc20",
            uniqueId="0xabc:log:3",
            asset="USDC",
            rawContract={
                "value": "0xf4240",
                "address": TOKEN.upper().replace("X", "x"),
                "decimal": "0x6",
            },
        ),
        item(category="erc721", erc721TokenId="0x2a", rawContract={"address": TOKEN}),
        item(
            category="erc1155",
            erc1155Metadata=[
                {"tokenId": "0x1", "value": "0x5"},
                {"tokenId": "0x2", "value": "0x1"},
            ],
            rawContract={"address": TOKEN},
        ),
    ]
    respx.post(URL).mock(
        return_value=httpx.Response(200, json={"result": {"transfers": transfers}})
    )

    page = AlchemyProvider(httpx.Client()).fetch_transfers_page("k1", request())

    native, erc20, nft, *multi = page.transfers
    assert native.category is TransferCategory.EXTERNAL
    assert native.token_address == NATIVE_TOKEN
    assert native.raw_amount == 10**18
    assert native.decimals == 18
    assert native.tx_hash == "0xabc"
    assert native.block_time.isoformat() == "2026-01-02T03:04:05+00:00"
    assert erc20.token_address == TOKEN and erc20.raw_amount == 1_000_000 and erc20.log_index == 3
    assert nft.token_id == "42" and nft.raw_amount == 1
    assert [(t.token_id, t.raw_amount) for t in multi] == [("1", 5), ("2", 1)]
    # first direction finished without pageKey -> continue with the "to" direction
    assert page.next_cursor == {"direction": 1, "page_key": None}


@respx.mock
def test_request_params_and_paging() -> None:
    route = respx.post(URL).mock(
        return_value=httpx.Response(200, json={"result": {"transfers": [], "pageKey": "pk2"}})
    )
    page = AlchemyProvider(httpx.Client()).fetch_transfers_page(
        "k1", request({"direction": 1, "page_key": "pk1"})
    )
    params = json.loads(route.calls.last.request.content)["params"][0]
    assert params["toAddress"] == WALLET
    assert "fromAddress" not in params
    assert params["pageKey"] == "pk1"
    assert params["fromBlock"] == "0x0" and params["toBlock"] == "0x64"
    assert "internal" in params["category"]
    assert page.next_cursor == {"direction": 1, "page_key": "pk2"}


@respx.mock
def test_last_direction_without_page_key_ends() -> None:
    respx.post(URL).mock(return_value=httpx.Response(200, json={"result": {"transfers": []}}))
    page = AlchemyProvider(httpx.Client()).fetch_transfers_page("k1", request({"direction": 1}))
    assert page.next_cursor is None


@respx.mock
def test_self_transfer_not_duplicated_in_second_direction() -> None:
    respx.post(URL).mock(
        return_value=httpx.Response(200, json={"result": {"transfers": [item(to=WALLET)]}})
    )
    page = AlchemyProvider(httpx.Client()).fetch_transfers_page("k1", request({"direction": 1}))
    assert page.transfers == []


@respx.mock
@pytest.mark.parametrize(
    ("response", "error"),
    [
        (httpx.Response(429), RateLimitedError),
        (
            httpx.Response(200, json={"error": {"code": 429, "message": "rate limited"}}),
            RateLimitedError,
        ),
        (
            httpx.Response(
                200, json={"error": {"code": -32000, "message": "Monthly capacity limit exceeded"}}
            ),
            QuotaExceededError,
        ),
        (
            httpx.Response(
                200,
                json={
                    "error": {
                        "code": 429,
                        "message": "Your app has exceeded its compute units per second capacity.",
                    }
                },
            ),
            RateLimitedError,
        ),
    ],
)
def test_error_mapping(response: httpx.Response, error: type[Exception]) -> None:
    respx.post(URL).mock(return_value=response)
    with pytest.raises(error):
        AlchemyProvider(httpx.Client()).fetch_transfers_page("k1", request())


@respx.mock
def test_transaction_count() -> None:
    route = respx.post(URL).mock(return_value=httpx.Response(200, json={"result": "0x2710"}))
    assert AlchemyProvider(httpx.Client()).get_transaction_count("k1", ethereum(), WALLET) == 10_000
    body = json.loads(route.calls.last.request.content)
    assert (body["method"], body["params"]) == ("eth_getTransactionCount", [WALLET, "latest"])
