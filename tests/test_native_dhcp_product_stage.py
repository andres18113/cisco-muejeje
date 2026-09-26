"""The owned native DHCP stage calls the maintained product entry end to end."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from importlib import import_module
from pathlib import Path

import pytest
from service_entry_fixture import IsolationPreflight, RecordingConfigurationRuntime

from packet_tracer_mcp.adapters.cli import service_qualification
from packet_tracer_mcp.adapters.cli.service_qualification import (
    native_dhcp_http_product_contract,
    production_boundaries,
)
from packet_tracer_mcp.application.ports.service_run_record import (
    RunRecordPersistenceError,
)
from packet_tracer_mcp.application.use_cases.apply_enterprise_services import (
    ServiceStageRuntimes,
)
from packet_tracer_mcp.application.use_cases.qualify_server_services import (
    _Q3ConfigurationRuntime,
)
from packet_tracer_mcp.domain.enterprise.models.configuration import (
    CreateVlan,
    SetEndpointDhcp,
    SetEndpointStaticAddress,
    VerificationKind,
)
from packet_tracer_mcp.domain.enterprise.models.configuration_runtime import (
    ActionExecutionStatus,
    ConfigurationApplicationStatus,
    RuntimeActionMutation,
)
from packet_tracer_mcp.domain.enterprise.models.service_entry import (
    ServiceRunStatus,
    ServiceStage,
    ServiceStageResult,
)
from packet_tracer_mcp.domain.enterprise.models.service_plan import (
    ConfigureServerDhcpPool,
    ServiceVerificationKind,
)
from packet_tracer_mcp.domain.enterprise.models.service_qualification import (
    MeasurementConclusion,
    QualificationRecord,
    RepositoryIdentity,
    stage_definition,
)
from packet_tracer_mcp.domain.enterprise.models.service_runtime import (
    ObservationFact,
    ServiceApplicationResult,
    ServiceVerificationResult,
)
from packet_tracer_mcp.infrastructure.execution.endpoint_address_observer import (
    PacketTracerEndpointAddressObserver,
)
from packet_tracer_mcp.infrastructure.execution.enterprise_configuration_runtime import (
    PacketTracerEnterpriseConfigurationRuntime,
)
from packet_tracer_mcp.infrastructure.execution.enterprise_service_runtime import (
    PacketTracerEnterpriseServiceRuntime,
)
from packet_tracer_mcp.infrastructure.persistence.server_pt_commissioning_store import (
    ServerPtCommissioningStore,
)
from packet_tracer_mcp.infrastructure.persistence.service_qualification_store import (
    QualificationRecordStore,
)
from packet_tracer_mcp.infrastructure.persistence.service_run_record_store import (
    ServiceRunRecordStore,
)
from tests.service_qualification_engine import (
    FORWARDING_ROWS,
    SIM_BUILD,
    SIM_PROCESS_ID,
    SIM_PROCESS_INCARNATION,
    SIM_PROCESS_PATH,
    SIM_SHA,
    SIM_TREE,
    NodeEngine,
    NodeEngineTransport,
    authorization_args,
    request_args,
    require_node,
    simulated_boundaries,
)

STAGE = "Q3-NATIVE-PRODUCT"
CAMPAIGN = "SERVER-PT-DHCP-AUTONOMOUS-02"
ATTEMPT = "e" * 32
MANDATE = (
    Path(__file__).resolve().parents[1]
    / "docs/reference/server-pt/assignments/ServerPT_DHCP_Delegated_Autonomy_Mandate.md"
)


def _hybrid_configuration(bound, inventory):
    """Use actual E5 endpoints while keeping unrelated IOS readiness local."""
    real = PacketTracerEnterpriseConfigurationRuntime(
        lambda: [item.model_dump(mode="json") for item in inventory],
        bound.send,
        bound.send_and_wait,
        convergence_interval_seconds=0.0,
    )
    synthetic = RecordingConfigurationRuntime(targets=list(inventory))

    class Hybrid:
        def inventory(self):
            return list(inventory)

        def apply_actions(self, actions):
            endpoint = [
                item
                for item in actions
                if isinstance(item, SetEndpointStaticAddress | SetEndpointDhcp)
            ]
            actual = {item.action_id: item for item in real.apply_actions(endpoint)}
            return [
                actual.get(item.id)
                or RuntimeActionMutation(action_id=item.id, applied=True)
                for item in actions
            ]

        def verify(self, expectations):
            endpoint = [
                item
                for item in expectations
                if item.kind
                in {
                    VerificationKind.ENDPOINT_ADDRESSING,
                    VerificationKind.ENDPOINT_DHCP_MODE,
                }
            ]
            actual = {item.expectation_id: item for item in real.verify(endpoint)}
            other = [item for item in expectations if item.id not in actual]
            synthetic_rows = {
                item.expectation_id: item for item in synthetic.verify(other)
            }
            return [
                actual.get(item.id) or synthetic_rows[item.id] for item in expectations
            ]

        def observe_access_forwarding(self, *args, **kwargs):
            return synthetic.observe_access_forwarding(*args, **kwargs)

        def wait_for_voice_access_forwarding(self, expectations):
            return synthetic.wait_for_voice_access_forwarding(expectations)

    return Hybrid()


def _service_runtime(bound, inventory):
    real = PacketTracerEnterpriseServiceRuntime(
        lambda: inventory,
        bound.send_and_wait,
        dispatch_and_wait=bound.dispatch_and_wait,
        convergence_interval_seconds=0.0,
        sleeper=lambda _seconds: None,
        http_timeout_seconds=1.0,
    )
    real._dhcp_state_interval = 0.0
    real._dhcp_state_max_samples = 3
    return real


def _without_enumeration(runtime):
    """Model production qualification runtimes that refuse broad inventory."""

    class NoInventory:
        def inventory(self):
            raise AssertionError("workspace enumeration forbidden")

        def __getattr__(self, name):
            return getattr(runtime, name)

    return NoInventory()


def _run(
    directory,
    capsys,
    monkeypatch,
    *,
    retry_on_enable,
    pc2_late=False,
    selected_count=1,
    start_offset=99,
    public_entry=False,
    inject_partial_product=False,
    fail_complete=False,
):
    definition = stage_definition(STAGE)
    contract = native_dhcp_http_product_contract(
        SIM_BUILD,
        "offline-stage",
        selected_count=selected_count,
        start_offset=start_offset,
    )
    inventory = [item.model_dump(mode="json") for item in contract.inventory]
    source = RepositoryIdentity(
        branch="feature/server-pt-goal-foundations",
        head=SIM_SHA,
        tree=SIM_TREE,
        clean=True,
        upstream="cisco/feature/server-pt-goal-foundations",
        upstream_head="b" * 40,
    )
    monkeypatch.setattr(service_qualification, "repository_identity", lambda _: source)
    if public_entry:
        monkeypatch.setattr(
            service_qualification.service_tools,
            "ImportIsolationPreflight",
            lambda _root: IsolationPreflight(),
        )
    if inject_partial_product:
        qualifier = import_module(
            "packet_tracer_mcp.application.use_cases.qualify_server_services"
        )
        real_apply = qualifier.apply_enterprise_services

        def partial_product(*args, **kwargs):
            result = real_apply(*args, **kwargs)
            assert result.status is ServiceRunStatus.VERIFIED
            result.status = ServiceRunStatus.PARTIAL
            return result

        monkeypatch.setattr(qualifier, "apply_enterprise_services", partial_product)
    store = ServerPtCommissioningStore(directory, CAMPAIGN)
    # Production's ignored sibling of the qualification store.
    product_directory = directory / "data/services/product-qualification"

    class CompleteFails(ServiceRunRecordStore):
        def complete(self, record):
            raise RunRecordPersistenceError("injected terminal product write failure")

    store.save_ledger_record(
        "episode-0006-opening",
        {
            "kind": "episode_opening",
            "episode": 6,
            "question": "Does the maintained product verify native DHCP before HTTP?",
            "stop_rule": "stop on unknown effect or incomplete lease attribution",
            "source_sha": SIM_SHA,
            "source_tree": SIM_TREE,
            "attempt_ids": [ATTEMPT],
            "tests_run": ["tests/test_native_dhcp_product_stage.py"],
            "targets": list(definition.fixture_names),
            "permitted_effects": [f"qualification:{STAGE}"],
            "allocated_operations": definition.budget.max_operations,
            "allocated_seconds": 2400.0,
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
    engine = NodeEngine(
        directory,
        **{
            "dhcp_default_pool": "native",
            "default_pool_realigns_on_address": True,
            "dhcp_native_start_behavior": (
                "coupled_candidate" if start_offset != 99 else "coupled"
            ),
            "dhcp_native_max_behavior": (
                "resize_candidate" if selected_count == 2 else "resize"
            ),
            "dhcp_mode_acquires": True,
            "dhcp_retry_on_server_enable": retry_on_enable,
            "pc2_mode_on_server_enable": pc2_late,
            "stp_rows": FORWARDING_ROWS,
            "terminals": True,
        },
    )
    try:
        transport = NodeEngineTransport(engine)

        def boundaries(_root):
            return simulated_boundaries(
                directory,
                transport,
                repository=lambda: source,
                record_store=QualificationRecordStore(
                    directory / "data/services/qualification"
                ),
                native_product_contract=lambda build, run_id: (
                    native_dhcp_http_product_contract(
                        build,
                        run_id,
                        selected_count=selected_count,
                        start_offset=start_offset,
                    )
                ),
                native_product_runtimes=lambda bound, _rows: ServiceStageRuntimes(
                    configuration=_without_enumeration(
                        _hybrid_configuration(bound, contract.inventory)
                    ),
                    services=_without_enumeration(_service_runtime(bound, inventory)),
                ),
                native_product_import_preflight=IsolationPreflight,
                native_product_record_store_factory=lambda: (
                    CompleteFails(product_directory)
                    if fail_complete
                    else ServiceRunRecordStore(product_directory)
                ),
                native_product_endpoint_observer=lambda bound: (
                    PacketTracerEndpointAddressObserver(bound.send_and_wait)
                ),
                native_public_product_entry=(
                    public_entry
                    if callable(public_entry)
                    else service_qualification._native_public_product_entry(directory)
                    if public_entry
                    else None
                ),
            )

        code = service_qualification.main(
            request_args(STAGE)
            + authorization_args(STAGE, attempt_id=ATTEMPT)
            + [
                "--campaign",
                "dhcp-autonomy",
                "--charter",
                str(MANDATE),
                "--episode",
                "6",
            ],
            environ={"PT_MCP_GOVERNED_ROOT": str(directory)},
            boundaries_factory=boundaries,
        )
        summary = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
        paths = list((directory / "data/services/qualification").rglob("*.json"))
        assert len(paths) == 1, (code, summary)
        (record_path,) = paths
        record = QualificationRecord.model_validate_json(
            record_path.read_text(encoding="utf-8")
        )
        return code, summary, record, transport.calls, engine.snapshot(), store
    finally:
        engine.close()


def test_production_stage_binds_public_interior_policy_and_profile(tmp_path):
    """The next LIVE composition requests an interior window through MCP."""
    boundaries = production_boundaries(tmp_path)
    contract = boundaries.native_product_contract("9.0.1.0858", "current-candidate")
    [pool] = [
        item
        for item in contract.service_plan.actions
        if isinstance(item, ConfigureServerDhcpPool)
    ]
    definition = stage_definition(STAGE)
    assert (pool.lease_start, pool.lease_end, pool.max_users) == (
        "192.0.2.125",
        "192.0.2.126",
        2,
    )
    assert definition.profile_version == "4"
    assert definition.dhcp_pool_capacity == 2
    assert boundaries.native_public_product_entry is not None


def test_production_product_runtimes_supply_inner_inventory(tmp_path):
    """The inner E5/E6 setters can index only the verified four-target fixture."""
    contract = native_dhcp_http_product_contract(SIM_BUILD, "inner-inventory")
    boundary = production_boundaries(tmp_path)

    class NeverDispatch:
        def send(self, _script):
            raise AssertionError("inventory must not dispatch")

        def send_and_wait(self, _script, _timeout):
            raise AssertionError("inventory must not dispatch")

        def dispatch_and_wait(self, _script, _timeout):
            raise AssertionError("inventory must not dispatch")

        def clock(self):
            return 0.0

        def capped_sleep(self, _seconds):
            raise AssertionError("inventory must not sleep")

    runtimes = boundary.native_product_runtimes(NeverDispatch(), contract.inventory)
    expected = list(contract.inventory)
    expected_ports = {item.device_name: set(item.interfaces) for item in expected}
    assert {
        item.device_name: set(item.interfaces)
        for item in runtimes.configuration.inventory()
    } == expected_ports
    assert {
        item.device_name: set(item.interfaces) for item in runtimes.services.inventory()
    } == expected_ports
    assert set(runtimes.configuration._targets) == {
        item.device_name for item in expected
    }
    store = boundary.native_product_record_store_factory()
    assert store.base_dir == (tmp_path / "data/services/product-qualification")
    product_path = store.path_for("qualification/probe", "probe-product")
    product_path.parent.mkdir(parents=True)
    product_path.write_text("{}", encoding="utf-8")
    qualification_store = QualificationRecordStore(
        tmp_path / "data/services/qualification"
    )
    assert qualification_store.attempt_exists("fresh-attempt") is False
    with pytest.raises(RuntimeError, match="never enumerates the workspace"):
        boundary.configuration_runtime(NeverDispatch()).inventory()
    with pytest.raises(RuntimeError, match="never enumerates the workspace"):
        boundary.service_runtime(NeverDispatch()).inventory()


def test_product_stage_ios_batch_indexes_inner_fixture_inventory(tmp_path):
    """The stage wrapper reaches E5 VLAN without the episode 6 inventory error."""
    require_node()
    contract = native_dhcp_http_product_contract(SIM_BUILD, "stage-inner-ios")
    engine = NodeEngine(tmp_path, dhcp_default_pool="native")
    try:
        for device in contract.topology.devices:
            engine.seed_device(device.name, device.model)
        transport = NodeEngineTransport(engine)

        class Bound:
            send = transport.send
            send_and_wait = transport.send_and_wait
            dispatch_and_wait = transport.dispatch_and_wait
            clock = staticmethod(lambda: 0.0)
            capped_sleep = staticmethod(lambda _seconds: None)

        inner = (
            production_boundaries(tmp_path)
            .native_product_runtimes(Bound(), contract.inventory)
            .configuration
        )
        inner._ios_readiness = lambda _name: True
        stage_runtime = _Q3ConfigurationRuntime(inner, contract.inventory)
        assert len(stage_runtime.inventory()) == 4
        assert inner._targets == {}
        vlan = next(
            action
            for action in contract.configuration_plan.actions
            if isinstance(action, CreateVlan)
        )
        (result,) = stage_runtime.apply_actions([vlan])
        assert result.applied, (result.failure_code, result.message)
        assert set(inner._targets) == {item.device_name for item in contract.inventory}
    finally:
        engine.close()


def test_owned_stage_runs_one_attributed_dhcp_then_cold_http(
    tmp_path, capsys, monkeypatch
):
    """A governed positive run reaches the one cold HTTP request and cleans up."""
    require_node()
    code, summary, record, calls, snapshot, store = _run(
        tmp_path, capsys, monkeypatch, retry_on_enable=True
    )
    assert code == 0, summary
    measures = {item.experiment_id: item for item in record.measurements}
    assert (
        measures["M-NATIVE-PRODUCT"].conclusion
        is MeasurementConclusion.SUPPORTED_IN_SAMPLE
    )
    assert (
        measures["M-NATIVE-PRODUCT-FINAL"].conclusion
        is MeasurementConclusion.SUPPORTED_IN_SAMPLE
    )
    requests = [script for _kind, script in calls if ".go(" in script]
    assert len(requests) == 1
    assert "192.0.2.10" in requests[0]
    assert not any("dhcpRun" in script for _kind, script in calls)
    assert not any("ping " in script for _kind, script in calls)
    assert snapshot["devices"] == []
    assert snapshot["links"] == 0
    assert snapshot["live_clients"] == 0
    assert store.load_phase_status(ATTEMPT, "qualification")["restoration_proven"]


def test_owned_stage_runs_two_attributed_clients_then_two_cold_http_requests(
    tmp_path, capsys, monkeypatch
):
    """The governed stage accepts independent two-client product results."""
    require_node()
    code, summary, record, calls, snapshot, store = _run(
        tmp_path,
        capsys,
        monkeypatch,
        retry_on_enable=True,
        selected_count=2,
    )
    assert code == 0, summary
    measured = {item.experiment_id: item for item in record.measurements}
    assert (
        measured["M-NATIVE-PRODUCT"].conclusion
        is MeasurementConclusion.SUPPORTED_IN_SAMPLE
    )
    assert len([script for _kind, script in calls if ".go(" in script]) == 2
    assert snapshot["devices"] == []
    assert store.load_phase_status(ATTEMPT, "qualification")["restoration_proven"]


def test_owned_stage_uses_shifted_policy_for_two_clients(tmp_path, capsys, monkeypatch):
    """The full stage carries a requested .151-.152 window to the runtime."""
    require_node()
    code, summary, record, calls, _snapshot, _store = _run(
        tmp_path,
        capsys,
        monkeypatch,
        retry_on_enable=True,
        selected_count=2,
        start_offset=150,
    )
    assert code == 0, summary
    measured = {item.experiment_id: item for item in record.measurements}
    assert (
        measured["M-NATIVE-PRODUCT"].conclusion
        is MeasurementConclusion.SUPPORTED_IN_SAMPLE
    )
    assert any("192.0.2.151" in script for _kind, script in calls)
    assert len([script for _kind, script in calls if ".go(" in script]) == 2


def test_owned_stage_uses_registered_four_input_tool_with_default_catalog(
    tmp_path, capsys, monkeypatch
):
    """The governed stage invokes the public handler and seals its product."""
    require_node()
    code, summary, record, calls, snapshot, store = _run(
        tmp_path,
        capsys,
        monkeypatch,
        retry_on_enable=True,
        selected_count=2,
        start_offset=124,
        public_entry=True,
    )
    assert code == 0, summary
    measured = {item.experiment_id: item for item in record.measurements}
    product = measured["M-NATIVE-PRODUCT"]
    assert product.conclusion is MeasurementConclusion.SUPPORTED_IN_SAMPLE
    assert product.facts["entry_surface"] == "registered_four_input"
    assert product.facts["fresh_public_build"] == "9.0.1.0858"
    assert product.facts["product_record_path"]
    assert len([script for _kind, script in calls if ".go(" in script]) == 2
    assert snapshot["devices"] == []
    assert store.load_phase_status(ATTEMPT, "qualification")["restoration_proven"]


def test_public_tool_persistence_failure_stops_stage_and_restores_fixture(
    tmp_path, capsys, monkeypatch
):
    """A public tool result cannot outvote a failed terminal record write."""
    require_node()
    code, _summary, record, calls, snapshot, store = _run(
        tmp_path,
        capsys,
        monkeypatch,
        retry_on_enable=True,
        selected_count=2,
        start_offset=124,
        public_entry=True,
        fail_complete=True,
    )
    assert code != 0
    measured = {item.experiment_id: item for item in record.measurements}
    assert measured["M-NATIVE-PRODUCT"].conclusion is MeasurementConclusion.INCONCLUSIVE
    assert len([script for _kind, script in calls if ".go(" in script]) == 2
    assert snapshot["devices"] == []
    assert store.load_phase_status(ATTEMPT, "qualification")["restoration_proven"]


def test_public_stage_cannot_accept_callback_without_fresh_binding(
    tmp_path, capsys, monkeypatch
):
    """A claimed public result without A5 build evidence cannot be promoted."""
    require_node()
    contract = native_dhcp_http_product_contract(
        SIM_BUILD, "spoof", selected_count=2, start_offset=124
    )
    required = [
        item
        for item in contract.service_plan.verification_expectations
        if item.kind
        in {
            ServiceVerificationKind.DHCP_LEASE,
            ServiceVerificationKind.HTTP_FETCH,
        }
    ]
    fake_path = tmp_path / "fake-public-record.json"
    fake_path.write_text("{}", encoding="utf-8")

    def unbound_result(_bound, _factory, manifest, _intent, _build, _label):
        return ServiceStageResult(
            run_id="unbound-public-claim",
            deployment_id=manifest.deployment_id,
            stage=ServiceStage.COMPLETED,
            persisted_stage=ServiceStage.COMPLETED,
            status=ServiceRunStatus.VERIFIED,
            record_path=str(fake_path),
            service_result=ServiceApplicationResult(
                service_plan_id=contract.service_plan.id,
                service_semantic_hash=contract.service_plan.semantic_hash,
                source_topology_hash=contract.service_plan.source_topology_hash,
                source_configuration_hash=contract.service_plan.source_configuration_hash,
                status=ConfigurationApplicationStatus.VERIFIED,
                verification_results=[
                    ServiceVerificationResult(
                        expectation_id=item.id,
                        service_id=item.service_id,
                        status=ActionExecutionStatus.VERIFIED,
                        evidence_kind=item.evidence_kind,
                        fresh_evidence=True,
                        observation=ObservationFact.OBSERVED,
                    )
                    for item in required
                ],
            ),
        )

    code, _summary, record, _calls, snapshot, _store = _run(
        tmp_path,
        capsys,
        monkeypatch,
        retry_on_enable=True,
        selected_count=2,
        start_offset=124,
        public_entry=unbound_result,
    )
    assert code != 0
    measured = {item.experiment_id: item for item in record.measurements}
    assert measured["M-NATIVE-PRODUCT"].conclusion is MeasurementConclusion.INCONCLUSIVE
    assert measured["M-NATIVE-PRODUCT"].facts["fresh_public_build"] == ""
    assert snapshot["devices"] == []


def test_positive_run_seals_its_product_record_in_the_campaign_archive(
    tmp_path, capsys, monkeypatch
):
    """Changing or deleting the decisive product record fails the archive."""
    require_node()
    code, summary, record, _calls, _snapshot, store = _run(
        tmp_path, capsys, monkeypatch, retry_on_enable=True
    )
    assert code == 0, summary
    measure = next(
        item for item in record.measurements if item.experiment_id == "M-NATIVE-PRODUCT"
    )
    product = Path(measure.facts["product_record_path"])
    assert product.is_file()
    assert store.external_source_registered(ATTEMPT, "product-record")
    assert store.verify_index() == ()
    original = product.read_bytes()
    product.write_bytes(original + b" ")
    assert store.verify_index() == ("archive_bytes_changed",)
    product.write_bytes(original)
    assert store.verify_index() == ()
    product.unlink()
    assert store.verify_index() != ()


def test_unsealable_product_record_fails_closed(tmp_path, capsys, monkeypatch):
    """A verified product run whose record cannot be sealed is not a success."""
    require_node()
    real = ServerPtCommissioningStore.register_external_source

    def refuse_product(self, attempt_id, label, source_path):
        if label == "product-record":
            raise ValueError("injected sealing failure")
        return real(self, attempt_id, label, source_path)

    monkeypatch.setattr(
        ServerPtCommissioningStore, "register_external_source", refuse_product
    )
    code, summary, record, _calls, _snapshot, store = _run(
        tmp_path, capsys, monkeypatch, retry_on_enable=True
    )
    measure = next(
        item for item in record.measurements if item.experiment_id == "M-NATIVE-PRODUCT"
    )
    assert measure.conclusion is MeasurementConclusion.SUPPORTED_IN_SAMPLE
    assert code != 0
    status = store.load_phase_status(ATTEMPT, "qualification")
    assert status["outcome"] == "stopped"
    findings = summary["campaign"]["archive_findings"]
    assert "product_record_unsealed:ValueError" in status["archive_findings"]
    assert "product_record_unsealed:ValueError" in findings
    assert not store.external_source_registered(ATTEMPT, "product-record")


def test_partial_status_write_never_exits_zero(tmp_path, capsys, monkeypatch):
    """A status whose digest was never written is not a completed phase."""
    require_node()
    store_module = import_module(
        "packet_tracer_mcp.infrastructure.persistence.server_pt_commissioning_store"
    )
    real = store_module._write_once

    def fail_status_digest(path, payload):
        if Path(path).name == "qualification-status.sha256":
            raise OSError("injected digest write failure")
        return real(path, payload)

    monkeypatch.setattr(store_module, "_write_once", fail_status_digest)
    code, summary, record, _calls, _snapshot, store = _run(
        tmp_path, capsys, monkeypatch, retry_on_enable=True
    )
    measure = next(
        item for item in record.measurements if item.experiment_id == "M-NATIVE-PRODUCT"
    )
    assert measure.conclusion is MeasurementConclusion.SUPPORTED_IN_SAMPLE
    assert code != 0
    assert "status_unrecorded:OSError" in summary["campaign"]["archive_findings"]
    with pytest.raises(ValueError):
        store.load_phase_status(ATTEMPT, "qualification")
    # Both records are still sealed for recovery.
    assert store.external_source_registered(ATTEMPT, "product-record")
    assert store.external_source_registered(ATTEMPT, "qualification-record")


def test_owned_stage_never_promotes_partial_product_run(tmp_path, capsys, monkeypatch):
    """Verified lease/fetch rows cannot mask a partial overall product run."""
    require_node()
    code, _summary, record, calls, _snapshot, _store = _run(
        tmp_path,
        capsys,
        monkeypatch,
        retry_on_enable=True,
        inject_partial_product=True,
    )
    measures = {item.experiment_id: item for item in record.measurements}
    assert code != 0
    assert measures["M-NATIVE-PRODUCT"].conclusion is MeasurementConclusion.INCONCLUSIVE
    assert any(".go(" in script for _kind, script in calls)
    assert measures["M-NATIVE-PRODUCT"].facts["product_summary"]["status"] == "partial"


def test_owned_stage_requires_completed_product_record(tmp_path, capsys, monkeypatch):
    """A successful HTTP read without durable completion remains inconclusive."""
    require_node()
    code, _summary, record, calls, _snapshot, _store = _run(
        tmp_path, capsys, monkeypatch, retry_on_enable=True, fail_complete=True
    )
    measure = next(
        item for item in record.measurements if item.experiment_id == "M-NATIVE-PRODUCT"
    )
    assert code != 0
    assert measure.conclusion is MeasurementConclusion.INCONCLUSIVE
    assert any(".go(" in script for _kind, script in calls)
    assert measure.facts["product_summary"]["status"] == "unknown"


@pytest.mark.parametrize(
    ("retry_on_enable", "pc2_late"),
    [(False, False), (True, True)],
)
def test_owned_stage_stops_http_without_attributable_lease(
    tmp_path, capsys, monkeypatch, retry_on_enable, pc2_late
):
    """Lease absence and inactive-client drift both withhold HTTP."""
    require_node()
    code, _summary, record, calls, snapshot, store = _run(
        tmp_path,
        capsys,
        monkeypatch,
        retry_on_enable=retry_on_enable,
        pc2_late=pc2_late,
    )
    assert code != 0
    measures = {item.experiment_id: item for item in record.measurements}
    assert measures["M-NATIVE-PRODUCT"].conclusion is MeasurementConclusion.INCONCLUSIVE
    assert not any(".go(" in script for _kind, script in calls)
    assert measures["M-NATIVE-PRODUCT-FINAL"].facts["complete"] is True
    assert snapshot["devices"] == []
    assert snapshot["links"] == 0
    assert snapshot["live_clients"] == 0
    assert store.load_phase_status(ATTEMPT, "qualification")["restoration_proven"]
