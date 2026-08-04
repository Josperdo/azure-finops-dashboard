"""Retry tuning for Azure SDK clients.

azure-core clients already retry transient failures (including 429s) via their pipeline —
the gap is that the *shape* of the backoff isn't aggressive enough for how Cost Management
throttles in practice (confirmed by hitting real 429s during this project's export and
trend testing). This isn't a custom retry loop, just a stronger configuration of the
built-in one.

azure-core's RetryPolicy defaults are `retry_total=10`, `retry_backoff_factor=0.8`,
`retry_backoff_max=120` (confirmed by inspecting `RetryPolicy()` directly - a first attempt
at this that picked `retry_total=6`/`retry_backoff_max=30` from assumption alone turned out
to be *weaker* than the defaults on both of those, not stronger, and 429s persisted as a
direct result). Only `retry_backoff_factor` is overridden here, to grow the exponential
delay between attempts faster than the default; `retry_total`/`retry_backoff_max` are left
at their already-generous defaults rather than second-guessed again without real data on
what Cost Management's throttling window actually needs.
"""

from typing import Any

RETRY_KWARGS: dict[str, Any] = {
    "retry_backoff_factor": 2.0,
}
