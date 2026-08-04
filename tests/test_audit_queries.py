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
    assert mock_client.resources.call_count == 2

    # Regression check: skip_token belongs on QueryRequestOptions, not QueryRequest
    # directly - passing it as a direct QueryRequest kwarg is silently ignored by the
    # SDK, which broke pagination without raising an error (confirmed live).
    first_request = mock_client.resources.call_args_list[0].args[0]
    second_request = mock_client.resources.call_args_list[1].args[0]
    assert first_request.options is None
    assert second_request.options.skip_token == "token-1"


def test_fetch_vms_extracts_power_state(mocker: MockerFixture) -> None:
    vm_running = SimpleNamespace(
        id=RG_VM,
        name="vm-1",
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
        instance_view=None,
    )
    mock_client = MagicMock()
    mock_client.virtual_machines.list_all.return_value = [vm_running, vm_no_instance_view]
    mocker.patch(
        "azure_finops_dashboard.audit_queries.ComputeManagementClient", return_value=mock_client
    )

    vms = fetch_vms(credential=MagicMock(), subscription_id=SUB_ID)

    assert vms[0].power_state == "PowerState/running"
    assert vms[0].resource_group == "rg-a"
    assert vms[1].power_state == ""
    mock_client.virtual_machines.list_all.assert_called_once_with(status_only="true")


def test_fetch_disks_maps_fields(mocker: MockerFixture) -> None:
    disk = SimpleNamespace(
        id=f"/subscriptions/{SUB_ID}/resourceGroups/rg-a/providers/Microsoft.Compute/disks/disk-1",
        name="disk-1",
        managed_by=None,
        disk_size_gb=64,
    )
    mock_client = MagicMock()
    mock_client.disks.list.return_value = [disk]
    mocker.patch(
        "azure_finops_dashboard.audit_queries.ComputeManagementClient", return_value=mock_client
    )

    disks = fetch_disks(credential=MagicMock(), subscription_id=SUB_ID)

    assert disks == [
        DiskInfo(
            resource_id=disk.id,
            name="disk-1",
            resource_group="rg-a",
            managed_by=None,
            disk_size_gb=64,
        )
    ]


def test_fetch_public_ips_maps_ip_configuration(mocker: MockerFixture) -> None:
    attached_ip = SimpleNamespace(
        id=f"/subscriptions/{SUB_ID}/resourceGroups/rg-a/providers/Microsoft.Network/publicIPAddresses/ip-1",
        name="ip-1",
        ip_configuration=SimpleNamespace(id="config-1"),
    )
    orphaned_ip = SimpleNamespace(
        id=f"/subscriptions/{SUB_ID}/resourceGroups/rg-a/providers/Microsoft.Network/publicIPAddresses/ip-2",
        name="ip-2",
        ip_configuration=None,
    )
    mock_client = MagicMock()
    mock_client.public_ip_addresses.list_all.return_value = [attached_ip, orphaned_ip]
    mocker.patch(
        "azure_finops_dashboard.audit_queries.NetworkManagementClient", return_value=mock_client
    )

    ips = fetch_public_ips(credential=MagicMock(), subscription_id=SUB_ID)

    assert ips[0].ip_configuration_id == "config-1"
    assert ips[1].ip_configuration_id is None
