"""E3.5 offline: sesiones seguras, snapshots y evidencia versionada."""

from __future__ import annotations

from src.packet_tracer_mcp.application.use_cases.capability_discovery import (
    CapabilityDiscoveryService,
    CapabilityProbeRegistry,
)
from src.packet_tracer_mcp.domain.enterprise.models.capabilities import (
    CapabilityEvidence,
    CapabilityStatus,
    DeviceRequirement,
    EvidenceSource,
)
from src.packet_tracer_mcp.domain.enterprise.models.discovery import (
    CapabilityProbeResult,
    CapabilitySnapshot,
    CleanupStatus,
    ProbeExecutionStatus,
    ProbeLevel,
    ProbeRequest,
    ProbeSession,
    ProbeSessionResult,
    RuntimeDeviceObservation,
    RuntimePortDescriptor,
)
from src.packet_tracer_mcp.domain.enterprise.models.roles import DeviceRole
from src.packet_tracer_mcp.domain.enterprise.services.capability_resolver import CapabilityResolver
from src.packet_tracer_mcp.domain.enterprise.services.device_selector import DeviceSelector
from src.packet_tracer_mcp.infrastructure.catalog.capability_providers import (
    ProbeCapabilityProvider,
    StaticVerifiedCapabilityProvider,
)
from src.packet_tracer_mcp.infrastructure.catalog.enterprise_capabilities import EnterpriseCapabilityAdapter
from src.packet_tracer_mcp.infrastructure.execution.fake_probe_runtime import FakePacketTracerProbeRuntime
from src.packet_tracer_mcp.infrastructure.execution.probe_runtime import PacketTracerBridgeProbeRuntime
from src.packet_tracer_mcp.infrastructure.execution.ios_terminal import IosCommandResult, IosSessionState, OperationalQueryId
from src.packet_tracer_mcp.infrastructure.persistence.capability_snapshot_store import (
    CapabilitySnapshotStore,
    compare_snapshots,
)


def _observation(model: str = "3560-24PS", poe: CapabilityStatus = CapabilityStatus.UNKNOWN):
    return RuntimeDeviceObservation(
        found=True, runtime_id=model, display_name=model,
        ports=[
            RuntimePortDescriptor(name="FastEthernet0/1", poe_status=poe),
            RuntimePortDescriptor(name="GigabitEthernet0/1", poe_status=poe),
        ],
    )


def _service(tmp_path, runtime: FakePacketTracerProbeRuntime):
    adapter = EnterpriseCapabilityAdapter()
    return CapabilityDiscoveryService(
        runtime, CapabilitySnapshotStore(tmp_path / "capabilities"), adapter.identity_for,
    )


def test_probe_session_tracks_created_device_and_cleans_it(tmp_path):
    runtime = FakePacketTracerProbeRuntime({"3560-24PS": _observation()})
    snapshot, cached = _service(tmp_path, runtime).run(ProbeRequest(models=["3560-24PS"]))

    assert not cached
    assert runtime.create_device_calls == runtime.delete_device_calls == 1
    assert snapshot.session.session.cleanup_status is CleanupStatus.CLEAN
    assert len(snapshot.session.cleanup_deleted) == 1
    assert snapshot.session.results[0].capability == "model_exists"


def test_cleanup_failure_is_dirty_and_names_only_probe_device(tmp_path):
    runtime = FakePacketTracerProbeRuntime({"2911": _observation("2911")})
    service = _service(tmp_path, runtime)
    original_delete = runtime.delete_temporary_device
    runtime.delete_temporary_device = lambda name: False

    snapshot, _ = service.run(ProbeRequest(models=["2911"], force=True))

    assert snapshot.session.session.cleanup_status is CleanupStatus.DIRTY_SESSION
    assert snapshot.session.cleanup_failed and snapshot.session.cleanup_failed[0].startswith("__MCP_PROBE_")
    runtime.delete_temporary_device = original_delete


def test_missing_or_timeout_model_remains_unknown_not_unsupported(tmp_path):
    runtime = FakePacketTracerProbeRuntime({"missing": RuntimeDeviceObservation(found=False)})
    snapshot, _ = _service(tmp_path, runtime).run(ProbeRequest(models=["missing"], probe_level=ProbeLevel.DISCOVERY))

    result = snapshot.session.results[0]
    assert result.status is CapabilityStatus.UNKNOWN
    assert result.execution_status is ProbeExecutionStatus.VERIFY_FAILED


def test_probe_timeout_remains_unknown_not_unsupported(tmp_path):
    timeout = CapabilityProbeResult(
        probe_id="layer2-probe", model="2960-24TT", capability="layer2",
        execution_status=ProbeExecutionStatus.TIMEOUT,
        evidence_source=EvidenceSource.CONTROLLED_PROBE,
    )
    runtime = FakePacketTracerProbeRuntime(
        {"2960-24TT": _observation("2960-24TT")},
        {("2960-24TT", "layer2"): timeout},
    )
    snapshot, _ = _service(tmp_path, runtime).run(ProbeRequest(
        models=["2960-24TT"], capabilities=["layer2"], force=True,
    ))

    result = next(item for item in snapshot.session.results if item.capability == "layer2")
    assert result.status is CapabilityStatus.UNKNOWN
    assert result.execution_status is ProbeExecutionStatus.TIMEOUT


def test_logical_prerequisites_skipped_by_runtime_are_not_reported_as_errors(tmp_path):
    runtime = FakePacketTracerProbeRuntime({"2960-24TT": _observation("2960-24TT")})

    snapshot, _ = _service(tmp_path, runtime).run(ProbeRequest(
        models=["2960-24TT"], probe_level=ProbeLevel.LOGICAL, force=True,
    ))

    results = {item.capability: item for item in snapshot.session.results}
    assert results["layer2"].execution_status is ProbeExecutionStatus.SKIPPED
    assert results["supports_vlan"].execution_status is ProbeExecutionStatus.SKIPPED
    assert results["supports_trunk"].execution_status is ProbeExecutionStatus.SKIPPED
    assert snapshot.compact_summary()["errors"] == 0


def test_runtime_only_and_catalog_identity_are_distinguished(tmp_path):
    runtime = FakePacketTracerProbeRuntime({
        "IE-3400": _observation("IE-3400"),
        "2911": _observation("2911"),
    })
    snapshot, _ = _service(tmp_path, runtime).run(ProbeRequest(models=["IE-3400", "2911"], force=True))
    identities = {item.identity.runtime_id: item.identity for item in snapshot.session.devices}

    assert identities["IE-3400"].status.value == "runtime_only"
    assert identities["2911"].status.value == "catalog_matched"


def test_mutating_capability_uses_a_fresh_device_without_recreating_physical_inventory(tmp_path):
    runtime = FakePacketTracerProbeRuntime({"3560-24PS": _observation()})
    snapshot, _ = _service(tmp_path, runtime).run(ProbeRequest(
        models=["3560-24PS"], capabilities=["port_inventory", "supports_poe", "layer3"], force=True,
    ))

    assert runtime.create_device_calls == 2
    assert runtime.delete_device_calls == 2
    assert {result.capability for result in snapshot.session.results} >= {"model_exists", "port_inventory", "supports_poe", "layer3"}


def test_cache_requires_exact_pt_version_and_force_bypasses_it(tmp_path):
    runtime = FakePacketTracerProbeRuntime({"2911": _observation("2911")}, packet_tracer_version="PT 9.0")
    service = _service(tmp_path, runtime)
    service.run(ProbeRequest(models=["2911"]))
    _, cached = service.run(ProbeRequest(models=["2911"]))
    assert cached and runtime.create_device_calls == 1

    runtime._version = "PT 10.0"
    _, cached = service.run(ProbeRequest(models=["2911"]))
    assert not cached and runtime.create_device_calls == 2
    service.run(ProbeRequest(models=["2911"], force=True))
    assert runtime.create_device_calls == 3


def test_snapshot_roundtrip_hash_and_diff_are_stable(tmp_path):
    runtime = FakePacketTracerProbeRuntime({"2911": _observation("2911")})
    service = _service(tmp_path, runtime)
    first, _ = service.run(ProbeRequest(models=["2911"]))
    store = CapabilitySnapshotStore(tmp_path / "capabilities")
    loaded = store.latest_runtime("PT-test")
    assert loaded is not None and loaded.stable_hash() == first.stable_hash()

    changed_port = first.model_copy(deep=True)
    changed_port.session.devices[0].ports.append(RuntimePortDescriptor(name="Serial0/0/0"))
    diff = compare_snapshots(first, changed_port)
    assert diff.ports_changed == ["2911"]


def test_runtime_probe_evidence_improves_hardware_selection_only_for_exact_version(tmp_path):
    session = ProbeSession(session_id="probe-fixed", packet_tracer_version="PT 9.0")
    result = CapabilityProbeResult(
        probe_id="poe-inventory", model="3560-24PS", capability="supports_poe",
        status=CapabilityStatus.SUPPORTED, execution_status=ProbeExecutionStatus.VERIFIED,
        evidence_source=EvidenceSource.CONTROLLED_PROBE, verified=True,
        observed_value=24,
        packet_tracer_version="PT 9.0",
    )
    snapshot = CapabilitySnapshot(
        packet_tracer_version="PT 9.0",
        session=ProbeSessionResult(session=session, results=[result]),
    )
    store = CapabilitySnapshotStore(tmp_path / "capabilities")
    store.save_runtime(snapshot)
    adapter = EnterpriseCapabilityAdapter(providers=[ProbeCapabilityProvider(store)])
    supported = adapter.capabilities_for("3560-24PS", "PT 9.0")
    other_version = adapter.capabilities_for("3560-24PS", "PT 10.0")
    assert supported is not None and other_version is not None
    assert supported.supports_poe is CapabilityStatus.SUPPORTED
    assert other_version.supports_poe is CapabilityStatus.UNKNOWN

    selection = DeviceSelector().select(
        DeviceRequirement(role=DeviceRole.ACCESS_SWITCH, poe_ports=1), [supported],
    )
    assert selection.selected_model == "3560-24PS"


def test_conflicting_evidence_keeps_warning_and_probe_wins_over_static_override():
    evidence = [
        CapabilityEvidence(capability="layer3", status=CapabilityStatus.SUPPORTED, source=EvidenceSource.STATIC_OVERRIDE),
        CapabilityEvidence(capability="layer3", status=CapabilityStatus.UNSUPPORTED, source=EvidenceSource.CONTROLLED_PROBE, verified=True),
    ]
    resolver = CapabilityResolver()
    assert resolver.resolve_evidence("layer3", evidence) is CapabilityStatus.UNSUPPORTED
    assert resolver.conflicts("3560-24PS", evidence)[0].winner is EvidenceSource.CONTROLLED_PROBE


def test_registry_declares_dependencies_without_accepting_raw_user_commands():
    definitions = CapabilityProbeRegistry().definitions_for(["supports_trunk"])

    assert [item.capability for item in definitions] == ["model_exists", "port_inventory", "layer2", "configuration_channel", "supports_vlan", "supports_trunk"]
    assert all(not hasattr(item, "command") for item in definitions)
    assert all(item.requires_fresh_device for item in definitions[-2:])


def test_registry_declares_dhcp_server_as_a_behavioral_layer3_probe():
    definitions = CapabilityProbeRegistry().definitions_for([
        "supports_dhcp_server",
    ])

    assert [item.capability for item in definitions] == [
        "model_exists",
        "port_inventory",
        "configuration_channel",
        "layer3",
        "supports_dhcp_server",
    ]
    assert definitions[-1].requires_fresh_device
    assert all(not hasattr(item, "command") for item in definitions)


def test_compact_summary_counts_large_snapshot_without_expanding_models(tmp_path):
    runtime = FakePacketTracerProbeRuntime({
        f"model-{index}": _observation(f"model-{index}") for index in range(100)
    })
    snapshot, _ = _service(tmp_path, runtime).run(ProbeRequest(models=list(runtime.observations), probe_level=ProbeLevel.DISCOVERY))
    summary = snapshot.compact_summary()

    assert summary["models"] == 100
    assert "devices" not in summary


def test_bridge_probe_runtime_serializes_untrusted_model_and_probe_names():
    sent: list[str] = []

    def send_and_wait(js: str, timeout: float):
        sent.append(js)
        return '{"found": false}'

    runtime = PacketTracerBridgeProbeRuntime(send_and_wait)
    runtime.create_temporary_device('x";throw new Error(1);//', '__MCP_PROBE_"_01')

    assert '\\";throw' in sent[0]
    assert 'var __model=' in sent[0]


def test_bridge_runtime_selects_the_documented_terminal_by_device_category():
    runtime = PacketTracerBridgeProbeRuntime(lambda _js, _timeout: '{"found": false}')

    assert runtime._terminal_kind_for("2911") == "ios_command_line"
    assert runtime._terminal_kind_for("2960-24TT") == "ios_command_line"
    assert runtime._terminal_kind_for("3560-24PS") == "ios_command_line"
    assert runtime._terminal_kind_for("PC-PT") == "pc_command_prompt"


def test_runtime_port_descriptor_marks_svis_as_logical_interfaces():
    vlan = PacketTracerBridgeProbeRuntime._port_descriptor({"name": "Vlan1", "bandwidth_kbps": 100000})
    ethernet = PacketTracerBridgeProbeRuntime._port_descriptor({"name": "GigabitEthernet0/0", "bandwidth_kbps": 1000000})

    assert vlan.logical and not vlan.physical
    assert ethernet.physical and not ethernet.logical


def test_runtime_port_power_observation_keeps_admin_runtime_and_delivery_separate():
    supported = PacketTracerBridgeProbeRuntime._port_descriptor({
        "name": "FastEthernet0/1",
        "power_admin_observed": True,
        "power_admin_enabled": True,
        "power_runtime_observed": True,
        "power_runtime_on": True,
    })
    unsupported = PacketTracerBridgeProbeRuntime._port_descriptor({
        "name": "FastEthernet0/2",
        "power_admin_observed": True,
        "power_admin_enabled": False,
        "power_runtime_observed": True,
        "power_runtime_on": False,
    })
    partial = PacketTracerBridgeProbeRuntime._port_descriptor({
        "name": "FastEthernet0/3",
        "power_admin_observed": True,
        "power_admin_enabled": True,
    })
    malformed = PacketTracerBridgeProbeRuntime._port_descriptor({
        "name": "FastEthernet0/4",
        "power_admin_observed": True,
        "power_admin_enabled": 1,
        "power_runtime_observed": True,
        "power_runtime_on": "true",
    })

    assert supported.poe_status is CapabilityStatus.SUPPORTED
    assert supported.power_admin_enabled is True
    assert supported.power_runtime_on is True
    assert supported.power_delivery_active is None
    assert supported.power_observation_complete is True
    assert unsupported.poe_status is CapabilityStatus.UNSUPPORTED
    assert partial.poe_status is CapabilityStatus.UNKNOWN
    assert malformed.poe_status is CapabilityStatus.UNKNOWN
    assert malformed.power_admin_enabled is None
    assert malformed.power_runtime_on is None


def test_bridge_runtime_reads_only_confirmed_port_power_getters():
    sent: list[str] = []

    def send_and_wait(script: str, _timeout: float):
        sent.append(script)
        return (
            '{"found":true,"runtime_id":"3560-24PS",'
            '"display_name":"SW","ports":[{'
            '"name":"FastEthernet0/1","bandwidth_kbps":100000,'
            '"power_admin_observed":true,"power_admin_enabled":true,'
            '"power_runtime_observed":true,"power_runtime_on":true}],'
            '"modules":[]}'
        )

    runtime = PacketTracerBridgeProbeRuntime(send_and_wait)
    runtime._wait_for_operational_readiness = lambda *_args: None
    observed = runtime.create_temporary_device("3560-24PS", "__MCP_PROBE_POWER_01")

    assert observed.ports[0].poe_status is CapabilityStatus.SUPPORTED
    assert "getPower" in sent[0]
    assert "isPowerOn" in sent[0]
    assert "setPower" not in sent[0]


def test_poe_inventory_requires_complete_nonempty_homogeneous_port_observation(tmp_path):
    supported = _observation(poe=CapabilityStatus.SUPPORTED)
    supported.ports[0].power_admin_enabled = True
    supported.ports[0].power_runtime_on = True
    supported.ports[0].power_observation_complete = True
    supported.ports[0].interface_type = "FastEthernet"
    supported.ports[1].power_admin_enabled = True
    supported.ports[1].power_runtime_on = True
    supported.ports[1].power_observation_complete = True
    unsupported = _observation(poe=CapabilityStatus.UNSUPPORTED)
    unsupported.ports[0].power_admin_enabled = False
    unsupported.ports[0].power_runtime_on = False
    unsupported.ports[0].power_observation_complete = True
    unsupported.ports[0].interface_type = "FastEthernet"
    mixed = _observation()
    mixed.ports = [
        RuntimePortDescriptor(
            name="FastEthernet0/1", interface_type="FastEthernet",
            poe_status=CapabilityStatus.SUPPORTED,
        ),
        RuntimePortDescriptor(
            name="FastEthernet0/2", interface_type="FastEthernet",
            poe_status=CapabilityStatus.UNKNOWN,
        ),
    ]
    empty = RuntimeDeviceObservation(
        found=True, runtime_id="3560-24PS", display_name="3560-24PS", ports=[],
    )

    observations = (supported, unsupported, mixed, empty)
    expected = (
        (CapabilityStatus.SUPPORTED, ProbeExecutionStatus.VERIFIED, 1),
        (CapabilityStatus.UNSUPPORTED, ProbeExecutionStatus.VERIFIED, None),
        (CapabilityStatus.UNKNOWN, ProbeExecutionStatus.SKIPPED, None),
        (CapabilityStatus.UNKNOWN, ProbeExecutionStatus.SKIPPED, None),
    )
    for index, (observation, outcome) in enumerate(zip(observations, expected)):
        runtime = FakePacketTracerProbeRuntime({"3560-24PS": observation})
        snapshot, _ = _service(tmp_path / str(index), runtime).run(ProbeRequest(
            models=["3560-24PS"], capabilities=["supports_poe"], force=True,
        ))
        result = next(
            item for item in snapshot.session.results
            if item.capability == "supports_poe"
        )
        assert (result.status, result.execution_status, result.observed_value) == outcome


def test_bridge_runtime_vlan_probe_requires_configure_readback_and_cleanup():
    sent: list[str] = []

    responses = iter((
        '{"found":true,"configuration_channel":true}',
        '{"found":true,"configuration_channel":true}',
        '{"found":true,"configuration_channel":true}',
    ))

    def send_and_wait(js: str, timeout: float):
        sent.append(js)
        return next(responses)

    definition = CapabilityProbeRegistry().definitions_for(["supports_vlan"])[-1]
    configured: list[str] = []
    result = PacketTracerBridgeProbeRuntime(send_and_wait, send=lambda js: configured.append(js) is None).probe_capability("__MCP_PROBE_01", "supports_vlan", definition)

    assert result.status is CapabilityStatus.SUPPORTED
    assert result.configured and result.verified
    assert "configureIosDevice" in configured[0]
    assert "getVlanAt" in sent[0]
    assert "no vlan" in configured[1]


def test_bridge_runtime_trunk_probe_requires_admin_mode_readback_and_cleanup():
    configured: list[str] = []
    runtime = PacketTracerBridgeProbeRuntime(
        lambda _js, _timeout: '{"found":true}',
        send=lambda js: configured.append(js) is None,
    )
    runtime._physical_access_ports = lambda _device, _count: ["FastEthernet0/1"]
    observed_modes = iter((True, True))
    runtime._wait_for_admin_mode = (
        lambda _device, _port, _expected: next(observed_modes)
    )
    definition = CapabilityProbeRegistry().definitions_for(["supports_trunk"])[-1]

    result = runtime.probe_capability(
        "__MCP_PROBE_01", "supports_trunk", definition,
    )

    assert result.status is CapabilityStatus.SUPPORTED
    assert result.configured and result.verified
    assert "switchport trunk encapsulation dot1q" in configured[0]
    assert "switchport mode trunk" in configured[0]
    assert "switchport mode access" in configured[1]


def test_bridge_runtime_dhcp_server_probe_requires_a_fresh_client_lease():
    configured: list[str] = []
    deleted: list[str] = []
    runtime = PacketTracerBridgeProbeRuntime(
        lambda _js, _timeout: '{"found":true}',
        send=lambda js: configured.append(js) is None,
    )
    runtime._layer3_target = lambda _device: ("GigabitEthernet0", False)
    runtime._create_probe_endpoint = lambda _name: True
    runtime._link_probe_endpoint = lambda _endpoint, _router, _port: True
    runtime._wait_for_dhcp_lease = lambda _endpoint: {
        "ipv4": "198.18.37.2",
        "netmask": "255.255.255.248",
    }
    runtime.delete_temporary_device = (
        lambda name: deleted.append(name) is None
    )
    definition = CapabilityProbeRegistry().definitions_for([
        "supports_dhcp_server",
    ])[-1]

    result = runtime.probe_capability(
        "__MCP_PROBE_01", "supports_dhcp_server", definition,
    )

    assert result.status is CapabilityStatus.SUPPORTED
    assert result.configured and result.verified
    assert "ip dhcp pool MCP_CAPABILITY_PROBE" in configured[0]
    assert "configurePcIp" in configured[1]
    assert "true" in configured[1]
    assert deleted == ["__MCP_PROBE_01_DHCP"]


def test_bridge_runtime_dhcp_server_probe_preserves_unknown_without_a_lease():
    runtime = PacketTracerBridgeProbeRuntime(
        lambda _js, _timeout: '{"found":true}',
        send=lambda _js: True,
    )
    runtime._layer3_target = lambda _device: ("GigabitEthernet0", False)
    runtime._create_probe_endpoint = lambda _name: True
    runtime._link_probe_endpoint = lambda _endpoint, _router, _port: True
    runtime._wait_for_dhcp_lease = lambda _endpoint: None
    runtime.delete_temporary_device = lambda _name: True
    definition = CapabilityProbeRegistry().definitions_for([
        "supports_dhcp_server",
    ])[-1]

    result = runtime.probe_capability(
        "__MCP_PROBE_01", "supports_dhcp_server", definition,
    )

    assert result.status is CapabilityStatus.UNKNOWN
    assert result.execution_status is ProbeExecutionStatus.VERIFY_FAILED
    assert not result.verified


def test_dhcp_server_observation_rejects_missing_malformed_or_foreign_leases():
    invalid = (
        {},
        {"ipv4": "", "netmask": "255.255.255.248"},
        {"ipv4": "not-an-address", "netmask": "255.255.255.248"},
        {"ipv4": "198.18.37.2", "netmask": "255.255.255.0"},
        {"ipv4": "198.18.38.2", "netmask": "255.255.255.248"},
        {"ipv4": "198.18.37.1", "netmask": "255.255.255.248"},
    )

    assert all(
        not PacketTracerBridgeProbeRuntime._dhcp_lease_matches(item)
        for item in invalid
    )
    assert PacketTracerBridgeProbeRuntime._dhcp_lease_matches({
        "ipv4": "198.18.37.2",
        "netmask": "255.255.255.248",
    })


def test_routed_probe_prefers_a_gigabit_port_over_lower_speed_aliases():
    runtime = PacketTracerBridgeProbeRuntime(
        lambda _js, _timeout: (
            '{"interfaces":["Ethernet1","FastEthernet0",'
            '"GigabitEthernet0"]}'
        ),
    )

    assert runtime._first_ethernet_port("R1") == "GigabitEthernet0"


def test_bridge_runtime_layer3_probe_requires_configure_readback_and_cleanup():
    sent: list[str] = []

    responses = iter((
        # La estrategia L3 se resuelve en dos pasos: primero el modelo observado
        # y su estrategia declarada, y sólo entonces la interfaz concreta.
        '{"model":"2911"}',
        '{"interfaces":["GigabitEthernet0/0"]}',
        '{"found":true,"booting":false,"terminal":true,"prompt":"Router>","output":""}',
        '{"ok":true,"before":""}',
        '{"found":true,"configuration_channel":true,"output":"Interface IP-Address"}',
        '{"found":true,"configuration_channel":true,"output":"Interface IP-Address"}',
        '{"found":true,"booting":false,"terminal":true,"prompt":"Router>","output":""}',
        '{"ok":true,"before":""}',
        '{"found":true,"configuration_channel":true,"output":"GigabitEthernet0/0 198.18.36.1 YES manual up up"}',
        '{"found":true,"configuration_channel":true,"output":"GigabitEthernet0/0 198.18.36.1 YES manual up up"}',
        '{"found":true,"booting":false,"terminal":true,"prompt":"Router>","output":""}',
        '{"ok":true,"before":""}',
        '{"found":true,"configuration_channel":true,"output":"GigabitEthernet0/0 unassigned YES unset administratively down down"}',
        '{"found":true,"configuration_channel":true,"output":"GigabitEthernet0/0 unassigned YES unset administratively down down"}',
    ))

    def send_and_wait(js: str, timeout: float):
        sent.append(js)
        return next(responses)

    definition = CapabilityProbeRegistry().definitions_for(["layer3"])[-1]
    configured: list[str] = []
    result = PacketTracerBridgeProbeRuntime(send_and_wait, send=lambda js: configured.append(js) is None).probe_capability("__MCP_PROBE_01", "layer3", definition)

    assert result.status is CapabilityStatus.SUPPORTED
    assert result.configured and result.verified
    assert "ip address 198.18.36.1 255.255.255.252" in configured[0]
    assert any("getCommandLine" in item for item in sent)
    assert "no ip address" in configured[1]


def test_ios_address_wait_retries_until_fresh_show_observes_the_new_address():
    class DelayedIos:
        def __init__(self):
            self.outputs = iter((
                "GigabitEthernet0/0 unassigned YES unset administratively down down",
                "GigabitEthernet0/0 198.18.36.1 YES manual up up",
            ))

        def execute(self, _device, _query):
            return IosCommandResult(
                device_name="R1", query_id=OperationalQueryId.SHOW_IP_INTERFACE_BRIEF,
                executed=True, output=next(self.outputs), session_state=IosSessionState.EXEC_PROMPT_READY,
                fresh_output_observed=True, window_strategy="prefix_delta",
            )

    runtime = PacketTracerBridgeProbeRuntime(lambda _js, _timeout: '{"found": true}')
    runtime._ios = DelayedIos()

    observed = runtime._wait_for_ios_address("R1", "GigabitEthernet0/0", "198.18.36.1", present=True)

    assert observed is not None
    assert "198.18.36.1" in observed.output


def test_scenario_readiness_does_not_require_endpoint_poe_or_routing(tmp_path):
    runtime = FakePacketTracerProbeRuntime(
        {"PC-PT": _observation("PC-PT"), "2911": _observation("2911")},
        {
            ("2911", "layer3"): CapabilityProbeResult(
                probe_id="layer3-probe", model="2911", capability="layer3",
                status=CapabilityStatus.SUPPORTED, execution_status=ProbeExecutionStatus.VERIFIED,
                evidence_source=EvidenceSource.CONTROLLED_PROBE, verified=True,
            ),
        },
    )
    service = _service(tmp_path, runtime)
    snapshot, _ = service.run(ProbeRequest(
        models=["PC-PT", "2911"], capabilities=["layer3"], force=True,
    ))

    report = service.readiness_report(snapshot)

    assert report.non_poe_e4.value == "ready"
    assert report.full_poe_e4.value == "ready"
    assert report.blockers_by_role == {}
    assert report.required_capabilities_by_role["endpoint"] == ["model_exists", "port_inventory"]
