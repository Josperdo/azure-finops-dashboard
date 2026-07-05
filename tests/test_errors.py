from azure.core.exceptions import ClientAuthenticationError, HttpResponseError

from azure_finops_dashboard.config import ConfigError
from azure_finops_dashboard.errors import friendly_error


def test_client_authentication_error() -> None:
    msg = friendly_error(ClientAuthenticationError("no token"))
    assert "az login" in msg


def test_http_403_error() -> None:
    exc = HttpResponseError(message="forbidden")
    exc.status_code = 403
    msg = friendly_error(exc)
    assert "Reader" in msg


def test_config_error_passthrough() -> None:
    msg = friendly_error(ConfigError("no subscription specified"))
    assert msg == "no subscription specified"


def test_unknown_error_passthrough() -> None:
    msg = friendly_error(ValueError("boom"))
    assert msg == "boom"
