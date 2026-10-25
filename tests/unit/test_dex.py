from __future__ import annotations

from eth_abi.abi import encode

from heatmap_core.config.settings import DiscoveryConfig
from heatmap_core.dex.abi import Call, decode_address, decode_text, multicall
from heatmap_core.dex.events import parse_swap_log, trade_sides
from heatmap_core.dex.pools import load_factories, resolve_pools
from heatmap_core.dex.traders import bot_reason
from heatmap_core.primitives import NATIVE_TOKEN, NULL_ADDRESS
from tests.support import addr
from tests.support_dex import (
    POOL_MANAGER,
    POSITION_MANAGER,
    UNI_V2_FACTORY,
    UNI_V3_FACTORY,
    USDC,
    WETH,
    FakeDexChain,
    dex_chain,
    v4_pool_id,
    word,
)

POOL = addr(0x2001)


def test_swap_events_are_reduced_to_the_pools_view() -> None:
    fake = FakeDexChain(head=1)
    fake.v2_swap(1, "0x01", POOL, (2_000, 0, 0, 1))  # paid token0, took token1
    fake.v3_swap(1, "0x02", POOL, -5, 7)  # pool view: took 7 of token1 in, gave 5 of token0
    pool_id = v4_pool_id((NULL_ADDRESS, USDC, 500, 10, NULL_ADDRESS))
    fake.v4_swap(1, "0x03", pool_id, -10, 20)  # swapper view: paid 10 of token0, got 20 of token1
    fake.v4_swap(1, "0x04", pool_id, -10, 20, emitter=addr(0xDEAD))  # spoofed PoolManager

    swaps = [parse_swap_log(entry, POOL_MANAGER) for entry in fake.logs]

    v2, v3, v4, spoof = swaps
    assert v2 is not None and (v2.kind, v2.delta0, v2.delta1) == ("v2", 2_000, -1)
    assert v3 is not None and (v3.kind, v3.delta0, v3.delta1) == ("v3", -5, 7)
    assert v4 is not None and (v4.kind, v4.pool_id, v4.delta0, v4.delta1) == (
        "v4",
        pool_id,
        10,
        -20,
    )
    assert spoof is None
    assert v2.log_index == 0 and v4.log_index == 2 and v2.tx_hash == "0x01"


def test_removed_and_garbled_logs_are_ignored() -> None:
    fake = FakeDexChain(head=1)
    fake.v3_swap(1, "0x01", POOL, 1, -1)
    entry = dict(fake.logs[0])
    assert parse_swap_log({**entry, "removed": True}, POOL_MANAGER) is None
    assert parse_swap_log({**entry, "data": "0x1234"}, POOL_MANAGER) is None
    assert parse_swap_log({**entry, "topics": []}, POOL_MANAGER) is None


def test_trade_sides() -> None:
    assert trade_sides(100, -2, "a", "b") == ("a", 100, "b", 2)
    assert trade_sides(-3, 50, "a", "b") == ("b", 50, "a", 3)
    assert trade_sides(1, 1, "a", "b") is None
    assert trade_sides(0, -1, "a", "b") is None


def test_multicall_and_decoders() -> None:
    fake = FakeDexChain(head=1)
    fake.answer(POOL, "token0()", b"", word(USDC))
    out = multicall(fake, dex_chain(), [Call(POOL, bytes.fromhex("0dfe1681")), Call(POOL, b"\x01")])
    assert decode_address(out[0]) == USDC and out[1] is None
    assert decode_text(encode(["string"], ["PEPE"])) == "PEPE"
    assert decode_text(b"MKR" + b"\x00" * 29) == "MKR"  # bytes32 symbol
    assert decode_text(None) is None


def test_pools_verified_by_their_factory_or_pool_id() -> None:
    chain = dex_chain()
    fake = FakeDexChain(head=1)
    real, fake_pool, v3 = addr(0x2001), addr(0x2BAD), addr(0x3001)
    for pool, factory in ((real, UNI_V2_FACTORY), (fake_pool, UNI_V2_FACTORY)):
        fake.answer(pool, "token0()", b"", word(USDC))
        fake.answer(pool, "token1()", b"", word(WETH))
        fake.answer(pool, "factory()", b"", word(factory))
    fake.answer(
        UNI_V2_FACTORY,
        "getPair(address,address)",
        encode(["address"] * 2, [USDC, WETH]),
        word(real),
    )
    fake.answer(v3, "token0()", b"", word(USDC))
    fake.answer(v3, "token1()", b"", word(WETH))
    fake.answer(v3, "factory()", b"", word(UNI_V3_FACTORY))
    fake.answer(v3, "fee()", b"", encode(["uint24"], [500]))
    fake.answer(
        UNI_V3_FACTORY,
        "getPool(address,address,uint24)",
        encode(["address", "address", "uint24"], [USDC, WETH, 500]),
        word(v3),
    )
    key = (NULL_ADDRESS, USDC, 500, 10, NULL_ADDRESS)
    good, unknown = v4_pool_id(key), v4_pool_id((NULL_ADDRESS, WETH, 500, 10, NULL_ADDRESS))
    for pool_id in (good, unknown):
        fake.answer(
            POSITION_MANAGER,
            "poolKeys(bytes25)",
            encode(["bytes25"], [bytes.fromhex(pool_id[2:])[:25]]),
            encode(["address", "address", "uint24", "int24", "address"], list(key)),
        )

    infos = {
        i.pool_id: i
        for i in resolve_pools(
            fake,
            chain,
            {real: "v2", fake_pool: "v2", v3: "v3", good: "v4", unknown: "v4"},
            load_factories(chain),
        )
    }

    assert infos[real].verified and infos[real].protocol == "uniswap_v2"
    assert not infos[fake_pool].verified  # claims the factory, but the factory disowns it
    assert infos[v3].verified and infos[v3].fee == 500
    assert infos[good].verified and infos[good].token0 == NATIVE_TOKEN
    assert infos[good].token1 == USDC and infos[good].hooks is None
    assert not infos[unknown].verified and infos[unknown].token0 is None  # key hashes differently


class Row:
    def __init__(self, **values: float) -> None:
        defaults = dict(
            settlement_share=0.0,
            private_share=0.0,
            arbitrage_share=0.0,
            swaps_per_tx=1.0,
            tx_count=10,
            active_days=5,
        )
        self.__dict__.update({**defaults, **values})


def test_bot_reasons_in_order() -> None:
    cfg = DiscoveryConfig()
    assert bot_reason(Row(), cfg) is None
    assert bot_reason(Row(settlement_share=0.6, private_share=0.9), cfg) == "settlement_signer"
    assert bot_reason(Row(private_share=0.5), cfg) == "private_contract"
    assert bot_reason(Row(arbitrage_share=0.3), cfg) == "arbitrage"
    assert bot_reason(Row(swaps_per_tx=8), cfg) == "batch_executor"
    assert bot_reason(Row(tx_count=600, active_days=5), cfg) == "high_frequency"
