"""The private SP-2 remote discriminator stays bound to its composed fixture."""

from __future__ import annotations

import json
from dataclasses import dataclass
from ipaddress import ip_interface

from campus_product_simulation import CampusPlans
from cold_http_acceptance_harness import FakeClock
from routed_product_simulation import RoutedCampusTerminal

from packet_tracer_mcp.adapters.cli import service_qualification
from packet_tracer_mcp.adapters.cli.service_qualification import (
    _request,
    fixture_plans,
    sp2_remote_relay_contract,
)
from packet_tracer_mcp.application.use_cases.qualify_server_services import (
    qualify_server_services,
)
from packet_tracer_mcp.domain.enterprise.models.service_qualification import (
    SP2_STAGES,
    STAGE_DEFINITIONS,
    MeasurementConclusion,
    QualificationStage,
    _sp2_remote_relay,
    stage_definition,
)
from packet_tracer_mcp.domain.enterprise.services import sp2_pool_diagnostic
from packet_tracer_mcp.domain.enterprise.services.dhcp_lease_evidence import (
    AddressRange,
    ClientReading,
    LeaseRow,
)
from tests.service_qualification_engine import (
    NodeEngine,
    NodeEngineTransport,
    authorization_args,
    request_args,
    require_node,
    simulated_boundaries,
)
from tests.test_sp2_native_pool_diagnostic import _scan

BUILD = "9.0.1.0858"
RUN_ID = "sp2-e3-stage-offline"


def test_remote_stage_binds_the_composed_fixture_and_budget():
    """The stage names the same devices, ports and bounded resources."""
    definition = _sp2_remote_relay()
    assert stage_definition("SP2-REMOTE-RELAY") == definition
    assert QualificationStage.SP2_REMOTE_RELAY in SP2_STAGES
    assert definition is not None and definition.executable
    assert definition.profile_id == "SP2-REMOTE-RELAY"
    assert definition.profile_version == "3"
    assert definition.allowed_channels == ("file",)
    assert definition.selected_clients == ("BR1-DEFAULT-PC-01",)
    assert definition.planned_minimum_operations <= definition.budget.max_operations

    contract = sp2_remote_relay_contract(BUILD, RUN_ID)
    assert {(item.name, item.model) for item in definition.fixtures} == {
        (item.name, item.model) for item in contract.topology.devices
    }
    assert {
        (item.device_a, item.port_a, item.device_b, item.port_b, item.cable)
        for item in definition.links
    } == {
        (item.device_a, item.port_a, item.device_b, item.port_b, item.cable)
        for item in contract.topology.links
    }
    devices, links = fixture_plans(definition)
    assert {item.name for item in devices} == set(definition.fixture_names)
    assert len(links) == 5


def test_remote_sample_supports_named_association_with_unknown_default_end():
    """Exact named rows prove association without an exclusive claim."""
    client = ClientReading(
        "BR1-DEFAULT-PC-01",
        True,
        True,
        "0001.0001.0001",
        "10.72.32.2",
        "255.255.255.248",
    )
    binding = {
        "device": client.client,
        "found": True,
        "port_found": True,
        "error": "",
        "ipv4": client.ipv4,
        "netmask": client.netmask,
        "gateway_reads": [{"api": True, "error": "", "value": "10.72.32.1"}],
        "dns_api": True,
        "dns_error": "",
        "dns_server": "10.72.0.2",
    }
    named = _scan(
        "BR1_DATA",
        LeaseRow(0, client.ipv4, client.mac, 100.0, "FastEthernet0"),
    )
    default = _scan("serverPool")
    assess = getattr(sp2_pool_diagnostic, "assess_sp2_remote_samples", None)
    assert callable(assess)
    result = assess(
        (client, client),
        (binding, binding),
        (named, named),
        (default, default),
        named_range=AddressRange("10.72.32.2", "10.72.32.3"),
        expected_mask="255.255.255.248",
        expected_gateway="10.72.32.1",
        expected_dns="10.72.0.2",
        expected_capacity=2,
    )
    assert result.conclusion is MeasurementConclusion.SUPPORTED_IN_SAMPLE
    assert result.facts["named_rows"] == ["exact_ip_mac_row", "exact_ip_mac_row"]
    assert result.facts["exclusive_serving"] is False
    assert "default_table_end_not_calibrated" in result.limitations
    assert (
        "pre_mode_absence_not_proven_no_causal_acquisition_claim" in result.limitations
    )


class _RelayCampus(RoutedCampusTerminal):
    """Answer the existing IOS helper query from applied typed IOS payloads."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helpers = {}
        self.wrong_helper = ""

    def _apply_ios(self, router, payload):
        super()._apply_ios(router, payload)
        interface = ""
        for raw in payload.splitlines():
            line = raw.strip()
            if line.startswith("interface "):
                interface = line.split(" ", 1)[1]
            elif line.startswith("ip helper-address ") and interface:
                self.helpers[(router.name, interface)] = line.split()[-1]
            elif line in {"exit", "end"}:
                interface = ""

    def _output(self, device):
        command = self.commands.get(device, "")
        if (
            not command.startswith("show ip interface ")
            or command == "show ip interface brief"
        ):
            return super()._output(device)
        interface = command.removeprefix("show ip interface ")
        router = self.routers[device]
        address, mask = router.interfaces.get(interface, ("", ""))
        helper = self.wrong_helper or self.helpers.get((device, interface), "")
        prefix = ip_interface(f"{address}/{mask}").network.prefixlen if address else 0
        table = (
            f"{interface} is up, line protocol is up\n"
            f"  Internet address is {address}/{prefix}\n"
            f"  Helper address is {helper or 'not set'}"
        )
        prompt = f"{device}#"
        self.events.append(f"ios_read:{device}:{command}")
        return json.dumps(
            {
                "found": True,
                "configuration_channel": True,
                "output": "\n".join((f"{prompt}{command}", table, prompt)),
                "owner_name": device,
                "owner_evidence": "terminal_object_identity",
                "owner_candidates": 1,
                "owner_candidate_evidence": "terminal_object_identity",
                "owner_candidate_names": [device],
                "device_count": len(self.inventory),
            }
        )


class _SwitchingTransport:
    """Keep fixture/probes in Node and route product IOS through the campus."""

    def __init__(self, engine, campus, *, clock, before_script=None, lose_when=None):
        self.engine = NodeEngineTransport(engine)
        self.campus = campus
        self.target = self.engine
        self.calls = []
        self.clock = clock
        self.before_script = before_script
        self.lose_when = lose_when
        self.lost = False

    def _before(self, script):
        if self.before_script is not None:
            self.before_script(script, self.clock)
        if (
            self.target is self.engine
            and not self.lost
            and self.lose_when is not None
            and self.lose_when(script)
        ):
            self.engine.lose.add(len(self.engine.calls) + 1)
            self.lost = True

    def send(self, script):
        self.calls.append(("send", script))
        self._before(script)
        return self.target.send(script)

    def send_and_wait(self, script, timeout):
        self.calls.append(("send_and_wait", script))
        self._before(script)
        return self.target.send_and_wait(script, timeout)

    def dispatch_and_wait(self, script, timeout):
        self.calls.append(("dispatch_and_wait", script))
        self._before(script)
        return self.target.dispatch_and_wait(script, timeout)


class _HybridView:
    """A single ledgered transport selecting the owner of each product call."""

    def __init__(self, bound, switching):
        self.bound = bound
        self.switching = switching
        self.observation_context = bound.observation_context
        self.clock = bound.clock
        self.capped_sleep = bound.capped_sleep
        self.remaining_seconds = bound.remaining_seconds

    def _send(self, method, script, *args):
        endpoint = (
            'getDevice("HQ-DEFAULT-DNS-01")' in script
            or 'getDevice("BR1-DEFAULT-PC-01")' in script
            or 'configurePcIp("HQ-DEFAULT-DNS-01"' in script
            or 'configurePcIp("BR1-DEFAULT-PC-01"' in script
        )
        self.switching.target = (
            self.switching.engine if endpoint else self.switching.campus
        )
        try:
            return getattr(self.bound, method)(script, *args)
        finally:
            self.switching.target = self.switching.engine

    def send(self, script):
        return self._send("send", script)

    def send_and_wait(self, script, timeout):
        return self._send("send_and_wait", script, timeout)

    def dispatch_and_wait(self, script, timeout):
        return self._send("dispatch_and_wait", script, timeout)


@dataclass
class _Run:
    result: object
    snapshot: dict
    switching: object
    campus: object

    @property
    def record(self):
        return self.result.record

    def measurement(self, name):
        return next(
            item for item in self.record.measurements if item.experiment_id == name
        )


def _run_remote(
    tmp_path,
    monkeypatch,
    *,
    engine_config=None,
    campus_config=None,
    boundary_overrides=None,
    operation_ceiling=None,
    before_script=None,
    lose_when=None,
):
    require_node()
    definition = stage_definition("SP2-REMOTE-RELAY")
    assert definition == _sp2_remote_relay()
    if operation_ceiling is not None:
        from dataclasses import replace

        from packet_tracer_mcp.domain.enterprise.models.service_qualification import (
            STAGE_CEILINGS,
            StageBudget,
        )

        planned = (
            operation_ceiling
            - definition.setup_operations
            - definition.reserve_operations
            - 80
            - 10
        )
        definition = replace(
            definition,
            budget=StageBudget(operation_ceiling, 3600, reserve_seconds=420),
            experiments=(
                replace(definition.experiments[0], planned_operations=planned),
                definition.experiments[1],
            ),
        )
        monkeypatch.setitem(
            STAGE_CEILINGS,
            QualificationStage.SP2_REMOTE_RELAY,
            (operation_ceiling, 3600),
        )
        monkeypatch.setitem(
            STAGE_DEFINITIONS, QualificationStage.SP2_REMOTE_RELAY, definition
        )
    contract = sp2_remote_relay_contract(BUILD, RUN_ID)
    plans = CampusPlans(
        payload=json.loads(contract.intent_json),
        intent_json=contract.intent_json,
        manifest=contract.manifest,
        inventory=list(contract.inventory),
        configuration_plan=contract.configuration_plan,
        service_plan=contract.service_plan,
        deployed_names={item.id: item.name for item in contract.topology.devices},
        device_count=6,
        link_count=5,
    )
    clock = FakeClock()
    campus = _RelayCampus(
        tmp_path / "campus", plans, clock, dns_server="10.72.0.2", records={}
    )
    if campus_config:
        campus_config(campus)
    options = {
        "terminals": True,
        "dhcp_default_pool": "native",
        "default_pool_realigns_on_address": True,
        "dhcp_mode_acquires": True,
        "dhcp_pool_selection": "intended",
        "dhcp_intended_pool_name": "BR1_DATA",
        # v3: the client is in DHCP mode before the process is enabled.
        "dhcp_retry_on_server_enable": True,
        **(engine_config or {}),
    }
    engine = NodeEngine(tmp_path, **options)
    try:
        switching = _SwitchingTransport(
            engine,
            campus,
            clock=clock,
            before_script=before_script,
            lose_when=lose_when,
        )

        def native_runtimes(bound, inventory):
            view = _HybridView(bound, switching)
            return service_qualification._native_product_runtimes(view, inventory)

        boundaries = simulated_boundaries(
            tmp_path,
            switching,
            clock=clock,
            sleep=clock.sleep,
            new_run_id=lambda _moment: RUN_ID,
            native_product_runtimes=native_runtimes,
            **(boundary_overrides or {}),
        )
        request = _request(
            request_args("SP2-REMOTE-RELAY") + authorization_args("SP2-REMOTE-RELAY")
        )
        try:
            result = qualify_server_services(
                request,
                boundaries,
                experimental_capabilities=frozenset(
                    definition.experimental_capabilities
                ),
            )
        except service_qualification.QualificationCancelled:
            from types import SimpleNamespace

            from packet_tracer_mcp.domain.enterprise.models.service_qualification import (
                QualificationRecord,
            )

            path = (
                tmp_path
                / "records"
                / "sp2-remote-relay"
                / f"sp2-remote-relay-{RUN_ID}.json"
            )
            result = SimpleNamespace(
                record=QualificationRecord.model_validate_json(path.read_text())
            )
        return _Run(result, engine.snapshot(), switching, campus)
    finally:
        engine.close()


def test_remote_coordinator_applies_mode_before_pool_and_retains_samples(
    tmp_path, monkeypatch
):
    """The real coordinator records the selected client and competing pool."""
    run = _run_remote(tmp_path, monkeypatch)
    measurement = run.measurement("M-SP2-REMOTE-POOL")
    assert measurement.conclusion is MeasurementConclusion.SUPPORTED_IN_SAMPLE, (
        run.record.primary_failure,
        measurement.causes,
    )
    assert [item["effect"] for item in run.snapshot["dhcp_timeline"]] == [
        "clientMode",
        "addPool",
        "setEnable",
    ]
    assert len(measurement.facts["samples"]) == 2
    assert run.record.restoration_proven is True
    assert run.record.budget.used_operations <= 3200


def test_wrong_helper_readback_stops_before_pool_or_client_mode(tmp_path, monkeypatch):
    """A changed helper answer cannot authorize E6 or a PC mode effect."""
    run = _run_remote(
        tmp_path,
        monkeypatch,
        campus_config=lambda campus: setattr(campus, "wrong_helper", "10.72.0.9"),
    )
    assert run.record.primary_failure
    assert run.snapshot["dhcp_timeline"] == []
    assert (
        run.measurement("M-SP2-REMOTE-POOL").conclusion
        is MeasurementConclusion.INCONCLUSIVE
    )


def test_missing_return_route_stops_before_pool_or_client_mode(tmp_path, monkeypatch):
    """The observed return path must cover the whole remote DHCP prefix."""

    def withhold(campus):
        campus.faults_after_service_apply = False
        campus.withheld_routes.add(("HQ-EDGE-RTR-01", "10.72.32.0"))

    run = _run_remote(tmp_path, monkeypatch, campus_config=withhold)
    assert run.record.primary_failure.startswith("contradiction:q3_e5_verification:")
    assert run.snapshot["dhcp_timeline"] == []
    assert (
        run.measurement("M-SP2-REMOTE-POOL").facts["e5_preclient"]["status"]
        != "verified"
    )


def test_default_pool_serving_is_a_negative_remote_finding(tmp_path, monkeypatch):
    """A physical serverPool row remains visible beside the named policy."""
    run = _run_remote(
        tmp_path, monkeypatch, engine_config={"dhcp_pool_selection": "default"}
    )
    finding = run.measurement("M-SP2-REMOTE-POOL")
    assert finding.conclusion is MeasurementConclusion.NEGATIVE_OBSERVED, finding.causes
    assert any("served_by_native_default" in cause for cause in finding.causes)
    assert len(finding.facts["samples"]) == 2
    assert run.snapshot["dhcp_runs"] == []


def test_stale_plan_hash_cannot_bind_a_changed_helper():
    """A changed typed action is refused even when its stored hash is stale."""
    from dataclasses import replace
    from types import SimpleNamespace

    from packet_tracer_mcp.application.server_service_qualification.workflows.sp2_remote_relay import (
        _sp2_remote_contract_mismatch,
    )

    contract = sp2_remote_relay_contract(BUILD, RUN_ID)
    actions = [
        action.model_copy(update={"server_address": "10.72.0.9"}, deep=True)
        if action.action_type.value == "configure_dhcp_relay"
        else action
        for action in contract.configuration_plan.actions
    ]
    plan = contract.configuration_plan.model_copy(
        update={"actions": actions}, deep=True
    )
    forged = replace(contract, configuration_plan=plan)
    execution = SimpleNamespace(
        definition=_sp2_remote_relay(),
        record=SimpleNamespace(run_id=RUN_ID),
    )
    assert (
        _sp2_remote_contract_mismatch(execution, forged)
        == "sp2_remote_plan_hash_changed"
    )


def test_terminal_needs_a_bound_subject_session():
    """An unproven fixture cannot become a successful terminal observation."""
    from packet_tracer_mcp.domain.enterprise.models.service_qualification import (
        DiagnosticPrecondition,
    )

    terminal = _sp2_remote_relay().experiment("M-SP2-REMOTE-FINAL")
    assert DiagnosticPrecondition.SUBJECT_SESSION in terminal.operational_prerequisites


def test_malformed_named_row_after_exact_row_cannot_support_remote_binding():
    """A later physical row with the same IP and unreadable MAC may conflict."""
    from packet_tracer_mcp.domain.enterprise.services.dhcp_lease_evidence import (
        classify_lease_scan,
    )

    client = ClientReading(
        "BR1-DEFAULT-PC-01",
        True,
        True,
        "0001.0001.0001",
        "10.72.32.2",
        "255.255.255.248",
    )
    binding = {
        "device": client.client,
        "found": True,
        "port_found": True,
        "error": "",
        "ipv4": client.ipv4,
        "netmask": client.netmask,
        "gateway_reads": [{"api": True, "error": "", "value": "10.72.32.1"}],
        "dns_api": True,
        "dns_error": "",
        "dns_server": "10.72.0.2",
    }
    named = classify_lease_scan(
        {
            "requested": "BR1_DATA",
            "found": True,
            "name": "BR1_DATA",
            "max": 2,
            "window": 3,
            "error": "",
            "entries": [
                {
                    "index": 0,
                    "return_kind": "object",
                    "error": "",
                    "row": {
                        "ipAddress": client.ipv4,
                        "macAddress": client.mac,
                        "leaseTime": 100.0,
                        "port": "FastEthernet0",
                    },
                },
                {
                    "index": 1,
                    "return_kind": "object",
                    "error": "",
                    "row": {
                        "ipAddress": client.ipv4,
                        "macAddress": "invalid",
                        "leaseTime": 100.0,
                        "port": "FastEthernet0",
                    },
                },
                {"index": 2, "return_kind": "null", "error": "", "row": None},
            ],
        },
        pool_name="BR1_DATA",
    )
    assert named.observed and named.termination == "malformed"
    default = _scan("serverPool")
    result = sp2_pool_diagnostic.assess_sp2_remote_samples(
        (client, client),
        (binding, binding),
        (named, named),
        (default, default),
        named_range=AddressRange("10.72.32.2", "10.72.32.3"),
        expected_mask="255.255.255.248",
        expected_gateway="10.72.32.1",
        expected_dns="10.72.0.2",
        expected_capacity=2,
    )
    assert result.conclusion is MeasurementConclusion.INCONCLUSIVE
    assert "sample_1:named_scan_incomplete" in result.causes


def test_named_pool_same_mac_on_another_address_is_a_shared_conflict():
    """A second normalized MAC row cannot be hidden by one exact IP row."""
    client = ClientReading(
        "BR1-DEFAULT-PC-01",
        True,
        True,
        "0001.0001.0001",
        "10.72.32.2",
        "255.255.255.248",
    )
    binding = {
        "device": client.client,
        "found": True,
        "port_found": True,
        "error": "",
        "ipv4": client.ipv4,
        "netmask": client.netmask,
        "gateway_reads": [{"api": True, "error": "", "value": "10.72.32.1"}],
        "dns_api": True,
        "dns_error": "",
        "dns_server": "10.72.0.2",
    }
    named = _scan(
        "BR1_DATA",
        LeaseRow(0, "10.72.32.2", "0001.0001.0001", 100.0, "FastEthernet0"),
        LeaseRow(1, "10.72.32.3", "00:01:00:01:00:01", 100.0, "FastEthernet0"),
    )
    default = _scan("serverPool")
    result = sp2_pool_diagnostic.assess_sp2_remote_samples(
        (client, client),
        (binding, binding),
        (named, named),
        (default, default),
        named_range=AddressRange("10.72.32.2", "10.72.32.3"),
        expected_mask="255.255.255.248",
        expected_gateway="10.72.32.1",
        expected_dns="10.72.0.2",
        expected_capacity=2,
    )
    assert result.conclusion is MeasurementConclusion.CONTRADICTED
    assert "sample_1:named_mac_multiple_addresses" in result.causes


def test_remote_contract_binds_build_and_capability_snapshots():
    """A substituted build or candidate input refuses before fixture effects."""
    from dataclasses import replace
    from types import SimpleNamespace

    from packet_tracer_mcp.application.server_service_qualification.workflows.sp2_remote_relay import (
        _sp2_remote_contract_mismatch,
    )

    contract = sp2_remote_relay_contract(BUILD, RUN_ID)
    execution = SimpleNamespace(
        definition=_sp2_remote_relay(),
        record=SimpleNamespace(run_id=RUN_ID),
    )
    assert _sp2_remote_contract_mismatch(execution, contract) == ""
    altered = (
        replace(
            contract,
            manifest=contract.manifest.model_copy(
                update={"backend_version": "9.9.9"}, deep=True
            ),
        ),
        replace(contract, device_capabilities={}),
        replace(contract, service_capabilities={}),
        replace(contract, device_capability_catalog=None),
    )
    assert all(_sp2_remote_contract_mismatch(execution, item) for item in altered)


def test_terminal_router_rows_require_fresh_exact_unique_identity():
    """Stale or foreign terminal text cannot support a final observation."""
    from packet_tracer_mcp.domain.enterprise.services import (
        qualification_terminal_evidence,
    )

    check = getattr(
        qualification_terminal_evidence, "terminal_router_rows_complete", None
    )
    assert callable(check)
    routers = ("BR1-EDGE-RTR-01", "HQ-EDGE-RTR-01")
    rows = [
        {
            "device": name,
            "query": query,
            "executed": True,
            "fresh_output_observed": True,
            "output_complete": True,
            "output": "ok",
            "output_characters": 2,
            "truncated_by_pager": False,
            "observed_device_name": name,
            "device_identity_provenance": "confirmed_unique",
            "failure_reason": "",
        }
        for name in routers
        for query in ("show_ip_interface_brief", "show_ip_route")
    ]
    assert check(rows, routers)
    assert not check([{**rows[0], "fresh_output_observed": False}, *rows[1:]], routers)
    assert not check(
        [{**rows[0], "observed_device_name": "foreign"}, *rows[1:]], routers
    )
    assert not check([{**rows[0], "truncated_by_pager": True}, *rows[1:]], routers)
    assert not check([{**rows[0], "output_characters": 3}, *rows[1:]], routers)
    assert not check([rows[0], rows[0], *rows[2:]], routers)


def test_product_scope_preserves_terminal_and_owned_cleanup_allowances():
    """A product cap cannot borrow read-only terminal or protected cleanup work."""
    from packet_tracer_mcp.application.use_cases.qualify_server_services import (
        OperationLedger,
    )

    clock = FakeClock()
    ledger = OperationLedger(max_operations=10, max_seconds=1000, clock=clock)
    ledger.reserve(2, 100)
    with ledger.ordinary_limit(operations=3, leave_seconds=50):
        assert ledger.allowance()[0] == 3
        for _ in range(3):
            ledger.admit("read", 1.0)
        assert not ledger.can_afford(1)
        clock.sleep(851)
        assert ledger.allowance()[1] <= 0
    assert ledger.can_afford(5)
    assert ledger.allowance()[0] == 5


def test_product_operation_exhaustion_keeps_cleanup_reserved(tmp_path, monkeypatch):
    """A controlled smaller grant stops ordinary work and records cleanup."""
    run = _run_remote(tmp_path, monkeypatch, operation_ceiling=250)
    assert run.record.primary_failure
    assert run.record.budget.used_operations <= 250
    refused = [
        index
        for index, row in enumerate(run.record.operations)
        if row.refused in {"operation_budget_exhausted", "time_budget_exhausted"}
    ]
    assert refused
    assert all(
        row.refused
        or row.phase in {"terminal_observation", "finalization", "protected_release"}
        for row in run.record.operations[refused[0] + 1 :]
    )
    assert run.record.restoration_proven


def test_time_exhaustion_after_e5_preserves_owned_cleanup(tmp_path, monkeypatch):
    """The phase clock can stop e3 after E5 without admitting E6."""
    advanced = False

    def expire_at_server_baseline(script, clock):
        nonlocal advanced
        if not advanced and "pool_count:" in script and "HQ-DEFAULT-DNS-01" in script:
            clock.now = 4181.0
            advanced = True

    run = _run_remote(tmp_path, monkeypatch, before_script=expire_at_server_baseline)
    assert advanced
    assert run.record.primary_failure
    assert run.snapshot["dhcp_timeline"] == []
    assert run.record.budget.elapsed_seconds <= 3600
    assert run.record.restoration_proven


def test_lost_pool_response_quarantines_enable_and_client_mode(tmp_path, monkeypatch):
    """A possibly applied named-pool write has no automatic replay."""
    run = _run_remote(
        tmp_path, monkeypatch, lose_when=lambda script: "addPool" in script
    )
    assert run.switching.lost
    assert run.record.primary_failure.startswith("outcome_unknown:")
    assert [item["effect"] for item in run.snapshot["dhcp_timeline"]] == [
        "clientMode",
        "addPool",
    ]
    assert run.record.restoration_proven


def test_record_write_failure_blocks_enable_after_pool(tmp_path, monkeypatch):
    """An unwritten transition cannot license another service mutation."""
    from tests.service_qualification_engine import RecordingStore

    store = RecordingStore(
        tmp_path / "records", fail_from="experiment:SP2_REMOTE:e6_enable"
    )
    run = _run_remote(tmp_path, monkeypatch, boundary_overrides={"record_store": store})
    assert "persistence:" in run.record.primary_failure
    assert [item["effect"] for item in run.snapshot["dhcp_timeline"]] == [
        "clientMode",
        "addPool",
    ]
    assert "experiment:SP2_REMOTE:e6_enable" in store.writes


def test_unobserved_pre_mode_pool_scan_blocks_client_activation(tmp_path, monkeypatch):
    """An unreadable shared scan cannot be treated as an empty pool.

    In v3 the pre-mode scan is the first scan and precedes every effect.
    """
    scans = 0

    def lose_first_scan(script):
        nonlocal scans
        if "var __req=" not in script or "BR1_DATA" not in script:
            return False
        scans += 1
        return scans == 1

    run = _run_remote(tmp_path, monkeypatch, lose_when=lose_first_scan)
    assert run.switching.lost and scans == 1
    assert run.record.primary_failure == "sp2_remote_pre_mode_pool_unobserved"
    assert run.snapshot["dhcp_timeline"] == []


def test_unbound_fixture_cannot_trigger_terminal_router_reads(tmp_path, monkeypatch):
    """A failed owned setup never licenses named terminal observations."""
    run = _run_remote(tmp_path, monkeypatch, engine_config={"create_throws": True})
    final = run.measurement("M-SP2-REMOTE-FINAL")
    assert final.status.value == "not_run"
    assert "subject_session_bound" in final.reason
    assert not any("show ip route" in script for _kind, script in run.switching.calls)


def test_duplicate_physical_pool_answers_are_retained_and_unobserved():
    """One response cannot silently choose the first of two pool identities."""
    from packet_tracer_mcp.domain.enterprise.services.dhcp_lease_evidence import (
        scans_by_pool,
    )

    entry = {
        "requested": "BR1_DATA",
        "found": True,
        "name": "BR1_DATA",
        "max": 2,
        "window": 1,
        "error": "",
        "entries": [{"index": 0, "return_kind": "null", "error": "", "row": None}],
    }
    scans = scans_by_pool({"pools": [entry, {**entry, "name": "wrong"}]}, ("BR1_DATA",))
    assert not scans["BR1_DATA"].observed
    assert scans["BR1_DATA"].cause == "scan_pool_duplicate"
    assert len(scans["BR1_DATA"].entries) == 2


def test_receiver_replacement_after_pool_blocks_enable_and_owned_cleanup(
    tmp_path, monkeypatch
):
    """A new process on the same mailbox cannot inherit e3's authority."""
    from dataclasses import replace

    from packet_tracer_mcp.domain.enterprise.models.service_qualification import (
        DiagnosticLifecycleObservation,
    )
    from tests.service_qualification_engine import (
        SIM_BUILD,
        SIM_PROCESS_ID,
        SIM_PROCESS_INCARNATION,
        SIM_PROCESS_PATH,
        SwitchableLifecycle,
    )

    first = DiagnosticLifecycleObservation(
        process_id=SIM_PROCESS_ID,
        process_path=SIM_PROCESS_PATH,
        product_version=SIM_BUILD,
        process_incarnation=SIM_PROCESS_INCARNATION,
    )
    lifecycle = SwitchableLifecycle(
        first, replace(first, process_incarnation="2026-09-28T00:00:00+00:00")
    )

    def replace_after_guard(script, _clock):
        if "addPool" in script:
            lifecycle.switch()

    run = _run_remote(
        tmp_path,
        monkeypatch,
        before_script=replace_after_guard,
        boundary_overrides={"diagnostic_lifecycle": lifecycle},
    )
    assert lifecycle.switched
    assert run.record.primary_failure
    assert [item["effect"] for item in run.snapshot["dhcp_timeline"]] == [
        "clientMode",
        "addPool",
    ]
    assert not run.record.restoration_proven
    assert run.snapshot["devices"]


def test_operator_cancellation_before_pool_keeps_earlier_e5_and_cleans_up(
    tmp_path, monkeypatch
):
    """A cancelled in-scope episode records the stop and retires its lab."""
    cancelled = False

    def interrupt(script, _clock):
        nonlocal cancelled
        if "addPool" in script and not cancelled:
            cancelled = True
            raise KeyboardInterrupt

    run = _run_remote(tmp_path, monkeypatch, before_script=interrupt)
    assert cancelled
    assert run.record.primary_failure == "cancelled"
    # v3: the client-mode effect precedes the interrupted pool write.
    assert [item["effect"] for item in run.snapshot["dhcp_timeline"]] == ["clientMode"]
    assert run.record.restoration_proven


def test_remote_stage_requires_sp2_campaign_before_backend_contact(tmp_path, capsys):
    """The registered private stage cannot run outside campaign accounting."""
    args = request_args("SP2-REMOTE-RELAY") + authorization_args("SP2-REMOTE-RELAY")

    def forbidden(_root):
        raise AssertionError("a direct remote stage must refuse before backend")

    code = service_qualification.main(
        args,
        environ={"PT_MCP_GOVERNED_ROOT": str(tmp_path)},
        boundaries_factory=forbidden,
    )
    assert code == 2
    assert "stage_requires_its_campaign" in capsys.readouterr().out


def test_slow_admissible_trace_keeps_terminal_and_cleanup(tmp_path, monkeypatch):
    """Latency consumes the phase clock without stealing later reserves."""
    run = _run_remote(
        tmp_path,
        monkeypatch,
        before_script=lambda _script, clock: clock.sleep(0.15),
    )
    assert (
        run.measurement("M-SP2-REMOTE-POOL").conclusion
        is MeasurementConclusion.SUPPORTED_IN_SAMPLE
    )
    assert (
        run.measurement("M-SP2-REMOTE-FINAL").conclusion
        is MeasurementConclusion.SUPPORTED_IN_SAMPLE
    )
    assert run.record.budget.elapsed_seconds > 30
    assert run.record.budget.elapsed_seconds < 3600
    assert run.record.restoration_proven


def test_remote_campaign_identity_cannot_borrow_sp1_authority():
    """The new stage remains inside the SP-2 campaign source gate."""
    from dataclasses import replace

    from packet_tracer_mcp.application.use_cases.qualify_server_services import (
        CampaignQualificationAuthority,
    )
    from packet_tracer_mcp.application.use_cases.server_pt_campaign import SP2_CAMPAIGN
    from packet_tracer_mcp.domain.enterprise.models.service_qualification import (
        RepositoryIdentity,
    )
    from tests.service_qualification_engine import SIM_SHA, SIM_TREE

    stage = "SP2-REMOTE-RELAY"
    request = _request(request_args(stage) + authorization_args(stage))
    authorization = request.authorization
    assert authorization is not None
    repository = RepositoryIdentity(
        branch="feature/sim",
        head=SIM_SHA,
        tree=SIM_TREE,
        clean=True,
        upstream="cisco/feature/sim",
        upstream_head=SIM_SHA,
    )
    grant = CampaignQualificationAuthority(
        campaign_id=SP2_CAMPAIGN.campaign_id,
        episode=3,
        admission_record=f"episode-0003-{authorization.attempt_id}-qualification-admission",
        attempt_id=authorization.attempt_id,
        authorization_id=authorization.authorization_id,
        sha=SIM_SHA,
        tree=SIM_TREE,
        process_incarnation="sim-incarnation",
    )
    assert grant.permits(request, repository)
    assert not replace(grant, campaign_id="SERVER-PT-SP1-ROUTED-01").permits(
        request, repository
    )


def test_named_pool_over_capacity_cannot_support_remote_binding():
    """Four physical rows cannot satisfy a stored two-client pool policy."""
    client = ClientReading(
        "BR1-DEFAULT-PC-01",
        True,
        True,
        "0001.0001.0001",
        "10.72.32.2",
        "255.255.255.248",
    )
    binding = {
        "device": client.client,
        "found": True,
        "port_found": True,
        "error": "",
        "ipv4": client.ipv4,
        "netmask": client.netmask,
        "gateway_reads": [{"api": True, "error": "", "value": "10.72.32.1"}],
        "dns_api": True,
        "dns_error": "",
        "dns_server": "10.72.0.2",
    }
    named = _scan(
        "BR1_DATA",
        LeaseRow(0, "10.72.32.2", client.mac, 100.0, "FastEthernet0"),
        LeaseRow(1, "10.72.32.3", "0001.0001.0002", 100.0, "FastEthernet0"),
        LeaseRow(2, "10.72.32.4", "0001.0001.0003", 100.0, "FastEthernet0"),
        LeaseRow(3, "10.72.32.5", "0001.0001.0004", 100.0, "FastEthernet0"),
    )
    assert named.termination == "window_exhausted" and named.capacity == 2
    default = _scan("serverPool")
    result = sp2_pool_diagnostic.assess_sp2_remote_samples(
        (client, client),
        (binding, binding),
        (named, named),
        (default, default),
        named_range=AddressRange("10.72.32.2", "10.72.32.3"),
        expected_mask="255.255.255.248",
        expected_gateway="10.72.32.1",
        expected_dns="10.72.0.2",
        expected_capacity=2,
    )
    assert result.conclusion is MeasurementConclusion.CONTRADICTED
    assert "sample_1:named_rows_exceed_capacity" in result.causes


def test_required_static_route_evidence_cannot_be_removed_with_catalog():
    """A matching adapter cannot replace the measured route provenance."""
    from dataclasses import replace
    from types import SimpleNamespace

    from packet_tracer_mcp.application.server_service_qualification.workflows.sp2_remote_relay import (
        _sp2_remote_contract_mismatch,
    )

    contract = sp2_remote_relay_contract(BUILD, RUN_ID)
    router = contract.device_capabilities["1941"]
    changed = router.model_copy(
        update={
            "evidence": [
                row
                for row in router.evidence
                if row.capability != "supports_static_routes"
            ]
        },
        deep=True,
    )
    supplied = {**contract.device_capabilities, "1941": changed}

    class ChangedCatalog:
        def capabilities_for(self, model, _build):
            return supplied[model]

    forged = replace(
        contract,
        device_capabilities=supplied,
        device_capability_catalog=ChangedCatalog(),
    )
    execution = SimpleNamespace(
        definition=_sp2_remote_relay(),
        record=SimpleNamespace(run_id=RUN_ID),
    )
    assert _sp2_remote_contract_mismatch(execution, forged) == (
        "sp2_remote_required_capability_evidence_changed"
    )


def test_duplicate_client_probe_rows_refuse_and_keep_both_answers():
    """A local reader cannot choose the first of conflicting client rows."""
    from packet_tracer_mcp.domain.enterprise.services.dhcp_lease_evidence import (
        client_readings,
    )

    first = {
        "device": "BR1-DEFAULT-PC-01",
        "found": True,
        "port_found": True,
        "mode_type": "boolean",
        "mode": True,
        "mac": "0001.0001.0001",
        "ipv4": "10.72.32.2",
        "netmask": "255.255.255.248",
        "lease_time": "3600",
        "error": "",
    }
    second = {**first, "ipv4": "10.72.32.3"}
    [reading] = client_readings(
        {"clients": [first, second]}, ("BR1-DEFAULT-PC-01",)
    ).values()
    assert not reading.observed
    assert reading.cause == "client_row_duplicate"
    assert len(reading.raw_rows) == 2


def test_terminal_state_requires_named_pool_enabled_and_client_dhcp_mode():
    """A shaped final snapshot with a disabled server or static PC is inconclusive."""
    from packet_tracer_mcp.application.server_service_qualification.workflows import (
        sp2_remote_relay,
    )

    check = getattr(sp2_remote_relay, "_sp2_remote_terminal_state_complete", None)
    assert callable(check)
    contract = sp2_remote_relay_contract(BUILD, RUN_ID)
    [pool] = [
        action
        for action in contract.service_plan.actions
        if action.action_type.value == "configure_server_dhcp_pool"
    ]
    named = {
        "name": "BR1_DATA",
        "network": pool.network,
        "mask": pool.netmask,
        "gateway": pool.gateway,
        "dns": pool.dns_server,
        "start": pool.lease_start,
        "end": pool.lease_end,
        "max": pool.max_users,
    }
    default = {"name": "serverPool", "start": "10.72.0.0", "end": "10.72.0.5"}
    server = {"observed": True, "raw": {"enabled": True, "pools": [named, default]}}
    client = ClientReading(
        "BR1-DEFAULT-PC-01",
        True,
        True,
        "0001.0001.0001",
        "10.72.32.2",
        "255.255.255.248",
    )
    binding = {
        "device": client.client,
        "found": True,
        "port_found": True,
        "error": "",
        "ipv4": client.ipv4,
        "netmask": client.netmask,
        "gateway_reads": [{"api": True, "error": "", "value": pool.gateway}],
        "dns_api": True,
        "dns_error": "",
        "dns_server": pool.dns_server,
    }
    assert check(server, client, binding, pool)
    assert not check(
        {**server, "raw": {**server["raw"], "enabled": False}}, client, binding, pool
    )
    assert not check(
        {**server, "raw": {**server["raw"], "pools": [default]}}, client, binding, pool
    )
    assert not check(
        server,
        ClientReading(
            client.client, True, False, client.mac, client.ipv4, client.netmask
        ),
        binding,
        pool,
    )


def test_remote_client_reader_refuses_an_extra_foreign_row():
    """The one-client private projection has one selected answer, never two."""
    from contextlib import nullcontext
    from types import SimpleNamespace

    from packet_tracer_mcp.application.server_service_qualification.workflows.sp2_remote_relay import (
        _sp2_remote_client,
    )

    selected = {
        "device": "BR1-DEFAULT-PC-01",
        "found": True,
        "port_found": True,
        "mode_type": "boolean",
        "mode": True,
        "mac": "0001.0001.0001",
        "ipv4": "10.72.32.2",
        "netmask": "255.255.255.248",
        "lease_time": "3600",
        "error": "",
    }
    answer = SimpleNamespace(
        observed=True,
        payload={"clients": [selected, {**selected, "device": "foreign"}]},
    )
    execution = SimpleNamespace(
        ledger=SimpleNamespace(purpose_of=lambda _label: nullcontext()),
        probes=SimpleNamespace(read_dhcp_clients=lambda _selected: answer),
    )
    reading = _sp2_remote_client(execution, "foreign_case")
    assert not reading.observed
    assert reading.cause == "client_rows_ambiguous"
    assert len(reading.raw_rows) == 2


def test_remote_client_reader_requires_exact_interface_echo():
    """A same-device reply from another PC port is not the selected subject."""
    from contextlib import nullcontext
    from types import SimpleNamespace

    from packet_tracer_mcp.application.server_service_qualification.workflows.sp2_remote_relay import (
        _sp2_remote_client,
    )

    row = {
        "device": "BR1-DEFAULT-PC-01",
        "interface": "FastEthernet1",
        "found": True,
        "port_found": True,
        "mode_type": "boolean",
        "mode": True,
        "mac": "0001.0001.0001",
        "ipv4": "10.72.32.2",
        "netmask": "255.255.255.248",
        "lease_time": "3600",
        "error": "",
    }
    answer = SimpleNamespace(observed=True, payload={"clients": [row]})
    execution = SimpleNamespace(
        ledger=SimpleNamespace(purpose_of=lambda _label: nullcontext()),
        probes=SimpleNamespace(read_dhcp_clients=lambda _selected: answer),
    )
    reading = _sp2_remote_client(execution, "wrong_interface")
    assert not reading.observed
    assert reading.cause == "client_interface_mismatch"
    assert reading.raw_rows == (row,)


def test_recomputed_topology_hash_refuses_changed_device_id():
    """A stale stored physical hash cannot bind altered device identity."""
    from dataclasses import replace
    from types import SimpleNamespace

    from packet_tracer_mcp.application.server_service_qualification.workflows.sp2_remote_relay import (
        _sp2_remote_contract_mismatch,
    )
    from packet_tracer_mcp.domain.enterprise.services.topology_identity import (
        compute_topology_hashes,
    )

    contract = sp2_remote_relay_contract(BUILD, RUN_ID)
    devices = [
        item.model_copy(update={"id": "altered-device-id"}, deep=True)
        if item.name == "HQ-DEFAULT-ACCESS-SW-01"
        else item
        for item in contract.topology.devices
    ]
    topology = contract.topology.model_copy(update={"devices": devices}, deep=True)
    assert compute_topology_hashes(topology).physical_topology_hash != (
        contract.topology.physical_topology_hash
    )
    execution = SimpleNamespace(
        definition=_sp2_remote_relay(),
        record=SimpleNamespace(run_id=RUN_ID),
    )
    assert _sp2_remote_contract_mismatch(
        execution, replace(contract, topology=topology)
    ) == ("sp2_remote_topology_hash_changed")


def test_recomputed_manifest_hash_refuses_changed_binding():
    """A stale manifest hash cannot retarget a semantic device to another name."""
    from dataclasses import replace
    from types import SimpleNamespace

    from packet_tracer_mcp.application.server_service_qualification.workflows.sp2_remote_relay import (
        _sp2_remote_contract_mismatch,
    )

    contract = sp2_remote_relay_contract(BUILD, RUN_ID)
    bindings = [
        row.model_copy(update={"deployed_name": "foreign"}, deep=True)
        if row.deployed_name == "HQ-DEFAULT-ACCESS-SW-01"
        else row
        for row in contract.manifest.bindings
    ]
    manifest = contract.manifest.model_copy(update={"bindings": bindings}, deep=True)
    execution = SimpleNamespace(
        definition=_sp2_remote_relay(),
        record=SimpleNamespace(run_id=RUN_ID),
    )
    assert _sp2_remote_contract_mismatch(
        execution, replace(contract, manifest=manifest)
    ) == ("sp2_remote_manifest_hash_changed")


def test_exact_named_row_with_later_table_throw_supports_usable_binding():
    """An unknown end does not erase an observed usable physical association."""
    from packet_tracer_mcp.domain.enterprise.services.dhcp_lease_evidence import (
        classify_lease_scan,
    )

    client = ClientReading(
        "BR1-DEFAULT-PC-01",
        True,
        True,
        "0001.0001.0001",
        "10.72.32.2",
        "255.255.255.248",
    )
    binding = {
        "device": client.client,
        "found": True,
        "port_found": True,
        "error": "",
        "ipv4": client.ipv4,
        "netmask": client.netmask,
        "gateway_reads": [{"api": True, "error": "", "value": "10.72.32.1"}],
        "dns_api": True,
        "dns_error": "",
        "dns_server": "10.72.0.2",
    }
    named = classify_lease_scan(
        {
            "requested": "BR1_DATA",
            "found": True,
            "name": "BR1_DATA",
            "max": 2,
            "window": 3,
            "error": "",
            "entries": [
                {
                    "index": 0,
                    "return_kind": "object",
                    "error": "",
                    "row": {
                        "ipAddress": client.ipv4,
                        "macAddress": client.mac,
                        "leaseTime": 100.0,
                        "port": "FastEthernet0",
                    },
                },
                {
                    "index": 1,
                    "return_kind": "throw",
                    "error": "lease table end",
                    "row": None,
                },
                {"index": 2, "return_kind": "null", "error": "", "row": None},
            ],
        },
        pool_name="BR1_DATA",
    )
    assert named.observed and named.termination == "throw"
    default = _scan("serverPool")
    result = sp2_pool_diagnostic.assess_sp2_remote_samples(
        (client, client),
        (binding, binding),
        (named, named),
        (default, default),
        named_range=AddressRange("10.72.32.2", "10.72.32.3"),
        expected_mask="255.255.255.248",
        expected_gateway="10.72.32.1",
        expected_dns="10.72.0.2",
        expected_capacity=2,
    )
    assert result.conclusion is MeasurementConclusion.SUPPORTED_IN_SAMPLE
    assert "named_table_end_not_calibrated" in result.limitations
    assert result.facts["exclusive_serving"] is False


def test_unselected_physical_row_withholds_one_client_remote_support():
    """An owned one-PC fixture cannot explain another MAC's pool lease."""
    client = ClientReading(
        "BR1-DEFAULT-PC-01",
        True,
        True,
        "0001.0001.0001",
        "10.72.32.2",
        "255.255.255.248",
    )
    binding = {
        "device": client.client,
        "found": True,
        "port_found": True,
        "error": "",
        "ipv4": client.ipv4,
        "netmask": client.netmask,
        "gateway_reads": [{"api": True, "error": "", "value": "10.72.32.1"}],
        "dns_api": True,
        "dns_error": "",
        "dns_server": "10.72.0.2",
    }
    named = _scan(
        "BR1_DATA",
        LeaseRow(0, client.ipv4, client.mac, 100.0, "FastEthernet0"),
        LeaseRow(1, "10.72.32.3", "0001.0001.9999", 100.0, "FastEthernet0"),
    )
    default = _scan("serverPool")
    result = sp2_pool_diagnostic.assess_sp2_remote_samples(
        (client, client),
        (binding, binding),
        (named, named),
        (default, default),
        named_range=AddressRange("10.72.32.2", "10.72.32.3"),
        expected_mask="255.255.255.248",
        expected_gateway="10.72.32.1",
        expected_dns="10.72.0.2",
        expected_capacity=2,
    )
    assert result.conclusion is MeasurementConclusion.INCONCLUSIVE
    assert "sample_1:unselected_named_lease_row" in result.causes
    named_selected = _scan(
        "BR1_DATA", LeaseRow(0, client.ipv4, client.mac, 100.0, "FastEthernet0")
    )
    default_foreign = _scan(
        "serverPool", LeaseRow(0, "10.72.0.2", "0001.0001.9999", 100.0, "FastEthernet0")
    )
    other = sp2_pool_diagnostic.assess_sp2_remote_samples(
        (client, client),
        (binding, binding),
        (named_selected, named_selected),
        (default_foreign, default_foreign),
        named_range=AddressRange("10.72.32.2", "10.72.32.3"),
        expected_mask="255.255.255.248",
        expected_gateway="10.72.32.1",
        expected_dns="10.72.0.2",
        expected_capacity=2,
    )
    assert other.conclusion is MeasurementConclusion.INCONCLUSIVE
    assert "sample_1:unselected_default_lease_row" in other.causes


def test_product_operation_cap_leaves_terminal_budget_in_real_coordinator(
    tmp_path, monkeypatch
):
    """A controlled product cap preserves terminal reads and owned cleanup."""
    run = _run_remote(tmp_path, monkeypatch, operation_ceiling=250)
    final = run.measurement("M-SP2-REMOTE-FINAL")
    assert (
        run.record.primary_failure
        == "budget:sp2_remote_product:operation_budget_exhausted"
    )
    assert final.status.value == "ran"
    assert run.record.restoration_proven
    assert run.record.budget.used_operations == len(run.switching.calls)


def test_product_time_cap_preserves_terminal_and_owned_cleanup(tmp_path, monkeypatch):
    """A product-only deadline leaves a final read window before cleanup."""
    advanced = False

    def expire_product_at_server_baseline(script, clock):
        nonlocal advanced
        if not advanced and "pool_count:" in script and "HQ-DEFAULT-DNS-01" in script:
            clock.now = 4001.0
            advanced = True

    run = _run_remote(
        tmp_path, monkeypatch, before_script=expire_product_at_server_baseline
    )
    assert advanced
    assert (
        run.record.primary_failure == "budget:sp2_remote_product:time_budget_exhausted"
    )
    assert run.snapshot["dhcp_timeline"] == []
    assert run.measurement("M-SP2-REMOTE-FINAL").status.value == "ran"
    assert run.record.restoration_proven
    assert run.record.budget.used_operations == len(run.switching.calls)


def test_slow_relayed_acquisition_is_observed_within_the_bounded_window(
    tmp_path, monkeypatch
):
    """RED at 81f7821c: e4 sampled twice at 2 s and saw no address.

    A lease that arrives after the two fixed samples reproduced e4's outcome
    offline. Profile v2 polls the client passively inside a bounded window
    before the two separated samples; nothing else is sent to the client.
    """
    run = _run_remote(
        tmp_path,
        monkeypatch,
        engine_config={
            "dhcp_retry_on_server_enable": False,
            "dhcp_mode_acquire_after_evals": 40,
        },
    )
    measurement = run.measurement("M-SP2-REMOTE-POOL")
    assert measurement.conclusion is MeasurementConclusion.SUPPORTED_IN_SAMPLE, (
        run.record.primary_failure,
        measurement.causes,
    )
    acquisition = measurement.facts["acquisition"]
    assert acquisition["acquired"] is True
    assert 1 < len(acquisition["polls"]) <= acquisition["max_polls"]
    assert run.snapshot["dhcp_runs"] == []
    assert run.record.restoration_proven


def test_acquisition_window_exhaustion_retains_samples_without_support(
    tmp_path, monkeypatch
):
    """No address inside the window is a retained finding, never a retry."""
    run = _run_remote(
        tmp_path,
        monkeypatch,
        engine_config={
            "dhcp_retry_on_server_enable": False,
            "dhcp_mode_acquire_after_evals": 100000,
        },
    )
    measurement = run.measurement("M-SP2-REMOTE-POOL")
    assert measurement.conclusion is not MeasurementConclusion.SUPPORTED_IN_SAMPLE
    acquisition = measurement.facts["acquisition"]
    assert acquisition["acquired"] is False
    assert len(acquisition["polls"]) == acquisition["max_polls"]
    assert len(measurement.facts["samples"]) == 2
    assert [item["effect"] for item in run.snapshot["dhcp_timeline"]].count(
        "clientMode"
    ) == 1
    assert run.snapshot["dhcp_runs"] == []
    assert run.record.restoration_proven


def test_unobserved_server_gateway_stops_before_client_mode(tmp_path, monkeypatch):
    """A relayed reply needs the server's planned return hop, read not assumed."""
    run = _run_remote(
        tmp_path, monkeypatch, engine_config={"server_gateway_dropped": True}
    )
    measurement = run.measurement("M-SP2-REMOTE-POOL")
    assert "sp2_remote_server_gateway_unverified" in measurement.causes
    assert "clientMode" not in [
        item["effect"] for item in run.snapshot["dhcp_timeline"]
    ]
    assert measurement.facts["server_binding"]["device"] == "HQ-DEFAULT-DNS-01"
    assert run.record.restoration_proven


def _wrap_reader(monkeypatch, name, label, replace):
    """Replace one coordinator reading at one labelled step, others real."""
    from packet_tracer_mcp.application.server_service_qualification.workflows import (
        sp2_remote_relay as qss,
    )

    real = getattr(qss, name)

    def reader(execution, step, *args, **kwargs):
        value = real(execution, step, *args, **kwargs)
        return replace(value) if step == label else value

    monkeypatch.setattr(qss, name, reader)


def test_named_pool_present_before_mode_stops_before_client_mode(tmp_path, monkeypatch):
    """v3 mode-first is observed: a named pool read present refuses mode."""
    from dataclasses import replace

    from packet_tracer_mcp.domain.enterprise.services.dhcp_lease_evidence import (
        TERMINATION_NULL,
    )

    def present(scans):
        return {
            **scans,
            "BR1_DATA": replace(
                scans["BR1_DATA"], cause="", termination=TERMINATION_NULL
            ),
        }

    _wrap_reader(monkeypatch, "_sp2_remote_scan", "before_mode", present)
    run = _run_remote(tmp_path, monkeypatch)
    assert run.record.primary_failure == "sp2_remote_named_pool_present_before_mode"
    assert run.snapshot["dhcp_timeline"] == []
    assert run.record.restoration_proven


def test_client_bound_between_mode_and_pool_stops_before_pool(tmp_path, monkeypatch):
    """An address seen after mode but before the pool cannot license E6."""
    from dataclasses import replace

    _wrap_reader(
        monkeypatch,
        "_sp2_remote_client",
        "after_mode_before_pool",
        lambda reading: replace(reading, ipv4="10.72.32.9"),
    )
    run = _run_remote(tmp_path, monkeypatch)
    assert run.record.primary_failure == "sp2_remote_client_state_changed_before_pool"
    assert [item["effect"] for item in run.snapshot["dhcp_timeline"]] == ["clientMode"]
    assert run.record.restoration_proven


def test_server_enabled_between_mode_and_pool_stops_before_pool(tmp_path, monkeypatch):
    """A process read enabled before the pool write cannot license E6."""

    def enabled(snapshot):
        return {**snapshot, "raw": {**snapshot["raw"], "enabled": True}}

    _wrap_reader(monkeypatch, "_sp2_remote_snapshot", "after_mode_before_pool", enabled)
    run = _run_remote(tmp_path, monkeypatch)
    assert run.record.primary_failure == "sp2_remote_server_state_changed_before_pool"
    assert [item["effect"] for item in run.snapshot["dhcp_timeline"]] == ["clientMode"]
    assert run.record.restoration_proven
