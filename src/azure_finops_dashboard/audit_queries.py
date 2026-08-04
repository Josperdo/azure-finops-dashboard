"""Live Azure queries that populate audit.py's detector inputs.

Kept separate from audit.py on purpose: audit.py's detection logic is pure/SDK-free and
fully unit-tested against fixture data, this module is the SDK-calling counterpart that
maps real Azure responses onto those same dataclasses - mirrors the cost.py/query_utils.py
split already used for cost data.
"""

from typing import Any, cast

from azure.core.credentials import TokenCredential
from azure.mgmt.compute import ComputeManagementClient
from azure.mgmt.network import NetworkManagementClient
from azure.mgmt.resourcegraph import ResourceGraphClient
from azure.mgmt.resourcegraph.models import QueryRequest, QueryRequestOptions

from azure_finops_dashboard.audit import DiskInfo, PublicIpInfo, ResourceInfo, VmInfo
from azure_finops_dashboard.client_config import CLIENT_KWARGS


def _resource_group_from_id(resource_id: str) -> str:
    """Parse the resource group name out of an ARM resource ID.

    Compute/Network list_all() responses don't include a separate resource-group field
    (unlike the Resource Graph query below, which explicitly projects one).
    """
    parts = resource_id.split("/")
    for i, part in enumerate(parts):
        if part.lower() == "resourcegroups" and i + 1 < len(parts):
            return parts[i + 1]
    return ""


def fetch_resources(credential: TokenCredential, subscription_id: str) -> list[ResourceInfo]:
    """List every resource in the subscription, for untagged-resource detection."""
    client = ResourceGraphClient(credential, **CLIENT_KWARGS)
    query = "Resources | project id, name, resourceGroup, type, tags"

    resources = []
    skip_token: str | None = None
    while True:
        # skip_token belongs on QueryRequestOptions, not QueryRequest directly - confirmed
        # live: passing it straight to QueryRequest silently drops it and pagination
        # never actually advanced past the first page.
        options = QueryRequestOptions(skip_token=skip_token) if skip_token else None
        request = QueryRequest(subscriptions=[subscription_id], query=query, options=options)
        result = client.resources(request)
        # The SDK stub types `.data` as a single MutableMapping, but resultFormat
        # "objectArray" (the default) actually returns a list of row dicts - confirmed
        # live against this same API earlier this session; the stub is just wrong here.
        rows = cast("list[dict[str, Any]]", result.data)
        for row in rows:
            resources.append(
                ResourceInfo(
                    resource_id=row["id"],
                    name=row["name"],
                    resource_group=row["resourceGroup"],
                    resource_type=row["type"],
                    tags=row.get("tags") or {},
                )
            )
        skip_token = getattr(result, "skip_token", None)
        if not skip_token:
            break
    return resources


def fetch_vms(credential: TokenCredential, subscription_id: str) -> list[VmInfo]:
    """List VMs with their power state, for idle-VM detection."""
    client = ComputeManagementClient(credential, subscription_id, **CLIENT_KWARGS)
    vms = []
    # status_only is a query-string flag, not a Python bool - the SDK forwards it as-is.
    for vm in client.virtual_machines.list_all(status_only="true"):
        if vm.id is None or vm.name is None:
            continue
        power_state = ""
        if vm.instance_view and vm.instance_view.statuses:
            for status in vm.instance_view.statuses:
                if status.code and status.code.startswith("PowerState/"):
                    power_state = status.code
                    break
        vms.append(
            VmInfo(
                resource_id=vm.id,
                name=vm.name,
                resource_group=_resource_group_from_id(vm.id),
                power_state=power_state,
            )
        )
    return vms


def fetch_disks(credential: TokenCredential, subscription_id: str) -> list[DiskInfo]:
    """List managed disks, for unattached-disk detection."""
    client = ComputeManagementClient(credential, subscription_id, **CLIENT_KWARGS)
    disks = []
    for disk in client.disks.list():
        if disk.id is None or disk.name is None:
            continue
        disks.append(
            DiskInfo(
                resource_id=disk.id,
                name=disk.name,
                resource_group=_resource_group_from_id(disk.id),
                managed_by=disk.managed_by,
                disk_size_gb=disk.disk_size_gb or 0,
            )
        )
    return disks


def fetch_public_ips(credential: TokenCredential, subscription_id: str) -> list[PublicIpInfo]:
    """List public IPs, for orphaned-IP detection."""
    client = NetworkManagementClient(credential, subscription_id, **CLIENT_KWARGS)
    ips = []
    for ip in client.public_ip_addresses.list_all():
        if ip.id is None or ip.name is None:
            continue
        ips.append(
            PublicIpInfo(
                resource_id=ip.id,
                name=ip.name,
                resource_group=_resource_group_from_id(ip.id),
                ip_configuration_id=ip.ip_configuration.id if ip.ip_configuration else None,
            )
        )
    return ips
