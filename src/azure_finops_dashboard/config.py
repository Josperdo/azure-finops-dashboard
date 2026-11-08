import json
import re
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_CONFIG_PATH = Path.home() / ".azure-finops" / "config.json"


@dataclass
class Config:
    tenant_id: str | None = None
    subscription_ids: list[str] = field(default_factory=list)


class ConfigError(Exception):
    pass


_GUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


def _validate_subscription_ids(ids: list[str], source: str) -> list[str]:
    """User-supplied IDs end up in ARM scope paths, so require the GUID shape up front."""
    for sub_id in ids:
        if not _GUID_RE.match(sub_id):
            raise ConfigError(f"Invalid subscription ID from {source}: expected a GUID.")
    return ids


def load_config(path: Path | None = None) -> Config:
    """Load default tenant/subscription scoping from a local JSON file.

    A missing file is not an error - it just means no defaults are configured yet.
    """
    config_path = path or DEFAULT_CONFIG_PATH
    if not config_path.exists():
        return Config()

    try:
        raw = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ConfigError(f"{config_path} is not valid JSON: {exc}") from exc

    return Config(
        tenant_id=raw.get("tenant_id"),
        subscription_ids=list(raw.get("subscription_ids", [])),
    )


def resolve_subscriptions(
    cli_ids: list[str],
    all_flag: bool,
    config: Config,
    discovered: list[str],
) -> list[str]:
    """Resolve which subscription IDs to operate on.

    Precedence: explicit --subscription flags > --all-subscriptions (every discovered
    subscription) > config file default > error.
    """
    if cli_ids:
        return _validate_subscription_ids(cli_ids, "--subscription")
    if all_flag:
        return discovered
    if config.subscription_ids:
        return _validate_subscription_ids(config.subscription_ids, "the config file")
    raise ConfigError(
        "No subscription specified. Pass --subscription, use --all-subscriptions, "
        f"or set a default in {DEFAULT_CONFIG_PATH}."
    )
