from azure.identity import DefaultAzureCredential


def get_credential() -> DefaultAzureCredential:
    """Single source of truth for how this tool authenticates to Azure.

    Uses the standard DefaultAzureCredential chain (environment variables, managed
    identity, Azure CLI, then interactive browser). No key- or secret-based auth path
    is implemented by this tool — see the README's Authentication section.
    """
    return DefaultAzureCredential()
