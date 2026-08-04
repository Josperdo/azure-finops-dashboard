from types import SimpleNamespace
from unittest.mock import MagicMock

from pytest_mock import MockerFixture

from azure_finops_dashboard.audit import DiskInfo
from azure_finops_dashboard.audit_queries import (
    _resource_group_from_id,
    fetch_disks,
    fetch_public_ips,
    fetch_resources,
    fetch_vms,
)

SUB_ID = "sub-1"
RG_VM = (
    f"/subscriptions/{SUB_ID}/resourceGroups/rg-a/providers/Microsoft.Compute/virtualMachines/vm-1"
)


def test_resource_group_from_id() -> None:
    assert _resource_group_from_id(RG_VM) == "rg-a"


def test_resource_group_from_id_missing_segment() -> None:
    assert _resource_group_from_id("/subscriptions/sub-1/providers/Microsoft.Foo") == ""


def test_fetch_resources_paginates_and_maps_fields(mocker: MockerFixture) -> None:
    page1 = SimpleNamespace(
        data=[
            {
                "id": "id-1",
                "name": "res-1",
                "resourceGroup": "rg-a",
                "type": "Microsoft.Storage/storageAccounts",
                "tags": {"env": "prod"},
                "location": "eastus",
            }
        ],
        skip_token="token-1",
    )
    page2 = SimpleNamespace(
        data=[
            {
                "id": "id-2",
                "name": "res-2",
                "resourceGroup": "rg-a",
                "type": "Microsoft.Compute/disks",
                "tags": None,
                "location": "eastus2",
            }
        ],
        skip_token=None,
    )
    mock_client = MagicMock()
    mock_client.resources.side_effect = [page1, page2]
    mocker.patch(
        "azure_finops_dashboard.audit_queries.ResourceGraphClient", return_value=mock_client
    )

    resources = fetch_resources(credential=MagicMock(), subscription_id=SUB_ID)

    assert len(resources) == 2
    assert resources[0].tags == {"env": "prod"}
    assert resources[1].tags == {}  # null tags normalized to empty dict
    assert resources[0].location == "eastus"
    assert mock_client.resources.call_count == 2

    # Regression check: skip_token belongs on QueryRequestOptions, not QueryRequest
    # directly - passing it as a direct QueryRequest kwarg is silently ignored by the
    # SDK, which broke pagination without raising an error (confirmed live).
    first_request = mock_client.resources.call_args_list[0].args[0]
    second_request = mock_client.resources.call_args_list[1].args[0]
    assert first_request.options is None
    assert second_request.options.skip_token == "token-1"


def test_fetch_resources_filters_by_region(mocker: MockerFixture) -> None:
    page = SimpleNamespace(
        data=[
            {
                "id": "id-1",
                "name": "res-1",
                "resourceGroup": "rg-a",
                "type": "Microsoft.Storage/storageAccounts",
                "tags": {},
                "location": "eastus",
            },
            {
                "id": "id-2",
                "name": "res-2",
                "resourceGroup": "rg-a",
                "type": "Microsoft.Compute/disks",
                "tags": {},
                "location": "eastus2",
            },
        ],
        skip_token=None,
    )
    mock_client = MagicMock()
    mock_client.resources.return_value = page
    mocker.patch(
        "azure_finops_dashboard.audit_queries.ResourceGraphClient", return_value=mock_client
    )

    resources = fetch_resources(credential=MagicMock(), subscription_id=SUB_ID, regions=["EastUS2"])

    assert [r.name for r in resources] == ["res-2"]  # case-insensitive match


def test_fetch_vms_extracts_power_state(mocker: MockerFixture) -> None:
    vm_running = SimpleNamespace(
        id=RG_VM,
        name="vm-1",
        location="eastus",
        instance_view=SimpleNamespace(
            statuses=[
                SimpleNamespace(code="ProvisioningState/succeeded"),
                SimpleNamespace(code="PowerState/running"),
            ]
        ),
    )
    vm_no_instance_view = SimpleNamespace(
        id=f"/subscriptions/{SUB_ID}/resourceGroups/rg-b/providers/Microsoft.Compute/virtualMachines/vm-2",
        name="vm-2",
        location="eastus2",
        instance_view=None,
    )
    vm_missing_id = SimpleNamespace(id=None, name="vm-3", location="eastus", instance_view=None)
    mock_client = MagicMock()
    mock_client.virtual_machines.list_all.return_value = [
        vm_running,
        vm_no_instance_view,
        vm_missing_id,
    ]
    mocker.patch(
        "azure_finops_dashboard.audit_queries.ComputeManagementClient", return_value=mock_client
    )

    vms = fetch_vms(credential=MagicMock(), subscription_id=SUB_ID)

    assert len(vms) == 2  # vm_missing_id skipped - malformed SDK data, no usable ID
    assert vms[0].power_state == "PowerState/running"
    assert vms[0].resource_group == "rg-a"
    assert vms[0].location == "eastus"
    assert vms[1].power_state == ""
    mock_client.virtual_machines.list_all.assert_called_once_with(status_only="true")


def test_fetch_vms_filters_by_region(mocker: MockerFixture) -> None:
    vm_east = SimpleNamespace(id=RG_VM, name="vm-1", location="eastus", instance_view=None)
    vm_west = SimpleNamespace(
        id=f"/subscriptions/{SUB_ID}/resourceGroups/rg-b/providers/Microsoft.Compute/virtualMachines/vm-2",
        name="vm-2",
        location="westus",
        instance_view=None,
    )
    mock_client = MagicMock()
    mock_client.virtual_machines.list_all.return_value = [vm_east, vm_west]
    mocker.patch(
        "azure_finops_dashboard.audit_queries.ComputeManagementClient", return_value=mock_client
    )

    vms = fetch_vms(credential=MagicMock(), subscription_id=SUB_ID, regions=["eastus"])

    assert [v.name for v in vms] == ["vm-1"]


def test_fetch_disks_maps_fields(mocker: MockerFixture) -> None:
    disk = SimpleNamespace(
        id=f"/subscriptions/{SUB_ID}/resourceGroups/rg-a/providers/Microsoft.Compute/disks/disk-1",
        name="disk-1",
        managed_by=None,
        disk_size_gb=64,
        location="eastus",
    )
    disk_missing_name = SimpleNamespace(
        id="id-x", name=None, managed_by=None, disk_size_gb=1, location="eastus"
    )
    mock_client = MagicMock()
    mock_client.disks.list.return_value = [disk, disk_missing_name]
    mocker.patch(
        "azure_finops_dashboard.audit_queries.ComputeManagementClient", return_value=mock_client
    )

    disks = fetch_disks(credential=MagicMock(), subscription_id=SUB_ID)

    assert disks == [  # disk_missing_name skipped - malformed SDK data, no usable name
        DiskInfo(
            resource_id=disk.id,
            name="disk-1",
            resource_group="rg-a",
            managed_by=None,
            disk_size_gb=64,
            location="eastus",
        )
    ]


def test_fetch_disks_filters_by_region(mocker: MockerFixture) -> None:
    disk_east = SimpleNamespace(
        id="id-1", name="disk-1", managed_by=None, disk_size_gb=1, location="eastus"
    )
    disk_west = SimpleNamespace(
        id="id-2", name="disk-2", managed_by=None, disk_size_gb=1, location="westus"
    )
    mock_client = MagicMock()
    mock_client.disks.list.return_value = [disk_east, disk_west]
    mocker.patch(
        "azure_finops_dashboard.audit_queries.ComputeManagementClient", return_value=mock_client
    )

    disks = fetch_disks(credential=MagicMock(), subscription_id=SUB_ID, regions=["westus"])

    assert [d.name for d in disks] == ["disk-2"]


def test_fetch_public_ips_maps_ip_configuration(mocker: MockerFixture) -> None:
    attached_ip = SimpleNamespace(
        id=f"/subscriptions/{SUB_ID}/resourceGroups/rg-a/providers/Microsoft.Network/publicIPAddresses/ip-1",
        name="ip-1",
        location="eastus",
        ip_configuration=SimpleNamespace(id="config-1"),
    )
    orphaned_ip = SimpleNamespace(
        id=f"/subscriptions/{SUB_ID}/resourceGroups/rg-a/providers/Microsoft.Network/publicIPAddresses/ip-2",
        name="ip-2",
        location="eastus",
        ip_configuration=None,
    )
    ip_missing_id = SimpleNamespace(id=None, name="ip-3", location="eastus", ip_configuration=None)
    mock_client = MagicMock()
    mock_client.public_ip_addresses.list_all.return_value = [
        attached_ip,
        orphaned_ip,
        ip_missing_id,
    ]
    mocker.patch(
        "azure_finops_dashboard.audit_queries.NetworkManagementClient", return_value=mock_client
    )

    ips = fetch_public_ips(credential=MagicMock(), subscription_id=SUB_ID)

    assert len(ips) == 2  # ip_missing_id skipped - malformed SDK data, no usable ID
    assert ips[0].ip_configuration_id == "config-1"
    assert ips[1].ip_configuration_id is None


def test_fetch_public_ips_filters_by_region(mocker: MockerFixture) -> None:
    ip_east = SimpleNamespace(id="id-1", name="ip-1", location="eastus", ip_configuration=None)
    ip_west = SimpleNamespace(id="id-2", name="ip-2", location="westus", ip_configuration=None)
    mock_client = MagicMock()
    mock_client.public_ip_addresses.list_all.return_value = [ip_east, ip_west]
    mocker.patch(
        "azure_finops_dashboard.audit_queries.NetworkManagementClient", return_value=mock_client
    )

    ips = fetch_public_ips(credential=MagicMock(), subscription_id=SUB_ID, regions=["eastus"])

    assert [ip.name for ip in ips] == ["ip-1"]
