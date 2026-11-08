# Changelog

All notable changes to this project are documented here. Format based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow
[Semantic Versioning](https://semver.org/).

## [0.1.0] - Unreleased

Initial release.

### Added
- `DefaultAzureCredential`-only authentication and subscription discovery
  (`subscriptions list`, `--subscription`, `--all-subscriptions`, optional config file).
- `cost summary`: spend by service, resource group, and tag key (repeatable `--tag-key`),
  month-to-date / last-month / custom date ranges, and a cross-subscription `--rollup`.
- `cost trend`: six-month spend trend with month-over-month change.
- `budget status`: Azure Consumption budget retrieval with 80% warning / 100% breach flags.
- `audit run`: untagged resources, stopped/deallocated VMs, unattached disks, orphaned
  public IPs, with `--region` filtering.
- `dashboard`: summary + trend + budgets in one command.
- CSV / JSON / PDF export via repeatable `--output`, on all reporting commands.
- CI: ruff (lint + format), mypy strict, pytest, and pip-audit on Linux and Windows across
  Python 3.10-3.13.

### Security
- `cryptography>=50.0.0` pinned directly after `pip-audit` flagged a known CVE in the
  transitive version.
