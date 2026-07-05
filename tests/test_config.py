import json
from pathlib import Path

import pytest

from azure_finops_dashboard.config import Config, ConfigError, load_config, resolve_subscriptions


def test_load_config_missing_file_returns_defaults(tmp_path: Path) -> None:
    config = load_config(tmp_path / "does-not-exist.json")
    assert config == Config()


def test_load_config_valid_file(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"tenant_id": "tenant-1", "subscription_ids": ["sub-1"]}))

    config = load_config(config_path)

    assert config.tenant_id == "tenant-1"
    assert config.subscription_ids == ["sub-1"]


def test_load_config_malformed_json_raises(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text("{not valid json")

    with pytest.raises(ConfigError):
        load_config(config_path)


def test_resolve_subscriptions_cli_flag_wins() -> None:
    result = resolve_subscriptions(
        cli_ids=["sub-cli"],
        all_flag=True,
        config=Config(subscription_ids=["sub-config"]),
        discovered=["sub-discovered"],
    )
    assert result == ["sub-cli"]


def test_resolve_subscriptions_all_flag() -> None:
    result = resolve_subscriptions(
        cli_ids=[],
        all_flag=True,
        config=Config(subscription_ids=["sub-config"]),
        discovered=["sub-discovered-1", "sub-discovered-2"],
    )
    assert result == ["sub-discovered-1", "sub-discovered-2"]


def test_resolve_subscriptions_config_default() -> None:
    result = resolve_subscriptions(
        cli_ids=[],
        all_flag=False,
        config=Config(subscription_ids=["sub-config"]),
        discovered=["sub-discovered"],
    )
    assert result == ["sub-config"]


def test_resolve_subscriptions_no_source_raises() -> None:
    with pytest.raises(ConfigError):
        resolve_subscriptions(cli_ids=[], all_flag=False, config=Config(), discovered=[])
