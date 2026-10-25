"""Application settings.

Values are layered (lowest to highest precedence):
1. Defaults declared on the models below.
2. YAML files listed in ``HEATMAP_CONFIG_FILES`` (comma separated, later files win),
   defaulting to ``config/default.yaml`` in the current working directory.
3. Environment variables prefixed ``HEATMAP_`` (nested with ``__``),
   e.g. ``HEATMAP_DATABASE_URL`` or ``HEATMAP_EXPANSION__MAX_HOPS=2``.

Provider secrets are never stored in YAML: a key entry names the environment
variable that holds the secret.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

ProviderKind = Literal["alchemy", "etherscan"]


class ProviderKeyConfig(BaseModel):
    id: str
    env: str = Field(description="Environment variable that holds the secret")
    rps: float = Field(5.0, gt=0, description="Max requests per second for this key")
    daily_quota: int | None = Field(None, gt=0, description="Max requests per UTC day")

    def secret(self) -> str | None:
        value = os.environ.get(self.env)
        return value or None


class ProviderConfig(BaseModel):
    kind: ProviderKind
    priority: int = 100
    base_url: str | None = None
    timeout_s: float = 30.0
    cooldown_s: float = Field(60.0, description="How long a rate-limited key is benched")
    max_retries: int = 3
    keys: list[ProviderKeyConfig] = Field(default_factory=list)


class ChainConfig(BaseModel):
    chain_id: int
    enabled: bool = True
    providers: list[str] = Field(default_factory=list, description="Provider names, in no order")
    confirmations: int = 12
    reorg_window: int = Field(64, description="Blocks re-scanned on each sync")
    start_block: int = 0
    sync_block_chunk: int = Field(
        1_000_000,
        gt=0,
        description="Blocks fetched per request range; the cursor commits per chunk",
    )
    classify_per_sync: int = Field(
        500,
        ge=0,
        description="Unknown counterparties checked with eth_getCode per sync run (0: off)",
    )
    multicall3: str = "0xca11bde05977b3631167028862be2a173976ca11"
    wrapped_native: str | None = Field(None, description="WETH-style token priced like native")
    uniswap_v4_pool_manager: str | None = None
    uniswap_v4_position_manager: str | None = None
    native_symbol: str = "ETH"
    native_decimals: int = 18
    alchemy_network: str | None = None
    defillama_chain: str | None = Field(
        None, description="DefiLlama chain slug for token prices; defaults to the chain name"
    )
    explorer_url: str | None = None


class ScheduleConfig(BaseModel):
    enabled: bool = True
    timezone: str = "UTC"
    sync_cron: str = "0 * * * *"
    discovery_cron: str = "*/10 * * * *"
    expansion_cron: str = "30 */6 * * *"
    # Models run right after features in the same job, so they have no cron of their own.
    features_cron: str = "0 2 * * *"


class ExpansionConfig(BaseModel):
    enabled: bool = True
    max_hops: int = Field(1, ge=0, le=3)
    top_n_per_wallet: int = 15
    min_interactions: int = 2
    window_days: int = 180
    hub_degree_threshold: int = Field(
        2000, description="Addresses with more distinct counterparties are treated as hubs"
    )
    max_total_neighbours: int = Field(5000, description="Cap on neighbours tracked at once")


class TrackingConfig(BaseModel):
    """Checks on wallets added automatically (DEX traders, neighbours) before their first sync.

    Contracts, and wallets that sent more than ``max_sent_txs`` transactions,
    are not tracked: they are pools, protocols, exchanges, payout services or
    bots, and one of them can hold millions of transfers.
    """

    max_sent_txs: int = Field(
        10_000, gt=0, description="Wallets that sent more transactions are not tracked"
    )


class SpamConfig(BaseModel):
    enabled: bool = True
    airdrop_min_recipients: int = Field(
        50, description="Unverified token sent from one tx to this many wallets is an airdrop"
    )
    flag_zero_value: bool = True
    flag_non_ascii_symbols: bool = True


class FeatureConfig(BaseModel):
    windows: list[str] = Field(default_factory=lambda: ["7d", "30d", "90d", "all"])
    min_transfers: int = 3
    co_timing_seconds: int = 120

    @field_validator("windows")
    @classmethod
    def _validate_windows(cls, value: list[str]) -> list[str]:
        for window in value:
            if window != "all" and not (window.endswith("d") and window[:-1].isdigit()):
                raise ValueError(f"window must be '<n>d' or 'all', got {window!r}")
        return value


class PromotionConfig(BaseModel):
    """Which discovered traders join the watchlist for deep sync and neighbour expansion."""

    enabled: bool = True
    min_volume_usd: float = 5_000
    min_trades: int = Field(3, description="Distinct transactions in the discovery window")
    min_active_days: int = 2
    max_per_run: int = 25
    max_total: int = Field(500, description="Cap on promoted wallets tracked at once")


class DiscoveryConfig(BaseModel):
    """Finding wallets from DEX trades (Uniswap v2/v3/v4 and forks)."""

    enabled: bool = True
    backfill_blocks: int = Field(7_200, ge=0, description="Blocks scanned on the first run")
    max_blocks_per_run: int = Field(1_800, gt=0)
    logs_block_range: int = Field(10, gt=0, description="Blocks per eth_getLogs request")
    window_days: int = Field(30, gt=0, description="Trades used for trader statistics")
    min_router_signers: int = Field(
        10,
        description="A contract called by fewer distinct signers is private (bot-like), "
        "unless it is a labelled router",
    )
    max_router_txs_per_signer: float = Field(
        5,
        description="An unlabelled contract whose signers average more transactions than "
        "this in the window is private: rotating bot wallets, not a public router",
    )
    bot_tx_per_day: float = Field(100, description="Trade frequency treated as a bot")
    bot_swaps_per_tx: float = Field(
        6, description="Average swaps per transaction treated as a solver/market maker"
    )
    bot_arbitrage_share: float = Field(
        0.3, description="Share of circular (arbitrage) transactions treated as a bot"
    )
    promote: PromotionConfig = Field(default_factory=PromotionConfig)


class ModelConfig(BaseModel):
    version: str = "v1"
    window: str = Field("all", description="Feature window used for tags, clusters, anomalies")
    drift_window: str = Field("30d", description="Feature window compared between snapshots")
    min_cluster_size: int = 10
    anomaly_contamination: float = 0.05
    drift_threshold: float = 3.0


class ApiConfig(BaseModel):
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])
    default_page_size: int = 50
    max_page_size: int = 500


class PricingConfig(BaseModel):
    enabled: bool = True
    source: Literal["defillama", "coingecko"] = "defillama"
    defillama_url: str = "https://coins.llama.fi"
    coingecko_url: str = "https://api.coingecko.com/api/v3"
    coingecko_api_key_env: str | None = "COINGECKO_API_KEY"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="HEATMAP_",
        env_nested_delimiter="__",
        extra="ignore",
    )

    env: Literal["dev", "test", "prod"] = "dev"
    log_level: str = "INFO"
    log_json: bool = False
    database_url: str = "postgresql+psycopg://heatmap:heatmap@localhost:5432/heatmap"

    providers: dict[str, ProviderConfig] = Field(default_factory=dict)
    chains: dict[str, ChainConfig] = Field(default_factory=dict)
    schedules: ScheduleConfig = Field(default_factory=ScheduleConfig)
    expansion: ExpansionConfig = Field(default_factory=ExpansionConfig)
    tracking: TrackingConfig = Field(default_factory=TrackingConfig)
    spam: SpamConfig = Field(default_factory=SpamConfig)
    features: FeatureConfig = Field(default_factory=FeatureConfig)
    discovery: DiscoveryConfig = Field(default_factory=DiscoveryConfig)
    models: ModelConfig = Field(default_factory=ModelConfig)
    pricing: PricingConfig = Field(default_factory=PricingConfig)
    api: ApiConfig = Field(default_factory=ApiConfig)

    @model_validator(mode="after")
    def _check_chain_providers(self) -> Settings:
        for chain_name, chain in self.chains.items():
            unknown = [p for p in chain.providers if p not in self.providers]
            if unknown:
                raise ValueError(f"chain {chain_name!r} references unknown providers {unknown}")
        return self

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            _YamlFilesSource(settings_cls),
            file_secret_settings,
        )


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def config_files() -> list[Path]:
    raw = os.environ.get("HEATMAP_CONFIG_FILES")
    if raw is not None:
        return [Path(p.strip()) for p in raw.split(",") if p.strip()]
    default = Path.cwd() / "config" / "default.yaml"
    return [default] if default.exists() else []


def load_yaml_config(paths: list[Path]) -> dict[str, Any]:
    data: dict[str, Any] = {}
    for path in paths:
        if not path.exists():
            raise FileNotFoundError(f"config file not found: {path}")
        loaded = yaml.safe_load(path.read_text()) or {}
        if not isinstance(loaded, dict):
            raise ValueError(f"config file {path} must contain a mapping")
        data = _deep_merge(data, loaded)
    return data


class _YamlFilesSource(PydanticBaseSettingsSource):
    def get_field_value(self, field: Any, field_name: str) -> tuple[Any, str, bool]:
        return None, field_name, False

    def __call__(self) -> dict[str, Any]:
        return load_yaml_config(config_files())


def load_env_file() -> None:
    """Load ``.env`` (or the file named by ``HEATMAP_ENV_FILE``) into the environment.

    Provider keys are read from ``os.environ``, so the file must be loaded there,
    not only into ``Settings``. Variables already set in the environment win.
    An empty ``HEATMAP_ENV_FILE`` disables loading (the test suite does this).
    """
    path = os.environ.get("HEATMAP_ENV_FILE", ".env")
    if path:
        load_dotenv(path, override=False)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    load_env_file()
    return Settings()
