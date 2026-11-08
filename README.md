# azure-finops-dashboard

[![CI](https://github.com/Josperdo/azure-finops-dashboard/actions/workflows/ci.yml/badge.svg)](https://github.com/Josperdo/azure-finops-dashboard/actions/workflows/ci.yml)
![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

A read-only Python CLI for Azure cost visibility and governance. Pulls spend across one or
more subscriptions, flags budget breaches, shows a six-month trend, and audits for wasted or
ungoverned resources. Modeled on [aws-finops-dashboard](https://github.com/ravikiranvm/aws-finops-dashboard),
rebuilt around Azure's model (one identity, many subscriptions).

<!-- TODO: add screenshots here (redacted / throwaway subscription only):
     docs/dashboard.png, docs/audit.png, docs/trend.png -->

## What it does

- Cost breakdowns by subscription, service, resource group, and tag
- Budget breach detection (Azure Consumption budgets)
- Six-month spend trend with month-over-month change
- **FinOps audit mode:** untagged resources, stopped/idle VMs, unattached disks, orphaned
  public IPs (detection only, never remediation)
- CSV / JSON / PDF export, multiple formats in one run
- Rich terminal UI

## Installation

```
pip install git+https://github.com/Josperdo/azure-finops-dashboard.git
```

Requires Python 3.10+ and an authenticated Azure identity (`az login` is the simplest).

## Quick start

1. Sign in: `az login`
2. Grant the identity read access (see [Required permissions](#required-permissions)).
3. Run:

```
azure-finops subscriptions list
azure-finops dashboard --all-subscriptions
```

## Usage

```
azure-finops subscriptions list                          # subscriptions visible to this identity
azure-finops cost summary --all-subscriptions             # MTD spend by service/resource group
azure-finops cost summary --all-subscriptions --tag-key Environment   # + breakdown by tag value
azure-finops cost summary --all-subscriptions --start 2026-07-01 --end 2026-07-31  # custom range
azure-finops cost summary --all-subscriptions --rollup    # + combined view across subscriptions
azure-finops cost summary --all-subscriptions --output report.csv --output report.pdf  # export
azure-finops cost trend --all-subscriptions                # 6-month spend trend
azure-finops budget status --all-subscriptions             # budget breach status
azure-finops audit run --all-subscriptions --region eastus2   # untagged/idle/unattached/orphaned
azure-finops dashboard --all-subscriptions                  # summary + trend + budgets in one run
```

`--subscription` (a subscription ID, repeatable) or `--all-subscriptions` selects scope on
every command. `--output` is repeatable, and the format is inferred from the extension
(`.csv`, `.json`, `.pdf`). Run `azure-finops <command> --help` for all options.

Optional defaults can be stored in `~/.azure-finops/config.json` (tenant and subscription IDs
only, never credentials).

## Authentication

Uses `DefaultAzureCredential` and nothing else (environment, managed identity, Azure CLI,
interactive browser). The tool itself never reads, prompts for, or stores keys, connection
strings, or client secrets, and offers no key-based login path of its own. `az login` or a
managed identity is the recommended setup. (Note: the standard Azure credential chain will
honor `AZURE_*` environment variables if you set them; that is Azure SDK behavior, not
something this tool adds.)

### Required permissions

**Reader** and **Cost Management Reader** at subscription scope (or a management group above
it). Nothing broader is needed for any feature:

```
az role assignment create --assignee <principal-id> --role "Reader" \
  --scope /subscriptions/<subscription-id>
az role assignment create --assignee <principal-id> --role "Cost Management Reader" \
  --scope /subscriptions/<subscription-id>
```

If a feature ever seems to need more, the feature should be redesigned rather than the role
widened. The tool does not request, grant, or verify access; on a 403 it prints a friendly
error naming the missing role.

## Security considerations

- **Read-only by design.** No code path creates, modifies, or deletes an Azure resource,
  including audit mode.
- **Keyless.** No secrets in code, config, or logs. The config file holds only IDs.
- **Least privilege.** Two built-in read-only roles cover everything.
- **Inputs are validated.** Subscription IDs must be GUIDs (they're used in ARM scope paths),
  dates are parsed strictly as ISO dates, and export formats are limited to an extension
  allowlist. Region filtering happens client-side, and tag keys are passed as API grouping
  names rather than interpolated into query strings. Azure errors are translated into short
  messages instead of dumped raw.
- **Exports may contain real cost and resource data.** Treat generated CSV/JSON/PDF files as
  sensitive, and do not commit them (the repo's `.gitignore` excludes `exports/` and `output/`).
- **Dependencies are scanned.** CI runs `pip-audit` on every push. It has already caught real
  advisories (a transitive `cryptography` version and a vulnerable `setuptools`).

## How it works

```
cli.py (Typer) ──► config.py / auth.py        scope resolution + DefaultAzureCredential
      │
      ├──► cost.py, trend.py ──► Cost Management Query API
      ├──► budgets.py ─────────► Consumption API
      ├──► audit_queries.py ───► Resource Graph / Compute / Network  (fetch + map)
      │         └──► audit.py                                        (pure detectors)
      └──► export.py ──────────► CSV / JSON / PDF (reportlab)
```

Fetching is kept separate from detection: the audit detectors in `audit.py` are pure
functions over dataclasses, so they're tested against fixture data with no SDK mocking.

### Design notes

Lessons from running against a real subscription, rather than trusting SDK type stubs:

- **Throttling (HTTP 429), root-caused.** Callers that omit a `ClientType` header share one
  rate-limit pool with every other such caller in the tenant. The tool sets its own
  `ClientType` and paces multi-call commands (Cost Management allows roughly 4 calls per scope
  per minute) instead of just retrying.
- **API shape surprises caught live.** `TagKey` groupings return generic `TagKey`/`TagValue`
  columns, monthly queries return `BillingMonth` instead of `UsageDate`, zero-cost months are
  omitted entirely (now backfilled), and Resource Graph silently ignores a mis-placed
  `skip_token`. Each now has a regression test.
- **Idle VMs vs. wasted VMs.** A `stopped` VM is still billed; a `deallocated` one is not. The
  audit treats them differently.
- **Terminal portability.** Output degrades cleanly on legacy Windows (cp1252) consoles
  instead of crashing on Unicode characters.

## Testing

```
pip install -e ".[dev]"
pytest
```

Unit tests mock the Azure SDK clients; CI makes no live Azure calls. Cost aggregation,
budget-breach logic, each audit detector, and export formats are tested against fixture
data. CI also runs `ruff` (lint and format), `mypy --strict`, and `pip-audit` on Linux and
Windows across Python 3.10-3.13. Live behavior was verified manually against a personal
subscription before each phase was considered done.

## Known limitations

- **Cost Management data latency.** Azure's cost data typically lags actual spend by up to
  24-48h; this tool reflects that, not real-time usage.
- **Tag propagation latency.** A freshly applied tag can take a while to show up on cost
  records, so `--tag-key` may show `(none)` for it.
- **Cost Management throttling.** Roughly 4 calls per scope per minute. Normal use stays under
  it, but several heavy commands back-to-back can trigger a (cleanly reported) 429.
- **Multi-subscription behavior is unit-tested only.** `--rollup` and repeated `--tag-key`
  were developed against a single-subscription test environment, so merging across several
  subscriptions has not been exercised live.
- **RBAC is a prerequisite**, not something this tool manages.
- **Read-only.** There are no remediation actions.

## Future work

Cost anomaly detection, scheduled / non-interactive report generation, Slack and Azure Blob
export, multi-tenant aggregation, and Reserved Instance / Savings Plan utilization.

## Development

```
python -m venv .venv
.venv\Scripts\activate      # Windows (use `source .venv/bin/activate` on macOS/Linux)
pip install -e ".[dev]"
pre-commit install
pytest
```

See [CHANGELOG.md](CHANGELOG.md) for release notes.

## License

[MIT](LICENSE)
