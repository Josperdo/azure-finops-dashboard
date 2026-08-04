from dataclasses import dataclass

from rich.table import Table

SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}
SEVERITY_STYLE = {"high": "red", "medium": "yellow", "low": "dim"}


@dataclass
class ResourceInfo:
    resource_id: str
    name: str
    resource_group: str
    resource_type: str
    tags: dict[str, str]
    location: str = ""


@dataclass
class VmInfo:
    resource_id: str
    name: str
    resource_group: str
    power_state: str
    location: str = ""


@dataclass
class DiskInfo:
    resource_id: str
    name: str
    resource_group: str
    managed_by: str | None
    disk_size_gb: int
    location: str = ""


@dataclass
class PublicIpInfo:
    resource_id: str
    name: str
    resource_group: str
    ip_configuration_id: str | None
    location: str = ""


@dataclass
class Finding:
    resource_id: str
    resource_name: str
    resource_group: str
    resource_type: str
    issue: str
    severity: str  # "high" | "medium" | "low"
    subscription_id: str = ""


def find_untagged_resources(resources: list[ResourceInfo]) -> list[Finding]:
    return [
        Finding(
            resource_id=r.resource_id,
            resource_name=r.name,
            resource_group=r.resource_group,
            resource_type=r.resource_type,
            issue="No tags applied",
            severity="low",
        )
        for r in resources
        if not r.tags
    ]


def find_idle_vms(vms: list[VmInfo]) -> list[Finding]:
    findings = []
    for vm in vms:
        if vm.power_state == "PowerState/stopped":
            findings.append(
                Finding(
                    resource_id=vm.resource_id,
                    resource_name=vm.name,
                    resource_group=vm.resource_group,
                    resource_type="virtual_machine",
                    issue="VM is stopped but not deallocated — still billed for compute",
                    severity="high",
                )
            )
        elif vm.power_state == "PowerState/deallocated":
            findings.append(
                Finding(
                    resource_id=vm.resource_id,
                    resource_name=vm.name,
                    resource_group=vm.resource_group,
                    resource_type="virtual_machine",
                    issue="VM is deallocated — no compute charge, but check attached disks/IPs",
                    severity="low",
                )
            )
    return findings


def find_unattached_disks(disks: list[DiskInfo]) -> list[Finding]:
    return [
        Finding(
            resource_id=d.resource_id,
            resource_name=d.name,
            resource_group=d.resource_group,
            resource_type="managed_disk",
            issue=f"Unattached managed disk ({d.disk_size_gb} GB) — incurring storage cost",
            severity="medium",
        )
        for d in disks
        if d.managed_by is None
    ]


def find_orphaned_public_ips(ips: list[PublicIpInfo]) -> list[Finding]:
    return [
        Finding(
            resource_id=ip.resource_id,
            resource_name=ip.name,
            resource_group=ip.resource_group,
            resource_type="public_ip",
            issue="Public IP not associated with any resource — incurring cost while unused",
            severity="medium",
        )
        for ip in ips
        if ip.ip_configuration_id is None
    ]


def render_audit_report(findings: list[Finding]) -> Table:
    """Render findings as a Rich table, most severe first."""
    ordered = sorted(findings, key=lambda f: SEVERITY_ORDER.get(f.severity, 99))

    table = Table(title="FinOps Audit Findings", header_style="bold cyan")
    # overflow="fold" wraps long cell text instead of truncating with Rich's default
    # Unicode ellipsis character, which isn't cp1252-safe and renders as mojibake on
    # Windows terminals stuck on a legacy console - confirmed live, same root cause as
    # the rich.bar.Bar crash fixed earlier (trend.py's _ascii_bar).
    table.add_column("Severity", overflow="fold")
    table.add_column("Type", overflow="fold")
    table.add_column("Resource Group", overflow="fold")
    table.add_column("Name", overflow="fold")
    table.add_column("Issue", overflow="fold")
    for finding in ordered:
        style = SEVERITY_STYLE.get(finding.severity, "")
        severity_cell = f"[{style}]{finding.severity}[/{style}]" if style else finding.severity
        table.add_row(
            severity_cell,
            finding.resource_type,
            finding.resource_group,
            finding.resource_name,
            finding.issue,
        )
    return table
