"""E6 compiler: servicios tipados, deterministas y ligados a E4/E5."""

from __future__ import annotations

from copy import deepcopy
from time import perf_counter

from src.packet_tracer_mcp.application.use_cases.compile_services import (
    compile_enterprise_services,
)
from src.packet_tracer_mcp.domain.enterprise.models.configuration import (
    ConfigurationIssueCode,
    ConfigurationPhase,
    ConfigurationPlan,
    SetEndpointStaticAddress,
)
from src.packet_tracer_mcp.domain.enterprise.models.enterprise_plan import (
    EnterprisePlan,
    SitePlan,
)
from src.packet_tracer_mcp.domain.enterprise.models.intent import SiteType
from src.packet_tracer_mcp.domain.enterprise.models.requirements import (
    DnsRecordRequirement,
    ServiceRequirement,
    TftpFileRequirement,
)
from src.packet_tracer_mcp.domain.enterprise.models.service_plan import (
    AddDnsRecord,
    EnableDnsService,
    EnableHttpService,
    PublishTftpFile,
    ServiceActionType,
    ServiceCapabilityProfile,
    ServiceType,
    SetHttpContent,
)
from src.packet_tracer_mcp.domain.enterprise.models.capabilities import CapabilityStatus
from src.packet_tracer_mcp.domain.models.plans import DevicePlan, TopologyPlan


def _foundation_action(device_id: str, name: str, address: str, segment: str = "hq-servers"):
    return SetEndpointStaticAddress(
        id=f"cfg/static/{device_id}",
        phase=ConfigurationPhase.ENDPOINT_ADDRESSING,
        device_id=device_id,
        device_name=name,
        site_id="hq",
        interface="FastEthernet0",
        ipv4=address,
        netmask="255.255.255.0",
        gateway="198.18.160.1",
        dns_server="198.18.160.10",
        segment_id=segment,
        required_capability="endpoint_static",
    )


def _fixture(services: list[ServiceRequirement] | None = None):
    services = services or [
        ServiceRequirement(
            name="central-dns",
            service_type=ServiceType.DNS,
            host_device_id="srv-1",
            client_device_ids=["pc-1"],
            dns_records=[DnsRecordRequirement(
                hostname="web.e6.example.local", address="198.18.160.10",
                target_device_id="srv-1",
            )],
        ),
        ServiceRequirement(
            name="intranet",
            service_type=ServiceType.HTTP,
            host_device_id="srv-1",
            client_device_ids=["pc-1"],
            hostname="web.e6.example.local",
            http_content="MCP_E6_HTTP_OK_REFERENCE",
        ),
    ]
    enterprise = EnterprisePlan(
        id="enterprise-e6",
        name="E6",
        sites=[SitePlan(
            name="HQ", site_id="hq", type=SiteType.HQ, services=services,
        )],
    )
    topology = TopologyPlan(
        id="topology-e6",
        semantic_hash="e4-semantic-hash",
        devices=[
            DevicePlan(
                id="srv-1", name="HQ-SERVER-01", model="Server-PT", category="server",
                enterprise_role="dns_server", site_id="hq",
            ),
            DevicePlan(
                id="pc-1", name="HQ-PC-01", model="PC-PT", category="pc",
                enterprise_role="user_pc", site_id="hq",
            ),
        ],
    )
    configuration = ConfigurationPlan(
        id="cfg-e6",
        source_topology_id=topology.id,
        source_topology_hash=topology.semantic_hash,
        semantic_hash="e5-semantic-hash",
        actions=[
            _foundation_action("srv-1", "HQ-SERVER-01", "198.18.160.10"),
            _foundation_action("pc-1", "HQ-PC-01", "198.18.160.20", "hq-data"),
        ],
    )
    capabilities = {
        "Server-PT:dns": ServiceCapabilityProfile(
            service_type=ServiceType.DNS,
            compile_support=CapabilityStatus.SUPPORTED,
            application_support=CapabilityStatus.SUPPORTED,
            direct_readback_support=CapabilityStatus.UNKNOWN,
            behavioral_verification_support=CapabilityStatus.SUPPORTED,
        ),
        "Server-PT:http": ServiceCapabilityProfile(
            service_type=ServiceType.HTTP,
            compile_support=CapabilityStatus.SUPPORTED,
            application_support=CapabilityStatus.SUPPORTED,
            direct_readback_support=CapabilityStatus.UNKNOWN,
            behavioral_verification_support=CapabilityStatus.SUPPORTED,
        ),
    }
    return enterprise, topology, configuration, capabilities


def _compile(services: list[ServiceRequirement] | None = None):
    enterprise, topology, configuration, capabilities = _fixture(services)
    return compile_enterprise_services(
        enterprise, topology, configuration, capabilities=capabilities,
    )


def test_service_plan_is_deterministic_10_of_10_and_input_order_independent():
    enterprise, topology, configuration, capabilities = _fixture()
    hashes = {
        compile_enterprise_services(
            deepcopy(enterprise), deepcopy(topology), deepcopy(configuration),
            capabilities=deepcopy(capabilities),
        ).semantic_hash
        for _ in range(10)
    }
    reordered = deepcopy(enterprise)
    reordered.sites[0].services.reverse()
    for service in reordered.sites[0].services:
        service.client_device_ids.reverse()
        service.dns_records.reverse()
    other = compile_enterprise_services(
        reordered, topology, configuration, capabilities=capabilities,
    )

    assert len(hashes) == 1
    assert other.semantic_hash == next(iter(hashes))


def test_plan_binds_e4_and_e5_hashes_and_emits_compact_summary():
    result = _compile()

    assert result.is_valid
    assert result.plan.source_topology_hash == "e4-semantic-hash"
    assert result.plan.source_configuration_hash == "e5-semantic-hash"
    assert len(result.plan.semantic_hash) == 64
    summary = result.compact_summary()
    assert "services" not in summary
    assert summary["service_count"] == 2
    assert summary["actions_by_type"]["add_dns_record"] == 1


def test_dns_compiles_closed_actions_deduplicates_identical_records_and_stable_order():
    dns = ServiceRequirement(
        name="dns", service_type=ServiceType.DNS, host_device_id="srv-1",
        client_device_ids=["pc-1"],
        dns_records=[
            DnsRecordRequirement(hostname="b.example.local", address="198.18.160.10"),
            DnsRecordRequirement(hostname="a.example.local", address="198.18.160.10"),
            DnsRecordRequirement(hostname="a.example.local", address="198.18.160.10"),
        ],
    )
    result = _compile([dns])
    records = [action for action in result.plan.actions if isinstance(action, AddDnsRecord)]

    assert result.is_valid
    assert len(result.plan.actions_of_type(ServiceActionType.ENABLE_DNS)) == 1
    assert [record.hostname for record in records] == ["a.example.local", "b.example.local"]
    assert all(isinstance(action, (EnableDnsService, AddDnsRecord)) for action in result.plan.actions)


def test_conflicting_dns_record_is_a_structured_compile_error():
    dns = ServiceRequirement(
        name="dns", service_type=ServiceType.DNS, host_device_id="srv-1",
        dns_records=[
            DnsRecordRequirement(hostname="same.example.local", address="198.18.160.10"),
            DnsRecordRequirement(hostname="same.example.local", address="198.18.160.11"),
        ],
    )
    result = _compile([dns])

    assert not result.is_valid
    assert result.plan is None
    assert ConfigurationIssueCode.DNS_RECORD_CONFLICT in {item.code for item in result.issues}


def test_invalid_hostname_and_unknown_target_are_rejected():
    dns = ServiceRequirement(
        name="dns", service_type=ServiceType.DNS, host_device_id="srv-1",
        dns_records=[DnsRecordRequirement(
            hostname="bad name;reload", address="198.18.160.10",
            target_device_id="missing-device",
        )],
    )
    result = _compile([dns])
    codes = {item.code for item in result.issues}

    assert not result.is_valid
    assert ConfigurationIssueCode.DNS_HOSTNAME_INVALID in codes
    assert ConfigurationIssueCode.SERVICE_HOST_MISSING in codes


def test_service_host_uses_existing_e4_role_deterministically_without_model_reselection():
    requirement = ServiceRequirement(
        name="dns", service_type=ServiceType.DNS,
        dns_records=[DnsRecordRequirement(hostname="x.example.local", address="198.18.160.10")],
    )
    result = _compile([requirement])

    assert result.is_valid
    service = result.plan.services[0]
    assert service.host_device_id == "srv-1"
    assert service.host_model == "Server-PT"


def test_missing_or_mismatched_foundational_configuration_never_invokes_e5():
    enterprise, topology, configuration, capabilities = _fixture()
    configuration.actions = [action for action in configuration.actions if action.device_id != "srv-1"]
    result = compile_enterprise_services(
        enterprise, topology, configuration, capabilities=capabilities,
    )

    assert not result.is_valid
    assert ConfigurationIssueCode.FOUNDATIONAL_CONFIGURATION_MISSING in {
        item.code for item in result.issues
    }


def test_stale_e5_topology_binding_is_rejected():
    enterprise, topology, configuration, capabilities = _fixture()
    configuration.source_topology_hash = "other-topology"
    result = compile_enterprise_services(
        enterprise, topology, configuration, capabilities=capabilities,
    )

    assert not result.is_valid
    assert ConfigurationIssueCode.SOURCE_CONFIGURATION_TOPOLOGY_MISMATCH in {
        item.code for item in result.issues
    }


def test_http_actions_are_typed_and_hostname_verification_depends_on_dns_and_ip_fetch():
    result = _compile()
    http = next(item for item in result.plan.services if item.service_type is ServiceType.HTTP)
    http_actions = [
        action for action in result.plan.actions if action.service_id == http.id
    ]
    composed = next(
        item for item in result.plan.verification_expectations
        if item.kind.value == "http_by_hostname"
    )

    assert any(isinstance(action, EnableHttpService) for action in http_actions)
    assert any(isinstance(action, SetHttpContent) for action in http_actions)
    dependency_kinds = {
        item.kind.value for item in result.plan.verification_expectations
        if item.id in composed.depends_on
    }
    assert dependency_kinds == {"dns_resolution", "http_fetch"}


def test_tftp_rejects_paths_and_hashes_safe_content_without_host_file_access():
    unsafe = ServiceRequirement(
        name="tftp", service_type=ServiceType.TFTP, host_device_id="srv-1",
        tftp_files=[TftpFileRequirement(filename="../running-config", content="x")],
    )
    result = _compile([unsafe])
    assert not result.is_valid
    assert ConfigurationIssueCode.TFTP_FILENAME_UNSAFE in {item.code for item in result.issues}

    safe = deepcopy(unsafe)
    safe.tftp_files = [TftpFileRequirement(filename="e6-test.txt", content="MCP_E6_TFTP_OK")]
    result = _compile([safe])
    publish = next(action for action in result.plan.actions if isinstance(action, PublishTftpFile))
    assert publish.filename == "e6-test.txt"
    assert publish.content_sha256
    assert not hasattr(publish, "source_path")


def test_service_dependency_cycle_is_reported_without_a_plan():
    services = [
        ServiceRequirement(
            name="dns", service_type=ServiceType.DNS, host_device_id="srv-1",
            depends_on=["http"],
        ),
        ServiceRequirement(
            name="http", service_type=ServiceType.HTTP, host_device_id="srv-1",
            depends_on=["dns"], http_content="MCP_E6_HTTP_OK",
        ),
    ]
    result = _compile(services)

    assert not result.is_valid
    assert ConfigurationIssueCode.DEPENDENCY_CYCLE in {item.code for item in result.issues}


def test_unknown_application_capability_is_warning_not_fabricated_support():
    enterprise, topology, configuration, capabilities = _fixture()
    capabilities["Server-PT:dns"].application_support = CapabilityStatus.UNKNOWN
    result = compile_enterprise_services(
        enterprise, topology, configuration, capabilities=capabilities,
    )

    assert result.is_valid
    assert ConfigurationIssueCode.CAPABILITY_UNVERIFIED in {item.code for item in result.issues}


def test_compilation_stays_interactive_for_137_devices():
    enterprise, topology, configuration, capabilities = _fixture()
    for index in range(2, 137):
        device_id = f"pc-{index}"
        name = f"HQ-PC-{index:03d}"
        topology.devices.append(DevicePlan(
            id=device_id, name=name, model="PC-PT", category="pc",
            enterprise_role="user_pc", site_id="hq",
        ))
        configuration.actions.append(_foundation_action(
            device_id, name, f"198.19.{index // 250}.{index % 250 + 1}", "hq-data",
        ))
    enterprise.sites[0].services[0].client_device_ids = [
        device.id for device in topology.devices if device.id.startswith("pc-")
    ]
    started = perf_counter()
    result = compile_enterprise_services(
        enterprise, topology, configuration, capabilities=capabilities,
    )
    elapsed = perf_counter() - started

    assert result.is_valid
    assert result.summary.service_count == 2
    assert elapsed < 2.0
