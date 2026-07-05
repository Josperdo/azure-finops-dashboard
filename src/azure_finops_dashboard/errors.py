from azure.core.exceptions import ClientAuthenticationError, HttpResponseError

from azure_finops_dashboard.config import ConfigError


def friendly_error(exc: Exception) -> str:
    """Translate common Azure SDK / config exceptions into an actionable message."""
    if isinstance(exc, ClientAuthenticationError):
        return (
            "No valid Azure credential found. Run `az login`, or set up a managed "
            "identity / environment-variable credential. See Security.md."
        )
    if isinstance(exc, HttpResponseError) and exc.status_code == 403:
        return (
            "Access denied. This identity needs the Reader role (and Cost Management "
            "Reader for cost data) on the target subscription."
        )
    if isinstance(exc, ConfigError):
        return str(exc)
    return str(exc)
