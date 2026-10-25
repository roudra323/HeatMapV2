import os
from pathlib import Path

import pytest
from pydantic import ValidationError

from heatmap_core.config import ChainRegistry, Settings, UnknownChainError
from heatmap_core.config.settings import load_env_file

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def default_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HEATMAP_CONFIG_FILES", str(REPO_ROOT / "config" / "default.yaml"))


@pytest.mark.usefixtures("default_config")
def test_default_yaml_loads() -> None:
    settings = Settings()
    assert settings.chains["ethereum"].chain_id == 1
    assert settings.providers["alchemy"].kind == "alchemy"
    assert len(settings.providers["etherscan"].keys) == 2
    assert settings.tracking.max_sent_txs == 10_000


@pytest.mark.usefixtures("default_config")
def test_env_overrides_yaml(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HEATMAP_EXPANSION__MAX_HOPS", "2")
    monkeypatch.setenv("HEATMAP_SCHEDULES__SYNC_CRON", "*/15 * * * *")
    settings = Settings()
    assert settings.expansion.max_hops == 2
    assert settings.schedules.sync_cron == "*/15 * * * *"
    # untouched YAML values survive the override
    assert settings.expansion.top_n_per_wallet == 15


def test_later_yaml_files_override_earlier(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    override = tmp_path / "override.yaml"
    override.write_text("chains:\n  ethereum:\n    confirmations: 30\n")
    monkeypatch.setenv(
        "HEATMAP_CONFIG_FILES", f"{REPO_ROOT / 'config' / 'default.yaml'},{override}"
    )
    settings = Settings()
    assert settings.chains["ethereum"].confirmations == 30
    assert settings.chains["ethereum"].chain_id == 1


def test_provider_secret_read_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HEATMAP_CONFIG_FILES", str(REPO_ROOT / "config" / "default.yaml"))
    monkeypatch.setenv("ALCHEMY_KEY_1", "secret-value")
    monkeypatch.delenv("ALCHEMY_KEY_2", raising=False)
    keys = Settings().providers["alchemy"].keys
    assert keys[0].secret() == "secret-value"
    assert keys[1].secret() is None


def test_env_file_loaded_without_overriding_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("HEATMAP_TEST_FROM_FILE=file\nHEATMAP_TEST_ALREADY_SET=file\n")
    monkeypatch.delenv("HEATMAP_TEST_FROM_FILE", raising=False)
    monkeypatch.setenv("HEATMAP_TEST_ALREADY_SET", "env")
    monkeypatch.setenv("HEATMAP_ENV_FILE", str(env_file))
    load_env_file()
    assert os.environ["HEATMAP_TEST_FROM_FILE"] == "file"
    assert os.environ["HEATMAP_TEST_ALREADY_SET"] == "env"
    monkeypatch.delenv("HEATMAP_TEST_FROM_FILE")


def test_empty_env_file_setting_disables_loading(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / ".env").write_text("HEATMAP_TEST_FROM_FILE=file\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("HEATMAP_TEST_FROM_FILE", raising=False)
    monkeypatch.setenv("HEATMAP_ENV_FILE", "")
    load_env_file()
    assert "HEATMAP_TEST_FROM_FILE" not in os.environ


def test_chain_with_unknown_provider_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HEATMAP_CONFIG_FILES", "")
    with pytest.raises(ValidationError, match="unknown providers"):
        Settings(chains={"ethereum": {"chain_id": 1, "providers": ["nope"]}})


def test_invalid_feature_window_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HEATMAP_CONFIG_FILES", "")
    with pytest.raises(ValidationError):
        Settings(features={"windows": ["weekly"]})


@pytest.mark.usefixtures("default_config")
def test_chain_registry() -> None:
    registry = ChainRegistry(Settings())
    assert registry.get("ethereum").chain_id == 1
    assert registry.by_id(1).name == "ethereum"
    with pytest.raises(UnknownChainError):
        registry.get("solana")
