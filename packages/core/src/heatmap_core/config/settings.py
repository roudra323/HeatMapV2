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
    native_symbol: str = "ETH"
    native_decimals: int = 18
    alchemy_network: str | None = None
    explorer_url: str | None = None


class ScheduleConfig(BaseModel):
    enabled: bool = True
    timezone: str = "UTC"
    sync_cron: str = "0 * * * *"
    expansion_cron: str = "30 */6 * * *"
    features_cron: str = "0 2 * * *"
    models_cron: str = "30 2 * * *"


class ExpansionConfig(BaseModel):
    enabled: bool = True
    max_hops: int = Field(1, ge=0, le=3)
    top_n_per_wallet: int = 15
    min_interactions: int = 2
    window_days: int = 180
    hub_degree_threshold: int = Field(
        2000, description="Addresses with more distinct counterparties are treated as hubs"
    )
    max_total_neighbours: int = 5000


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


class ModelConfig(BaseModel):
    version: str = "v1"
    min_cluster_size: int = 10
    anomaly_contamination: float = 0.05
    drift_threshold: float = 3.0


class ApiConfig(BaseModel):
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])
    default_page_size: int = 50
    max_page_size: int = 500


class PricingConfig(BaseModel):
    enabled: bool = True
    base_url: str = "https://api.coingecko.com/api/v3"
    api_key_env: str | None = "COINGECKO_API_KEY"
    stable_usd_symbols: list[str] = Field(
        default_factory=lambda: ["USDC", "USDT", "DAI", "USDS", "PYUSD", "FDUSD", "TUSD"]
    )


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
    spam: SpamConfig = Field(default_factory=SpamConfig)
    features: FeatureConfig = Field(default_factory=FeatureConfig)
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


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
