from dataclasses import dataclass

from azure.core.credentials import TokenCredential
from azure.mgmt.subscription import SubscriptionClient


@dataclass
class SubscriptionInfo:
    subscription_id: str
    display_name: str
    state: str


def list_subscriptions(credential: TokenCredential) -> list[SubscriptionInfo]:
    """List every subscription the given credential can see."""
    client = SubscriptionClient(credential)
    return [
        SubscriptionInfo(
            subscription_id=sub.subscription_id or "",
            display_name=sub.display_name or "",
            state=str(sub.state) if sub.state else "",
        )
        for sub in client.subscriptions.list()
    ]
