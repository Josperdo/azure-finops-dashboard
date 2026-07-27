from azure_finops_dashboard.audit import (
    DiskInfo,
    Finding,
    PublicIpInfo,
    ResourceInfo,
    VmInfo,
    find_idle_vms,
    find_orphaned_public_ips,
    find_unattached_disks,
    find_untagged_resources,
    render_audit_report,
)


def test_find_untagged_resources() -> None:
    tagged = ResourceInfo("id-1", "res-1", "rg-a", "storage_account", tags={"env": "prod"})
    untagged = ResourceInfo("id-2", "res-2", "rg-a", "storage_account", tags={})

    findings = find_untagged_resources([tagged, untagged])

    assert len(findings) == 1
    assert findings[0].resource_id == "id-2"
    assert findings[0].severity == "low"


def test_find_idle_vms_stopped_is_high_severity() -> None:
    vms = [
        VmInfo("id-1", "vm-running", "rg-a", "PowerState/running"),
        VmInfo("id-2", "vm-stopped", "rg-a", "PowerState/stopped"),
        VmInfo("id-3", "vm-deallocated", "rg-a", "PowerState/deallocated"),
    ]

    findings = find_idle_vms(vms)

    assert len(findings) == 2
    stopped = next(f for f in findings if f.resource_id == "id-2")
    deallocated = next(f for f in findings if f.resource_id == "id-3")
    assert stopped.severity == "high"
    assert "still billed" in stopped.issue
    assert deallocated.severity == "low"


def test_find_unattached_disks() -> None:
    disks = [
        DiskInfo("id-1", "disk-attached", "rg-a", managed_by="vm-1", disk_size_gb=128),
        DiskInfo("id-2", "disk-orphan", "rg-a", managed_by=None, disk_size_gb=64),
    ]

    findings = find_unattached_disks(disks)

    assert len(findings) == 1
    assert findings[0].resource_id == "id-2"
    assert "64 GB" in findings[0].issue
    assert findings[0].severity == "medium"


def test_find_orphaned_public_ips() -> None:
    ips = [
        PublicIpInfo("id-1", "ip-attached", "rg-a", ip_configuration_id="config-1"),
        PublicIpInfo("id-2", "ip-orphan", "rg-a", ip_configuration_id=None),
    ]

    findings = find_orphaned_public_ips(ips)

    assert len(findings) == 1
    assert findings[0].resource_id == "id-2"
    assert findings[0].severity == "medium"


def test_render_audit_report_orders_by_severity() -> None:
    findings = [
        Finding("id-1", "res-low", "rg-a", "resource", "no tags", "low"),
        Finding("id-2", "res-high", "rg-a", "virtual_machine", "stopped", "high"),
        Finding("id-3", "res-medium", "rg-a", "managed_disk", "unattached", "medium"),
    ]

    table = render_audit_report(findings)
    severity_column = [str(cell) for cell in table.columns[0].cells]
    name_column = [str(cell) for cell in table.columns[3].cells]

    assert table.row_count == 3
    assert severity_column == ["high", "medium", "low"]
    assert name_column == ["res-high", "res-medium", "res-low"]
