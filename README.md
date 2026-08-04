# azure-finops-dashboard

A Python CLI for Azure cost visibility and governance.

## What it does

- Cost breakdowns by subscription, service, resource group, and tag
- Budget breach detection (Azure Consumption budgets)
- Six-month spend trend
- **FinOps audit mode:** untagged resources, stopped/idle VMs, unattached disks, orphaned
  public IPs
- CSV / JSON / PDF export
- Rich terminal UI

## Installation

```
pip install git+https://github.com/Josperdo/azure-finops-dashboard.git
```

Requires Python 3.10+ and an authenticated Azure identity (`az login`, a managed identity,
or environment-variable credentials — see Authentication below).

## Usage

```
azure-finops subscriptions list                          # subscriptions visible to this identity
azure-finops cost summary --all-subscriptions             # MTD spend by service/resource group
azure-finops cost summary --all-subscriptions --tag-key Environment   # + breakdown by tag value
azure-finops cost summary --all-subscriptions --start 2026-07-01 --end 2026-07-31  # custom range
azure-finops cost summary --all-subscriptions --rollup    # + combined view across subscriptions
azure-finops cost summary --all-subscriptions --output report.csv   # also export (.csv/.json/.pdf)
azure-finops cost trend --all-subscriptions                # 6-month spend trend
azure-finops budget status --all-subscriptions             # budget breach status
azure-finops audit run --all-subscriptions                 # untagged/idle/unattached/orphaned findings
azure-finops dashboard --all-subscriptions                  # summary + trend + budgets in one run
```

Each of `--subscription`/`--all-subscriptions`, `--top`, and `--months` work the same way
across the commands that support them; `--subscription` accepts a subscription ID and is
repeatable to target several at once.

## Authentication

Uses `DefaultAzureCredential` exclusively (environment → managed identity → Azure CLI →
interactive browser). No API keys, connection strings, or client secrets. Requires **Reader**
and **Cost Management Reader** RBAC roles on the target subscription(s) — nothing broader.

## Known Limitations

- **Cost Management data latency** — Azure's own cost data typically lags actual spend by up
  to 24-48h; this tool reflects that, not real-time usage.
- **Tag propagation latency** — a tag applied to a resource can take a while to appear on
  that resource's cost records, separate from the latency above. `--tag-key` may show `(none)`
  for a freshly-tagged resource even after the general cost-data latency has passed.
- **Cost Management throttling** — Azure limits Cost Management API calls to roughly 4 per
  scope per minute. This tool identifies itself via a dedicated `ClientType` header and paces
  its own multi-call commands to stay well under that, and shouldn't be hit by normal use, but
  running several heavy commands back-to-back can still trigger it.
- **RBAC is a prerequisite, not something this tool manages** — it does not request, grant,
  or verify access beyond surfacing a friendly error if a call fails on missing permissions.
- **Read-only by design** — no code path creates, modifies, or deletes an Azure resource,
  including in audit mode (detection only).

## Development

```
python -m venv .venv
.venv\Scripts\activate      # Windows (use `source .venv/bin/activate` on macOS/Linux)
pip install -e ".[dev]"
pytest
```

Run `azure-finops --help` to confirm the CLI entry point is installed correctly.

## License

[MIT](LICENSE)