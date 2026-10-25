"""Pool registry: which tokens a pool trades, and whether a known factory vouches for it.

Anyone can deploy a contract that emits Swap events with made-up numbers, so a
v2/v3 pool only counts as verified when its factory is a known one and that
factory returns the same pool for the pool's tokens (and fee). A v4 pool is
verified when its PoolKey hashes to the PoolId the PoolManager emitted.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from eth_abi.abi import encode
from eth_utils.crypto import keccak
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from heatmap_core.config import Chain
from heatmap_core.db.models import DexPool, Token
from heatmap_core.dex.abi import (
    Call,
    ContractReader,
    decode_address,
    decode_text,
    decode_uint,
    decode_values,
    multicall,
    selector,
)
from heatmap_core.entities.labels import read_seed
from heatmap_core.primitives import NATIVE_TOKEN, NULL_ADDRESS, normalize_address

TOKEN0 = selector("token0()")
TOKEN1 = selector("token1()")
FACTORY = selector("factory()")
FEE = selector("fee()")
GET_PAIR = selector("getPair(address,address)")
GET_POOL = selector("getPool(address,address,uint24)")
POOL_KEYS = selector("poolKeys(bytes25)")
DECIMALS = selector("decimals()")
SYMBOL = selector("symbol()")
NAME = selector("name()")
POOL_KEY_TYPES = ["address", "address", "uint24", "int24", "address"]


@dataclass(frozen=True)
class Factory:
    address: str
    protocol: str
    version: str  # "v2" | "v3"


@dataclass(frozen=True)
class PoolInfo:
    pool_id: str
    protocol: str
    token0: str | None
    token1: str | None
    verified: bool
    factory: str | None = None
    fee: int | None = None
    hooks: str | None = None

    def row(self, chain_id: int) -> dict[str, Any]:
        return {"chain_id": chain_id, **self.__dict__}


def load_factories(chain: Chain) -> dict[str, Factory]:
    return {
        (address := normalize_address(r["address"])): Factory(address, r["protocol"], r["version"])
        for r in read_seed(f"dex_factories_{chain.name}.csv")
    }


def _v4_currency(address: str) -> str:
    return NATIVE_TOKEN if address == NULL_ADDRESS else address


def resolve_pools(
    reader: ContractReader,
    chain: Chain,
    pools: dict[str, str],
    factories: dict[str, Factory],
) -> list[PoolInfo]:
    """Look up ``{pool_id: kind}`` on-chain; unresolvable pools come back without tokens."""
    v23 = sorted(p for p, kind in pools.items() if kind in ("v2", "v3"))
    v4 = sorted(p for p, kind in pools.items() if kind == "v4")
    return _resolve_v23(reader, chain, v23, pools, factories) + _resolve_v4(reader, chain, v4)


def _resolve_v23(
    reader: ContractReader,
    chain: Chain,
    addresses: list[str],
    kinds: dict[str, str],
    factories: dict[str, Factory],
) -> list[PoolInfo]:
    if not addresses:
        return []
    per_pool = (TOKEN0, TOKEN1, FACTORY, FEE)
    raw = multicall(reader, chain, [Call(a, sel) for a in addresses for sel in per_pool])
    found: list[tuple[str, str | None, str | None, str | None, int | None]] = []
    for i, address in enumerate(addresses):
        raw_t0, raw_t1, raw_factory, raw_fee = raw[i * 4 : i * 4 + 4]
        found.append(
            (
                address,
                decode_address(raw_t0),
                decode_address(raw_t1),
                decode_address(raw_factory),
                decode_uint(raw_fee),
            )
        )

    # Ask each known factory whether the pool is really its own.
    checks: list[tuple[int, Call]] = []
    for i, (address, t0, t1, factory, fee) in enumerate(found):
        known = factories.get(factory or "")
        if known is None or t0 is None or t1 is None or known.version != kinds[address]:
            continue
        if known.version == "v2":
            data = GET_PAIR + encode(["address", "address"], [t0, t1])
        elif fee is not None:
            data = GET_POOL + encode(["address", "address", "uint24"], [t0, t1, fee])
        else:
            continue
        checks.append((i, Call(known.address, data)))
    answers = multicall(reader, chain, [c for _, c in checks]) if checks else []
    confirmed = {
        found[i][0]
        for (i, _), answer in zip(checks, answers, strict=True)
        if decode_address(answer) == found[i][0]
    }

    infos = []
    for address, t0, t1, factory, fee in found:
        known = factories.get(factory or "")
        infos.append(
            PoolInfo(
                pool_id=address,
                protocol=known.protocol if known else f"unknown_{kinds[address]}",
                token0=t0,
                token1=t1,
                verified=address in confirmed,
                factory=factory,
                fee=fee if kinds[address] == "v3" else None,
            )
        )
    return infos


def _resolve_v4(reader: ContractReader, chain: Chain, pool_ids: list[str]) -> list[PoolInfo]:
    manager = chain.config.uniswap_v4_position_manager
    if not pool_ids:
        return []
    if manager is None:
        return [PoolInfo(p, "uniswap_v4", None, None, False) for p in pool_ids]
    calls = [
        Call(manager, POOL_KEYS + encode(["bytes25"], [bytes.fromhex(p[2:])[:25]]))
        for p in pool_ids
    ]
    infos = []
    for pool_id, raw in zip(pool_ids, multicall(reader, chain, calls), strict=True):
        key = decode_values(POOL_KEY_TYPES, raw)
        # The PositionManager only knows pools it has added liquidity to; the
        # PoolId is the hash of the key, so a wrong or empty key cannot match.
        if key is None or "0x" + keccak(encode(POOL_KEY_TYPES, list(key))).hex() != pool_id:
            infos.append(PoolInfo(pool_id, "uniswap_v4", None, None, False))
            continue
        c0, c1, fee, _spacing, hooks = key
        infos.append(
            PoolInfo(
                pool_id=pool_id,
                protocol="uniswap_v4",
                token0=_v4_currency(str(c0).lower()),
                token1=_v4_currency(str(c1).lower()),
                verified=True,
                fee=int(fee),
                hooks=None if str(hooks).lower() == NULL_ADDRESS else str(hooks).lower(),
            )
        )
    return infos


def ensure_pools(
    session: Session,
    reader: ContractReader,
    chain: Chain,
    pools: dict[str, str],
    factories: dict[str, Factory],
) -> dict[str, DexPool]:
    """Registry rows for ``{pool_id: kind}``, resolving new pools and ones still unresolved."""
    chain_id = chain.chain_id
    stored = {
        p.pool_id: p
        for p in session.scalars(
            select(DexPool).where(DexPool.chain_id == chain_id, DexPool.pool_id.in_(pools))
        )
    }
    todo = {p: k for p, k in pools.items() if p not in stored or stored[p].token0 is None}
    if todo:
        infos = resolve_pools(reader, chain, todo, factories)
        stmt = insert(DexPool).values([i.row(chain_id) for i in infos])
        session.execute(
            stmt.on_conflict_do_update(
                index_elements=["chain_id", "pool_id"],
                set_={
                    c: stmt.excluded[c]
                    for c in ("protocol", "factory", "token0", "token1", "fee", "hooks", "verified")
                },
                where=DexPool.token0.is_(None),
            )
        )
        tokens = {t for i in infos for t in (i.token0, i.token1) if t is not None}
        ensure_tokens(session, reader, chain, tokens)
        session.flush()
        stored = {
            p.pool_id: p
            for p in session.scalars(
                select(DexPool)
                .where(DexPool.chain_id == chain_id, DexPool.pool_id.in_(pools))
                .execution_options(populate_existing=True)
            )
        }
    return stored


def ensure_tokens(
    session: Session, reader: ContractReader, chain: Chain, addresses: Iterable[str]
) -> None:
    """Fetch decimals, symbol and name for tokens not known yet (never overwrites)."""
    chain_id = chain.chain_id
    wanted = set(addresses)
    known = set(
        session.scalars(
            select(Token.address).where(
                Token.chain_id == chain_id,
                Token.address.in_(wanted),
                Token.decimals.is_not(None),
            )
        )
    )
    rows: list[dict[str, Any]] = []
    if NATIVE_TOKEN in wanted - known:
        rows.append(
            {
                "chain_id": chain_id,
                "address": NATIVE_TOKEN,
                "standard": "native",
                "symbol": chain.config.native_symbol,
                "name": chain.config.native_symbol,
                "decimals": chain.config.native_decimals,
                "category": "native",
            }
        )
    missing = sorted(wanted - known - {NATIVE_TOKEN})
    raw = multicall(reader, chain, [Call(t, s) for t in missing for s in (DECIMALS, SYMBOL, NAME)])
    for i, address in enumerate(missing):
        decimals = decode_uint(raw[i * 3])
        symbol, name = decode_text(raw[i * 3 + 1]), decode_text(raw[i * 3 + 2])
        rows.append(
            {
                "chain_id": chain_id,
                "address": address,
                "standard": "erc20",
                "symbol": symbol[:64] if symbol else None,
                "name": name[:256] if name else None,
                "decimals": decimals if decimals is not None and decimals <= 36 else None,
                "category": "other",
            }
        )
    if not rows:
        return
    stmt = insert(Token).values(rows)
    session.execute(
        stmt.on_conflict_do_update(
            index_elements=["chain_id", "address"],
            set_={
                "symbol": func.coalesce(Token.symbol, stmt.excluded.symbol),
                "name": func.coalesce(Token.name, stmt.excluded.name),
                "decimals": func.coalesce(Token.decimals, stmt.excluded.decimals),
            },
        )
    )
