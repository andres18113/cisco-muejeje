"""SP-1 qualification stages over a simulated engine and a simulated campus.

Production code: the qualification CLI and its campaign gate, the coordinator,
the SP-1 contract composer, the registered four-input product tool, both
product runtimes, the readiness gate and the record stores. Simulated: the
Packet Tracer the fixtures are created in (the Node engine) and the routed
campus the product runtimes talk to (`routed_product_simulation`). The two
simulations are separate, so the product's dispatches are counted by the
campus transport here, not by the stage ledger: these tests calibrate the
planned product cost; they do not prove the LIVE ledger accounting of it.
"""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from campus_product_simulation import CampusPlans
from cold_http_acceptance_harness import FakeClock
from routed_product_simulation import RoutedCampusTerminal
from service_entry_fixture import IsolationPreflight

from packet_tracer_mcp.adapters.cli import service_qualification
from packet_tracer_mcp.adapters.cli.sp1_routed_qualification import (
    sp1_device_catalog,
    sp1_routed_product_contract,
    sp1_run_parameters,
)
from packet_tracer_mcp.domain.enterprise.models.service_qualification import (
    SP1_BRANCH_CLIENTS,
    SP1_HQ_CLIENTS,
    SP1_ROUTED_FINAL_OPERATIONS,
    SP1_ROUTED_PRODUCT_OPERATIONS,
    DiagnosticLifecycleObservation,
    MeasurementConclusion,
    QualificationRecord,
    RepositoryIdentity,
    stage_definition,
)
from packet_tracer_mcp.infrastructure.catalog.cables import ALL_LINK_TYPES
from packet_tracer_mcp.infrastructure.execution.endpoint_address_observer import (
    PacketTracerEndpointAddressObserver,
)
from packet_tracer_mcp.infrastructure.persistence.server_pt_commissioning_store import (
    ServerPtCommissioningStore,
)
from packet_tracer_mcp.infrastructure.persistence.service_qualification_store import (
    QualificationRecordStore,
)
from tests.service_qualification_engine import (
    SIM_BUILD,
    SIM_PROCESS_ID,
    SIM_PROCESS_INCARNATION,
    SIM_PROCESS_PATH,
    SIM_SHA,
    SIM_TREE,
    NodeEngine,
    NodeEngineTransport,
    SwitchableLifecycle,
    authorization_args,
    request_args,
    require_node,
    simulated_boundaries,
)

CAMPAIGN = "SERVER-PT-SP1-ROUTED-01"
ATTEMPT = "5" * 32
RUN_ID = "2026-09-26T08-00-00Z-5f1a0c2e"
CHARTER = (
    Path(__file__).resolve().parents[1]
    / "docs/reference/server-pt/assignments/Prompt_SP1_Routed_DNS_HTTP.md"
)


def _plans(stage: str) -> tuple[CampusPlans, object]:
    """Compose exactly the contract the coordinator will compose for RUN_ID."""
    definition = stage_definition(stage)
    contract = sp1_routed_product_contract(
        SIM_BUILD, RUN_ID, definition.selected_clients
    )
    plans = CampusPlans(
        payload=json.loads(contract.intent_json),
        intent_json=contract.intent_json,
        manifest=contract.manifest,
        inventory=list(contract.inventory),
        configuration_plan=contract.configuration_plan,
        service_plan=contract.service_plan,
        deployed_names={item.id: item.name for item in contract.topology.devices},
        device_count=len(contract.topology.devices),
        link_count=len(contract.topology.links),
    )
    return plans, contract


def _address(contract, name: str) -> str:
    return next(
        item.ipv4
        for item in contract.configuration_plan.actions
        if item.action_type.value == "set_endpoint_static" and item.device_name == name
    )


class _SwitchingTransport:
    """The stage's channel: the Node engine, or the campus while the product talks.

    Every product dispatch still goes through the stage's ledgered transport,
    so the effect gate, receiver continuity and the operation count apply to
    it exactly as LIVE; only the simulated receiver underneath differs.
    """

    def __init__(self, engine, campus, before_campus_call=None) -> None:
        self.engine = engine
        self.campus = campus
        self.target = engine
        self.campus_calls = 0
        self.before_campus_call = before_campus_call

    def _pick(self):
        if self.target is self.campus:
            self.campus_calls += 1
            if self.before_campus_call is not None:
                self.before_campus_call(self.campus_calls)
        return self.target

    def send(self, script):
        return self._pick().send(script)

    def send_and_wait(self, script, timeout):
        return self._pick().send_and_wait(script, timeout)

    def dispatch_and_wait(self, script, timeout):
        return self._pick().dispatch_and_wait(script, timeout)


class _CampusView:
    """The ledgered transport, pointed at the campus for each product call."""

    def __init__(self, bound, switching: _SwitchingTransport) -> None:
        self._bound = bound
        self._switching = switching
        self.clock = bound.clock
        self.capped_sleep = bound.capped_sleep

    def _via_campus(self, name, *args):
        self._switching.target = self._switching.campus
        try:
            return getattr(self._bound, name)(*args)
        finally:
            self._switching.target = self._switching.engine

    def send(self, script):
        return self._via_campus("send", script)

    def send_and_wait(self, script, timeout):
        return self._via_campus("send_and_wait", script, timeout)

    def dispatch_and_wait(self, script, timeout):
        return self._via_campus("dispatch_and_wait", script, timeout)


#: The switching channel of the latest run, for the tests that count on it.
LAST: dict = {}


def _run(
    tmp_path,
    capsys,
    monkeypatch,
    stage: str,
    configure=None,
    *,
    lifecycle=None,
    before_campus_call=None,
    wrap_entry=None,
):
    """Run one SP-1 stage end to end under its campaign, offline."""
    require_node()
    definition = stage_definition(stage)
    plans, contract = _plans(stage)
    terminal = RoutedCampusTerminal(
        tmp_path / "campus",
        plans,
        FakeClock(),
        dns_server=_address(contract, "HQ-DEFAULT-DNS-01"),
        records={
            sp1_run_parameters(RUN_ID).hostname: _address(contract, "HQ-DEFAULT-WEB-01")
        },
    )
    if configure is not None:
        configure(terminal, contract)
    views: dict = {}

    def product_runtimes(bound, inventory):
        # The production factory, over the same ledgered transport.
        view = views.setdefault(id(bound), _CampusView(bound, LAST["switching"]))
        return service_qualification._native_product_runtimes(view, inventory)

    def endpoint_observer(bound):
        view = views.setdefault(id(bound), _CampusView(bound, LAST["switching"]))
        return PacketTracerEndpointAddressObserver(view.send_and_wait)

    source = RepositoryIdentity(
        branch="feature/server-pt-goal-foundations",
        head=SIM_SHA,
        tree=SIM_TREE,
        clean=True,
        upstream="cisco/feature/server-pt-goal-foundations",
        upstream_head="b" * 40,
    )
    monkeypatch.setattr(service_qualification, "repository_identity", lambda _: source)
    monkeypatch.setattr(
        service_qualification.service_tools,
        "ImportIsolationPreflight",
        lambda _root: IsolationPreflight(),
    )
    store = ServerPtCommissioningStore(tmp_path, CAMPAIGN)
    store.save_ledger_record(
        "episode-0001-opening",
        {
            "kind": "episode_opening",
            "episode": 1,
            "question": "Does the product serve routed DNS and HTTP?",
            "stop_rule": "stop on unknown effect or an unverified client",
            "source_sha": SIM_SHA,
            "source_tree": SIM_TREE,
            "attempt_ids": [ATTEMPT],
            "tests_run": ["tests/test_sp1_routed_stage.py"],
            "targets": list(definition.fixture_names),
            "permitted_effects": [f"qualification:{stage}"],
            "allocated_operations": definition.budget.max_operations,
            "allocated_seconds": float(definition.budget.max_seconds) + 600.0,
            "opened_at_utc": (datetime.now(UTC) - timedelta(seconds=5)).isoformat(),
        },
    )
    store.save_process_launch(
        ATTEMPT,
        {
            "pid": SIM_PROCESS_ID,
            "process_path": SIM_PROCESS_PATH,
            "process_incarnation": SIM_PROCESS_INCARNATION,
            "campaign_id": CAMPAIGN,
            "execution_purpose": "experimental",
            "source_sha": SIM_SHA,
            "source_tree": SIM_TREE,
        },
    )
    store.refresh_index()
    engine = NodeEngine(tmp_path, terminals=True)
    try:
        transport = _SwitchingTransport(
            NodeEngineTransport(engine), terminal, before_campus_call
        )
        LAST["switching"] = transport

        def boundaries(_root):
            extra = {}
            if wrap_entry is not None:
                extra["sp1_public_product_entry"] = wrap_entry(
                    service_qualification._native_public_product_entry(
                        tmp_path, dhcp_authority=False
                    )
                )
            return simulated_boundaries(
                tmp_path,
                transport,
                repository=lambda: source,
                record_store=QualificationRecordStore(
                    tmp_path / "data/services/qualification"
                ),
                new_run_id=lambda _moment: RUN_ID,
                native_product_runtimes=product_runtimes,
                native_product_endpoint_observer=endpoint_observer,
                **({"diagnostic_lifecycle": lifecycle} if lifecycle else {}),
                **extra,
            )

        code = service_qualification.main(
            request_args(stage)
            + authorization_args(stage, attempt_id=ATTEMPT)
            + ["--campaign", "sp1", "--charter", str(CHARTER), "--episode", "1"],
            environ={"PT_MCP_GOVERNED_ROOT": str(tmp_path)},
            boundaries_factory=boundaries,
        )
        summary = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
        paths = list((tmp_path / "data/services/qualification").rglob("*.json"))
        record = (
            QualificationRecord.model_validate_json(
                paths[0].read_text(encoding="utf-8")
            )
            if len(paths) == 1
            else None
        )
        return code, summary, record, engine.snapshot(), store, terminal
    finally:
        engine.close()


def _measured(record: QualificationRecord) -> dict:
    return {item.experiment_id: item for item in record.measurements}


# -- the contract ----------------------------------------------------------------


@pytest.mark.parametrize("stage", ["SP1-ROUTED-W1", "SP1-ROUTED-W2"])
def test_the_composed_contract_is_exactly_the_stage_fixture(stage):
    """Devices, ports and cables are what the product designs; clients match."""
    definition = stage_definition(stage)
    contract = sp1_routed_product_contract(
        SIM_BUILD, RUN_ID, definition.selected_clients
    )

    assert {(item.name, item.model) for item in contract.topology.devices} == {
        (item.name, item.model) for item in definition.fixtures
    }
    assert {
        (item.device_a, item.port_a, item.device_b, item.port_b, item.cable)
        for item in contract.topology.links
    } == {
        (item.device_a, item.port_a, item.device_b, item.port_b, item.cable)
        for item in definition.links
    }
    served = {
        item.client_device_name
        for item in contract.service_plan.verification_expectations
        if item.kind.value == "http_fetch"
    }
    assert served == set(definition.selected_clients)


def test_the_two_workloads_differ_only_in_their_clients():
    """W1 is the HQ pair (one gateway); W2 adds both branches."""
    w1, w2 = stage_definition("SP1-ROUTED-W1"), stage_definition("SP1-ROUTED-W2")
    assert w1.selected_clients == SP1_HQ_CLIENTS
    assert w2.selected_clients == (*SP1_HQ_CLIENTS, *SP1_BRANCH_CLIENTS)
    assert w1.fixtures == w2.fixtures and w1.links == w2.links
    # The router-to-router crossovers are part of what an authorization names.
    assert sum(item.endswith("/cross") for item in w2.link_bindings) == 2


def test_every_run_chooses_its_own_addresses_marker_and_host_name():
    """One run's evidence can never satisfy another run's expectations."""
    first, second = sp1_run_parameters("run-a"), sp1_run_parameters("run-b")
    assert first != sp1_run_parameters("run-b")
    assert first == sp1_run_parameters("run-a")
    for item in (first, second):
        assert item.address_space.startswith("10.")
        assert 64 <= int(item.address_space.split(".")[1]) <= 127
    assert first.marker != second.marker and first.hostname != second.hostname


def test_candidate_evidence_is_named_only_while_the_catalog_lacks_it():
    """Today the build's catalog does not support static routes on 1941/2911."""
    catalog = sp1_device_catalog(SIM_BUILD)
    assert catalog is not None
    for model in ("1941", "2911"):
        caps = catalog.capabilities_for(model, SIM_BUILD)
        assert caps.supports_static_routes.value == "supported"


# -- the stage -------------------------------------------------------------------


def test_w2_serves_every_client_across_three_routers(tmp_path, capsys, monkeypatch):
    """The whole routed workload verifies and the lab is restored."""
    code, summary, record, snapshot, store, _terminal = _run(
        tmp_path, capsys, monkeypatch, "SP1-ROUTED-W2"
    )

    assert code == 0, summary
    measured = _measured(record)
    product = measured["M-SP1-ROUTED-PRODUCT"]
    assert product.conclusion is MeasurementConclusion.SUPPORTED_IN_SAMPLE, (
        product.facts,
        record.primary_failure,
    )
    assert product.facts["entry_surface"] == "registered_four_input"
    assert product.facts["device_catalog"] == "candidate"
    assert product.limitations == [
        "candidate_device_evidence_not_global_product_promotion"
    ]
    checks = product.facts["client_checks"]
    assert set(checks) == set(SP1_HQ_CLIENTS + SP1_BRANCH_CLIENTS)
    for name, kinds in checks.items():
        for kind in ("http_fetch", "dns_resolution", "dns_negative_control"):
            assert kinds[kind] == "verified", (name, kinds)
        assert kinds["http_by_hostname"] == "verified", (name, kinds)
    groups = product.facts["routed_groups"]
    assert groups and {item["status"] for item in groups} == {"admitted"}
    assert any(len(item["device_ids"]) == 3 for item in groups)

    final = measured["M-SP1-ROUTED-FINAL"]
    assert final.conclusion is MeasurementConclusion.SUPPORTED_IN_SAMPLE, final.facts
    routers = final.facts["routers"]
    assert {(row["device"], row["query"]) for row in routers} == {
        (name, query)
        for name in ("HQ-EDGE-RTR-01", "BR1-EDGE-RTR-01", "BR2-EDGE-RTR-01")
        for query in ("show_ip_interface_brief", "show_ip_route")
    }
    assert all(
        "S " in row["output"] or row["query"] == "show_ip_interface_brief"
        for row in routers
    )
    assert len(final.facts["client_bindings"]) == 6

    # Crossovers where the product designed them; nothing left behind.
    cables = {tuple(item[:4]): item[4] for item in snapshot["link_cables"]}
    crossed = {
        key for key, value in cables.items() if value == str(ALL_LINK_TYPES["cross"])
    }
    assert crossed == {
        (
            "BR1-EDGE-RTR-01",
            "GigabitEthernet0/1",
            "HQ-EDGE-RTR-01",
            "GigabitEthernet0/0",
        ),
        (
            "BR1-EDGE-RTR-01",
            "GigabitEthernet0/0",
            "BR2-EDGE-RTR-01",
            "GigabitEthernet0/0",
        ),
    }
    assert set(cables.values()) == {
        str(ALL_LINK_TYPES["cross"]),
        str(ALL_LINK_TYPES["straight"]),
    }
    assert snapshot["devices"] == []
    assert record.restoration_proven
    assert store.external_source_registered(ATTEMPT, "product-record")
    assert store.verify_index() == ()
    # Calibration: the product's real dispatch count fits its planned cost.
    print(
        f"\nSP1-W2 product dispatches={LAST['switching'].campus_calls} "
        f"stage operations={record.budget.used_operations}"
    )
    assert LAST["switching"].campus_calls <= SP1_ROUTED_PRODUCT_OPERATIONS
    assert record.budget.used_operations <= record.budget.max_operations
    assert sum(row["channel_calls"] for row in routers) <= SP1_ROUTED_FINAL_OPERATIONS


def test_w1_requests_only_the_hq_clients_over_one_gateway(
    tmp_path, capsys, monkeypatch
):
    """Inter-VLAN only: every routed group is read on the HQ router alone."""
    code, summary, record, _snapshot, _store, terminal = _run(
        tmp_path, capsys, monkeypatch, "SP1-ROUTED-W1"
    )

    assert code == 0, summary
    product = _measured(record)["M-SP1-ROUTED-PRODUCT"]
    assert set(product.facts["client_checks"]) == set(SP1_HQ_CLIENTS)
    assert all(
        item["device_ids"] == ["HQ-EDGE-RTR-01"] or len(item["device_ids"]) == 1
        for item in product.facts["routed_groups"]
    )
    requested = {client for _t, _kind, client, *_ in terminal.requests}
    assert requested == set(SP1_HQ_CLIENTS)
    print(f"\nSP1-W1 product dispatches={LAST['switching'].campus_calls}")


def test_a_withheld_return_route_stops_the_stage_and_keeps_the_evidence(
    tmp_path, capsys, monkeypatch
):
    """The product refuses the clients behind it; the stage restores anyway."""
    import ipaddress

    from packet_tracer_mcp.application.use_cases import (
        service_access_readiness_gate as gate,
    )

    monkeypatch.setattr(gate, "ROUTED_GROUP_DEADLINE_SECONDS", 4.0)

    def configure(terminal, contract):
        client = next(
            item
            for item in contract.configuration_plan.actions
            if item.action_type.value == "set_endpoint_static"
            and item.device_name == "BR2-DEFAULT-PC-01"
        )
        network = ipaddress.ip_interface(f"{client.ipv4}/{client.netmask}").network
        terminal.withheld_routes.add(("HQ-EDGE-RTR-01", str(network.network_address)))

    code, summary, record, snapshot, _store, terminal = _run(
        tmp_path, capsys, monkeypatch, "SP1-ROUTED-W2", configure
    )

    assert code == 1, summary
    assert record.primary_failure == "sp1_product_not_verified"
    product = _measured(record)["M-SP1-ROUTED-PRODUCT"]
    assert product.conclusion is MeasurementConclusion.INCONCLUSIVE
    checks = product.facts["client_checks"]
    assert checks["BR2-DEFAULT-PC-01"]["http_fetch"] == "dependency_blocked"
    assert checks["HQ-DEFAULT-PC-01"]["http_fetch"] == "verified"
    requested = {client for _t, _kind, client, *_ in terminal.requests}
    assert not requested & {"BR2-DEFAULT-PC-01", "BR2-DEFAULT-PC-02"}
    # The terminal observation still ran and shows the table that lacked it.
    final = _measured(record)["M-SP1-ROUTED-FINAL"]
    assert final.facts["routers"]
    assert snapshot["devices"] == []
    assert record.restoration_proven


def test_an_sp1_stage_outside_its_campaign_is_refused(tmp_path, capsys):
    """No campaign, no SP-1 stage: refused before anything is composed."""
    code = service_qualification.main(
        request_args("SP1-ROUTED-W1")
        + authorization_args("SP1-ROUTED-W1", attempt_id=ATTEMPT),
        environ={"PT_MCP_GOVERNED_ROOT": str(tmp_path)},
        boundaries_factory=lambda _root: pytest.fail("composed without campaign"),
    )
    assert code == 2
    assert json.loads(capsys.readouterr().out.strip().splitlines()[-1]) == {
        "outcome": "refused",
        "reason": "stage_requires_its_campaign",
    }


def test_a_contract_for_other_clients_is_refused_before_any_effect(
    tmp_path, capsys, monkeypatch
):
    """W2 composed with W1's clients is not W2: the stage stops at the contract."""
    original = sp1_routed_product_contract
    monkeypatch.setattr(
        service_qualification,
        "sp1_routed_product_contract",
        lambda build, run_id, _clients: original(build, run_id, SP1_HQ_CLIENTS),
    )

    code, summary, record, snapshot, _store, _terminal = _run(
        tmp_path, capsys, monkeypatch, "SP1-ROUTED-W2"
    )

    assert code == 1, summary
    assert record.primary_failure == "sp1_intent_services_differ_from_stage"
    assert LAST["switching"].campus_calls == 0
    assert snapshot["devices"] == []


def _pairing(incarnation: str = SIM_PROCESS_INCARNATION):
    return DiagnosticLifecycleObservation(
        process_id=SIM_PROCESS_ID,
        process_path=SIM_PROCESS_PATH,
        product_version=SIM_BUILD,
        process_incarnation=incarnation,
    )


def test_a_receiver_replaced_mid_product_receives_nothing_further(
    tmp_path, capsys, monkeypatch
):
    """Receiver continuity is decided per dispatch, inside the product too."""
    readings = SwitchableLifecycle(
        _pairing(), _pairing("2026-09-26T09:00:00.0000000+00:00")
    )

    def replace_at(number):
        if number == 40:
            readings.switch()

    code, summary, record, snapshot, _store, _terminal = _run(
        tmp_path,
        capsys,
        monkeypatch,
        "SP1-ROUTED-W2",
        lifecycle=readings,
        before_campus_call=replace_at,
    )

    assert code != 0, summary
    assert LAST["switching"].campus_calls == 40
    product = _measured(record)["M-SP1-ROUTED-PRODUCT"]
    assert product.conclusion is not MeasurementConclusion.SUPPORTED_IN_SAMPLE
    assert any(item.refused for item in record.operations)
    # Nothing is removed from a receiver this run no longer owns.
    assert not record.restoration_proven
    assert snapshot["devices"]


def test_a_cancellation_inside_the_product_stops_and_is_recorded(
    tmp_path, capsys, monkeypatch
):
    """An operator interrupt mid-product is a cancellation, not a result."""

    def cancel_at(number):
        if number == 60:
            raise KeyboardInterrupt

    code, summary, record, snapshot, _store, _terminal = _run(
        tmp_path, capsys, monkeypatch, "SP1-ROUTED-W2", before_campus_call=cancel_at
    )

    assert code == 130, summary
    assert summary["primary_failure"] == "cancelled"
    assert record is not None and record.primary_failure == "cancelled"
    product = _measured(record)["M-SP1-ROUTED-PRODUCT"]
    assert product.conclusion is not MeasurementConclusion.SUPPORTED_IN_SAMPLE
    # Owned cleanup still ran: the fixtures are gone and restoration proven.
    assert snapshot["devices"] == []
    assert record.restoration_proven


# -- review findings (independent adversarial review of 2057070..6e5e527) --------


def test_an_intent_with_an_extra_client_is_refused_before_any_effect(
    tmp_path, capsys, monkeypatch
):
    """The plans match W1, but the intent the tool recomposes adds a client."""
    original = sp1_routed_product_contract

    def widened(build, run_id, clients):
        contract = original(build, run_id, clients)
        intent = json.loads(contract.intent_json)
        ids = {item.name: item.id for item in contract.topology.devices}
        for service in intent["sites"][0]["services"]:
            service["client_device_ids"].append(ids["BR1-DEFAULT-PC-01"])
        return replace(contract, intent_json=json.dumps(intent))

    monkeypatch.setattr(service_qualification, "sp1_routed_product_contract", widened)

    code, summary, record, snapshot, _store, _terminal = _run(
        tmp_path, capsys, monkeypatch, "SP1-ROUTED-W1"
    )

    assert code == 1, summary
    assert record.primary_failure == "sp1_intent_services_differ_from_stage"
    assert LAST["switching"].campus_calls == 0
    assert snapshot["devices"] == []


def test_a_verified_run_missing_one_routed_group_is_not_accepted(
    tmp_path, capsys, monkeypatch
):
    """Requests verified, but the BR2 group's admission is not in the result."""

    def drop_br2(entry):
        def invoke(*args):
            result = entry(*args)
            result.operational_readiness = [
                row
                for row in result.operational_readiness
                if row.get("client_segment_id") != "br2-data"
            ]
            return result

        return invoke

    code, summary, record, _snapshot, _store, _terminal = _run(
        tmp_path, capsys, monkeypatch, "SP1-ROUTED-W2", wrap_entry=drop_br2
    )

    assert code == 1, summary
    product = _measured(record)["M-SP1-ROUTED-PRODUCT"]
    assert product.conclusion is MeasurementConclusion.INCONCLUSIVE
    assert ["br2-data", "hq-servers"] in product.facts["expected_routed_groups"]


def test_a_candidate_run_records_the_exact_injected_evidence(
    tmp_path, capsys, monkeypatch
):
    """Every injected entry is named, digested and matched by the product."""
    code, summary, record, _snapshot, _store, _terminal = _run(
        tmp_path, capsys, monkeypatch, "SP1-ROUTED-W1"
    )

    assert code == 0, summary
    facts = _measured(record)["M-SP1-ROUTED-PRODUCT"].facts
    assert facts["product_device_catalog_injected"] is True
    assert [
        (item["model"], item["capability"], item["verified"])
        for item in facts["device_candidate_evidence"]
    ] == [
        ("1941", "supports_static_routes", False),
        ("2911", "supports_static_routes", False),
    ]
    assert len(facts["device_candidate_evidence_sha256"]) == 64


def test_an_unrecorded_ledger_result_never_reports_success(
    tmp_path, capsys, monkeypatch
):
    """A verified stage whose campaign result cannot be written is not a pass."""
    real = ServerPtCommissioningStore.save_ledger_record

    def failing(self, name, value):
        if name.endswith("-qualification-result"):
            raise OSError("injected ledger write failure")
        return real(self, name, value)

    monkeypatch.setattr(ServerPtCommissioningStore, "save_ledger_record", failing)

    code, summary, record, _snapshot, _store, _terminal = _run(
        tmp_path, capsys, monkeypatch, "SP1-ROUTED-W1"
    )

    assert _measured(record)["M-SP1-ROUTED-PRODUCT"].conclusion is (
        MeasurementConclusion.SUPPORTED_IN_SAMPLE
    )
    assert code != 0, summary
    assert "ledger_result_unrecorded" in json.dumps(summary["campaign"])


@pytest.mark.parametrize(
    ("service_type", "field", "value"),
    [
        ("http", "http_content", "SP1_ROUTED_000000000000"),
        ("http", "hostname", "www.other.lab.example"),
        ("dns", "address", "10.64.0.99"),
    ],
)
def test_an_intent_with_another_runs_value_is_refused_before_any_effect(
    tmp_path, capsys, monkeypatch, service_type, field, value
):
    """A self-consistent intent carrying a value this run did not derive."""
    original = sp1_routed_product_contract

    def altered(build, run_id, clients):
        contract = original(build, run_id, clients)
        intent = json.loads(contract.intent_json)
        for service in intent["sites"][0]["services"]:
            if service["service_type"] == service_type:
                service[field] = value
        return replace(contract, intent_json=json.dumps(intent))

    monkeypatch.setattr(service_qualification, "sp1_routed_product_contract", altered)

    code, summary, record, snapshot, _store, _terminal = _run(
        tmp_path, capsys, monkeypatch, "SP1-ROUTED-W1"
    )

    assert code == 1, summary
    assert record.primary_failure == "sp1_intent_values_differ_from_run"
    assert LAST["switching"].campus_calls == 0
    assert snapshot["devices"] == []


def test_an_intent_with_another_wan_subnet_is_refused_before_any_effect(
    tmp_path, capsys, monkeypatch
):
    """Third review pass: an uplink /30 the run did not derive changes routes."""
    original = sp1_routed_product_contract

    def rewired(build, run_id, clients):
        contract = original(build, run_id, clients)
        intent = json.loads(contract.intent_json)
        intent["sites"][0]["uplinks"][0].update(
            network="203.0.113.252/30",
            source_ipv4="203.0.113.253",
            target_ipv4="203.0.113.254",
        )
        return replace(contract, intent_json=json.dumps(intent))

    monkeypatch.setattr(service_qualification, "sp1_routed_product_contract", rewired)

    code, summary, record, snapshot, _store, _terminal = _run(
        tmp_path, capsys, monkeypatch, "SP1-ROUTED-W2"
    )

    assert code == 1, summary
    assert record.primary_failure == "sp1_intent_values_differ_from_run"
    assert LAST["switching"].campus_calls == 0
    assert snapshot["devices"] == []
