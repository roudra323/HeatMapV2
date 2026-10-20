"""Chain registry: resolves chains by name or id from settings."""

from __future__ import annotations

from dataclasses import dataclass

from heatmap_core.config.settings import ChainConfig, Settings


@dataclass(frozen=True)
class Chain:
    name: str
    config: ChainConfig

    @property
    def chain_id(self) -> int:
        return self.config.chain_id


class UnknownChainError(LookupError):
    pass


class ChainRegistry:
    def __init__(self, settings: Settings) -> None:
        self._by_name = {
            name: Chain(name=name, config=cfg)
            for name, cfg in settings.chains.items()
            if cfg.enabled
        }
        self._by_id = {chain.chain_id: chain for chain in self._by_name.values()}

    def get(self, name: str) -> Chain:
        try:
            return self._by_name[name]
        except KeyError as exc:
            raise UnknownChainError(f"chain {name!r} is not configured or disabled") from exc

    def by_id(self, chain_id: int) -> Chain:
        try:
            return self._by_id[chain_id]
        except KeyError as exc:
            raise UnknownChainError(f"chain id {chain_id} is not configured or disabled") from exc

    def all(self) -> list[Chain]:
        return list(self._by_name.values())
