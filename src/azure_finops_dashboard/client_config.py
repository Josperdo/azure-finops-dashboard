"""Shared construction kwargs for Azure SDK clients, aimed at reducing 429s.

Two independent mitigations, both confirmed against real throttling hit during this
project's testing (Cost Management is throttled far more aggressively than other
management APIs):

1. **Retry tuning.** azure-core clients already retry transient failures (including 429s)
   via their pipeline - the gap is that the *shape* of the backoff isn't aggressive enough
   by default. azure-core's `RetryPolicy` defaults are `retry_total=10`,
   `retry_backoff_factor=0.8`, `retry_backoff_max=120` (confirmed by inspecting
   `RetryPolicy()` directly - a first attempt at this that picked `retry_total=6`/
   `retry_backoff_max=30` from assumption alone turned out to be *weaker* than the defaults
   on both of those, not stronger, and 429s persisted as a direct result). Only
   `retry_backoff_factor` is overridden here, to grow the exponential delay between
   attempts faster than the default; `retry_total`/`retry_backoff_max` are left at their
   already-generous defaults.

2. **`ClientType` header.** Per Microsoft Q&A guidance from a Cost Management team
   moderator (https://learn.microsoft.com/en-us/answers/questions/1520105/), *any* caller
   that omits a `ClientType` header shares one rate-limit pool with every other caller in
   the tenant that also omits it — including other tools, scripts, and portal sessions, not
   just this CLI's own calls. Setting a distinct `ClientType` moves this tool into its own
   pool. This is likely the single biggest lever available for the throttling hit
   repeatedly during this project's live testing, more so than the retry tuning above.
"""

from typing import Any

from azure.core.pipeline.policies import HeadersPolicy

CLIENT_KWARGS: dict[str, Any] = {
    "retry_backoff_factor": 2.0,
    "headers_policy": HeadersPolicy(base_headers={"ClientType": "azure-finops-dashboard"}),
}
