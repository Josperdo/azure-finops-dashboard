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

## Authentication

Uses `DefaultAzureCredential` exclusively (environment → managed identity → Azure CLI →
interactive browser). No API keys, connection strings, or client secrets. Requires **Reader**
and **Cost Management Reader** RBAC roles on the target subscription(s) — nothing broader.

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