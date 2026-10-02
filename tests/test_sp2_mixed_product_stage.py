"""The private SP-2 mixed product stage over a hybrid simulation.

Production code: the qualification coordinator, the mixed contract composer,
the product use case with both product runtimes, the readiness gates and the
record stores. Simulated: the Node engine answers every endpoint script (the
DHCP server and clients, DNS and HTTP), and the routed campus answers every
router and switch. Neither is Packet Tracer. The engine's per-client pool is a
scenario setting, so these tests prove binding, composition, evidence handling
and budget, never native serving, relay or capacity.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

from campus_product_simulation import CampusPlans, TrunkEnd
from cold_http_acceptance_harness import FakeClock
from routed_product_simulation import _IOS_CALL
from service_entry_fixture import IsolationPreflight

from packet_tracer_mcp.adapters.cli import service_qualification
from packet_tracer_mcp.adapters.cli.service_qualification import _request
from packet_tracer_mcp.adapters.cli.sp2_mixed_qualification import (
    sp2_capacity_product_contract,
    sp2_mixed_product_contract,
)
from packet_tracer_mcp.application.use_cases.qualify_server_services import (
    qualify_server_services,
)
from packet_tracer_mcp.application.use_cases.server_pt_campaign import SP2_CAMPAIGN
from packet_tracer_mcp.domain.enterprise.models.capabilities import CapabilityStatus
from packet_tracer_mcp.domain.enterprise.models.service_qualification import (
    SP2_CAPACITY_SITE_CLIENTS,
    SP2_MIXED_CLIENTS,
    SP2_MIXED_FINAL_OPERATIONS,
    SP2_MIXED_PRODUCT_OPERATIONS,
    SP2_MIXED_SITE_CLIENTS,
    SP2_STAGES,
    STAGE_CEILINGS,
    STAGE_DEFINITIONS,
    MeasurementConclusion,
    QualificationRecord,
    QualificationStage,
    RepositoryIdentity,
    StageBudget,
    stage_definition,
)
from packet_tracer_mcp.infrastructure.catalog.service_capabilities import (
    packet_tracer_service_capabilities,
)
from packet_tracer_mcp.infrastructure.persistence.server_pt_commissioning_store import (
    ServerPtCommissioningStore,
)
from packet_tracer_mcp.infrastructure.persistence.service_qualification_store import (
    QualificationRecordStore,
)
from tests.service_qualification_engine import (
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
from tests.test_sp2_remote_relay_stage import _RelayCampus

BUILD = "9.0.1.0858"
RUN_ID = "sp2-mixed-stage-offline"
STAGE = "SP2-MIXED-PRODUCT"
SERVER = "HQ-DEFAULT-DNS-01"
POOLS = {"HQ": "serverPool", "BR1": "BR1_DATA", "BR2": "BR2_DATA"}
_NAME = re.compile(r'"((?:HQ|BR1|BR2)-[A-Z0-9-]+)"')
CAMPAIGN_ATTEMPT = "8" * 32
SP2_CHARTER = (
    Path(__file__).resolve().parents[1]
    / "docs/reference/server-pt/assignments/Prompt_SP2_Generalized_DHCP_Relay.md"
)


def _client_pools(*, capacity: bool = False) -> dict[str, str]:
    return {
        name: POOLS[site]
        for site, names in (
            SP2_CAPACITY_SITE_CLIENTS if capacity else SP2_MIXED_SITE_CLIENTS
        ).items()
        for name in names
    }


class _SwitchingTransport:
    """The stage channel: the Node engine by default, the campus when asked."""

    def __init__(self, engine, campus):
        self.engine = NodeEngineTransport(engine)
        self.campus = campus
        self.target = self.engine
        self.campus_calls = 0
        self.engine_product_calls = 0
        #: Optionally rewrites one answer, modelling a read that failed.
        self.rewrite = None

    def send(self, script):
        return self.target.send(script)

    def send_and_wait(self, script, timeout):
        return self.target.send_and_wait(script, timeout)

    def dispatch_and_wait(self, script, timeout):
        outcome = self.target.dispatch_and_wait(script, timeout)
        return self.rewrite(script, outcome) if self.rewrite else outcome


class _InitiallyUnconfiguredL2Campus(_RelayCampus):
    """Start blank and derive switch state only from dispatched IOS commands."""

    def __init__(self, *args, physical_links, **kwargs):
        super().__init__(*args, **kwargs)
        self.ignored_trunk_switch = ""
        self.switch_modes = {}
        self.physical_peers = {}
        self.applied_switch_payloads = []
        for link in physical_links:
            self.physical_peers[(link.device_a, link.port_a)] = (
                link.device_b,
                link.port_b,
                link.id,
            )
            self.physical_peers[(link.device_b, link.port_b)] = (
                link.device_a,
                link.port_a,
                link.id,
            )
        for switch in self.network.switches.values():
            switch.vlans.clear()
            switch.access.clear()
            switch.trunks.clear()

    def send(self, script):
        for device_json, payload_json in _IOS_CALL.findall(script):
            name, payload = json.loads(device_json), json.loads(payload_json)
            owner = self.network.switches.get(name)
            if owner is None:
                continue
            self.applied_switch_payloads.append((name, payload))
            current = ""
            for raw in payload.splitlines():
                command = raw.strip()
                if command.startswith("vlan "):
                    owner.vlans.add(int(command.split()[-1]))
                elif command.startswith("interface "):
                    current = command.removeprefix("interface ")
                elif command == "switchport mode access" and current:
                    self.switch_modes[(name, current)] = "access"
                elif command.startswith("switchport access vlan ") and current:
                    owner.access[current] = int(command.split()[-1])
                elif command == "switchport mode trunk" and current:
                    if name == self.ignored_trunk_switch:
                        continue
                    self.switch_modes[(name, current)] = "trunk"
                    peer = self.physical_peers.get((name, current))
                    if peer is not None:
                        owner.trunks[current] = TrunkEnd(
                            current, peer[0], peer[1], peer[2], frozenset({1})
                        )
                elif command.startswith("switchport trunk allowed vlan ") and current:
                    if current in owner.trunks:
                        owner.trunks[current].allowed = frozenset(
                            int(value) for value in command.split()[-1].split(",")
                        )
                elif command in {"exit", "end"}:
                    current = ""
        return super().send(script)


class _HybridView:
    """The ledgered transport, pointing each product call at its owner.

    A script naming only endpoints goes to the engine and one naming only
    routers or switches goes to the campus. A script naming both is a test
    defect, not a routing choice, so it fails loudly.
    """

    def __init__(
        self, bound, switching, network_names, before_call=None, ambiguous=False
    ):
        self.bound = bound
        self.switching = switching
        self.network_names = network_names
        self.before_call = before_call
        #: When set, every router answer names two candidate owners.
        self.ambiguous = ambiguous
        self.observation_context = bound.observation_context
        self.clock = bound.clock
        self.capped_sleep = bound.capped_sleep
        self.remaining_seconds = bound.remaining_seconds

    def _send(self, method, script, *args):
        names = set(_NAME.findall(script))
        network = names & self.network_names
        if self.before_call is not None:
            self.before_call(
                self.switching.campus_calls + self.switching.engine_product_calls + 1,
                script,
            )
        if network and names - self.network_names:
            raise AssertionError(f"a product script names both sides: {sorted(names)}")
        if network:
            self.switching.target = self.switching.campus
            self.switching.campus_calls += 1
        else:
            self.switching.engine_product_calls += 1
            if "var results=[]" in script:
                # E6 applies on the server, which the engine owns; the campus
                # still learns that services started, which arms its faults.
                self.switching.campus.events.append("service_apply")
        try:
            answer = getattr(self.bound, method)(script, *args)
        finally:
            self.switching.target = self.switching.engine
        if self.ambiguous and network:
            body = getattr(answer, "body", answer)
            try:
                payload = json.loads(body) if isinstance(body, str) else None
            except ValueError:
                payload = None
            if isinstance(payload, dict) and "owner_candidates" in payload:
                # Two candidate owners and no attributed one: ambiguous.
                payload.update(
                    owner_name="",
                    owner_evidence="",
                    owner_candidates=2,
                    owner_candidate_names=[*sorted(network), "OTHER"],
                )
                body = json.dumps(payload)
                answer = body if isinstance(answer, str) else replace(answer, body=body)
        return answer

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
    switching: _SwitchingTransport
    campus: object

    @property
    def record(self):
        return self.result.record

    def measurement(self, name):
        return next(
            item for item in self.record.measurements if item.experiment_id == name
        )


def _open_campaign_episode(tmp_path, monkeypatch, definition, episode):
    """Open one SP-2 campaign episode for an owned simulated process.

    Returns the boundary overrides the campaign route needs: the clean
    repository identity it re-reads and a record store inside the governed
    root, where the campaign may seal external sources.
    """
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
    store = ServerPtCommissioningStore(tmp_path, SP2_CAMPAIGN.campaign_id)
    store.save_ledger_record(
        f"episode-{episode:04d}-opening",
        {
            "kind": "episode_opening",
            "episode": episode,
            "question": "Does the mixed product serve every selected client?",
            "stop_rule": "stop on unknown effect or an unverified client",
            "source_sha": SIM_SHA,
            "source_tree": SIM_TREE,
            "attempt_ids": [CAMPAIGN_ATTEMPT],
            "tests_run": ["tests/test_sp2_mixed_product_stage.py"],
            "targets": list(definition.fixture_names),
            "permitted_effects": [f"qualification:{definition.stage.value}"],
            "allocated_operations": definition.budget.max_operations,
            "allocated_seconds": float(definition.budget.max_seconds) + 600.0,
            "opened_at_utc": (datetime.now(UTC) - timedelta(seconds=5)).isoformat(),
        },
    )
    store.save_process_launch(
        CAMPAIGN_ATTEMPT,
        {
            "pid": SIM_PROCESS_ID,
            "process_path": SIM_PROCESS_PATH,
            "process_incarnation": SIM_PROCESS_INCARNATION,
            "campaign_id": SP2_CAMPAIGN.campaign_id,
            "execution_purpose": "experimental",
            "source_sha": SIM_SHA,
            "source_tree": SIM_TREE,
        },
    )
    store.refresh_index()
    return {
        "repository": lambda: source,
        "record_store": QualificationRecordStore(
            tmp_path / "data/services/qualification"
        ),
    }


def _run(
    tmp_path,
    *,
    engine_config=None,
    campus_config=None,
    contract_factory=None,
    before_call=None,
    boundary_overrides=None,
    monkeypatch=None,
    operation_ceiling=None,
    rewrite=None,
    ambiguous_terminal_routers=False,
    stage=STAGE,
    run_id=RUN_ID,
    campaign_episode=None,
    capsys=None,
):
    require_node()
    definition = stage_definition(stage)
    campaign_overrides = (
        _open_campaign_episode(tmp_path, monkeypatch, definition, campaign_episode)
        if campaign_episode is not None
        else {}
    )
    capacity = stage == "SP2-CAPACITY-PRODUCT"
    constructor = (
        sp2_capacity_product_contract if capacity else sp2_mixed_product_contract
    )
    if operation_ceiling is not None:
        # A controlled smaller grant: the same stage with the product
        # allowance that remains after setup, terminal and owned cleanup.
        planned = (
            operation_ceiling
            - definition.setup_operations
            - definition.reserve_operations
            - SP2_MIXED_FINAL_OPERATIONS
        )
        definition = replace(
            definition,
            budget=StageBudget(
                operation_ceiling,
                definition.budget.max_seconds,
                reserve_seconds=definition.budget.reserve_seconds,
            ),
            experiments=(
                replace(definition.experiments[0], planned_operations=planned),
                definition.experiments[1],
            ),
        )
        monkeypatch.setitem(
            STAGE_CEILINGS,
            QualificationStage(stage),
            (operation_ceiling, definition.budget.max_seconds),
        )
        monkeypatch.setitem(STAGE_DEFINITIONS, QualificationStage(stage), definition)
    contract = constructor(BUILD, run_id)
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
    clock = FakeClock()
    server_address = next(
        item.ipv4
        for item in contract.configuration_plan.actions
        if item.action_type.value == "set_endpoint_static"
        and item.device_name == SERVER
    )
    campus_factory = _InitiallyUnconfiguredL2Campus if capacity else _RelayCampus
    campus = campus_factory(
        tmp_path / "campus",
        plans,
        clock,
        dns_server=server_address,
        records={},
        **({"physical_links": contract.topology.links} if capacity else {}),
    )
    if campus_config:
        campus_config(campus)
    options = {
        "terminals": True,
        "dhcp_default_pool": "native",
        "default_pool_realigns_on_address": True,
        "dhcp_native_start_behavior": "coupled_candidate",
        "dhcp_native_max_behavior": "resize_candidate",
        "dhcp_mode_acquires": True,
        "dhcp_retry_on_server_enable": True,
        "dhcp_client_pools": _client_pools(capacity=capacity),
        "dns_server_stub": True,
        # Measured on 9.0.1.0858 (e1-e6): a read past the rows throws.
        "dhcp_table_end": "native",
        **(engine_config or {}),
    }
    network_names = {
        item.name
        for item in definition.fixtures
        if item.model not in {"PC-PT", "Server-PT"}
    }
    engine = NodeEngine(tmp_path, **options)
    try:
        switching = _SwitchingTransport(engine, campus)
        switching.rewrite = rewrite

        built: list[object] = []

        def native_runtimes(bound, inventory):
            # The product binds its runtimes first; the terminal binds its own.
            view = _HybridView(
                bound,
                switching,
                network_names,
                before_call,
                ambiguous=ambiguous_terminal_routers and bool(built),
            )
            built.append(view)
            return service_qualification._native_product_runtimes(view, inventory)

        boundaries = simulated_boundaries(
            tmp_path,
            switching,
            clock=clock,
            sleep=clock.sleep,
            new_run_id=lambda _moment: run_id,
            native_product_runtimes=native_runtimes,
            native_product_import_preflight=lambda: IsolationPreflight(),
            **(
                {
                    "sp2_capacity_product_contract"
                    if capacity
                    else "sp2_mixed_product_contract": contract_factory or constructor
                }
            ),
            **campaign_overrides,
            **(boundary_overrides or {}),
        )
        if campaign_episode is not None:
            # The operator's route: the qualification CLI under its campaign,
            # which seals the records the qualification record cites.
            code = service_qualification.main(
                request_args(stage)
                + authorization_args(stage, attempt_id=CAMPAIGN_ATTEMPT)
                + ["--campaign", "sp2", "--charter", str(SP2_CHARTER)]
                + ["--episode", str(campaign_episode)],
                environ={"PT_MCP_GOVERNED_ROOT": str(tmp_path)},
                boundaries_factory=lambda _root: boundaries,
            )
            summary = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
            [path] = list((tmp_path / "data/services/qualification").rglob("*.json"))
            result = SimpleNamespace(
                record=QualificationRecord.model_validate_json(
                    path.read_text(encoding="utf-8")
                ),
                code=code,
                summary=summary,
            )
            return _Run(result, engine.snapshot(), switching, campus)
        request = _request(request_args(stage) + authorization_args(stage))
        try:
            result = qualify_server_services(
                request,
                boundaries,
                experimental_capabilities=frozenset(
                    definition.experimental_capabilities
                ),
            )
        except service_qualification.QualificationCancelled:
            [path] = list((tmp_path / "records").rglob("*.json"))
            result = SimpleNamespace(
                record=QualificationRecord.model_validate_json(
                    path.read_text(encoding="utf-8")
                ),
                cancelled=True,
            )
        return _Run(result, engine.snapshot(), switching, campus)
    finally:
        engine.close()


# -- the stage and its contract ---------------------------------------------------


def test_mixed_stage_binds_the_composed_fixture_and_budget():
    """The stage names exactly what the designer composes, within its ceiling."""
    definition = stage_definition(STAGE)
    contract = sp2_mixed_product_contract(BUILD, RUN_ID)

    assert QualificationStage.SP2_MIXED_PRODUCT in SP2_STAGES
    assert definition.executable and definition.allowed_channels == ("file",)
    assert definition.selected_clients == SP2_MIXED_CLIENTS
    assert len(SP2_MIXED_CLIENTS) == 11
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
    assert definition.planned_minimum_operations <= definition.budget.max_operations
    assert definition.budget.reserve_seconds == 420


def test_mixed_contract_candidates_stay_private():
    """The default catalog keeps its scope; only the contract carries candidates."""
    default = packet_tracer_service_capabilities(BUILD)
    contract = sp2_mixed_product_contract(BUILD, RUN_ID)
    relay = "Server-PT:dhcp_relay_named_pool_binding"
    native = "Server-PT:dhcp_native_default_binding"

    assert relay not in default
    assert default[native].native_policy_scope.network == "192.0.2.0"
    assert default[native].native_policy_scope.max_users == 2
    assert contract.service_capabilities[relay].source.startswith("candidate:")
    scope = contract.service_capabilities[native].native_policy_scope
    assert (scope.network, scope.max_users) == ("10.80.1.0", 5)
    assert {item["model"] for item in contract.device_capability_evidence} == {
        "1941",
        "2911",
    }
    assert all(
        item["verified"] is False and item["confidence"] == "candidate"
        for item in contract.device_capability_evidence
    )


def test_mixed_intent_is_bound_to_its_run():
    """Two runs differ only in the run-derived marker and host name."""
    first = json.loads(sp2_mixed_product_contract(BUILD, "run-a").intent_json)
    second = json.loads(sp2_mixed_product_contract(BUILD, "run-b").intent_json)
    assert first != second
    web = [
        service
        for site in first["sites"]
        for service in site.get("services", [])
        if service["service_type"] == "http"
    ]
    assert web and web[0]["http_content"].startswith("SP2_MIXED_")


# -- the positive trace -----------------------------------------------------------


def test_mixed_stage_verifies_every_client_in_its_pool_and_services(tmp_path):
    """Local clients join serverPool, branch clients their named pool; all serve."""
    run = _run(tmp_path)

    product = run.measurement("M-SP2-MIXED-PRODUCT")
    assert product.conclusion is MeasurementConclusion.SUPPORTED_IN_SAMPLE, (
        product.causes,
        run.record.primary_failure,
        product.facts.get("product_summary"),
    )
    clients = product.facts["clients"]
    assert set(clients) == set(SP2_MIXED_CLIENTS)
    for name, entry in clients.items():
        site = name.split("-")[0]
        assert entry["intended_pool"] == POOLS[site]
        assert entry["lease"]["effective_pool_name"] == POOLS[site], (name, entry)
        assert set(entry["checks"].values()) == {"verified"}, (name, entry)
    assert product.facts["entry_surface"] == "private_candidate"
    assert product.facts["product_device_catalog_injected"] is True
    assert (
        "private_candidate_capabilities_not_global_product_promotion"
        in product.limitations
    )
    phases = {
        (row["phase"], row["client_segment_id"], row["status"])
        for row in product.facts["routed_groups"]
    }
    assert phases == {
        ("dhcp_prelease", "br1-data", "admitted"),
        ("dhcp_prelease", "br2-data", "admitted"),
        ("", "br1-data", "admitted"),
        ("", "br2-data", "admitted"),
    }
    final = run.measurement("M-SP2-MIXED-FINAL")
    assert final.conclusion is MeasurementConclusion.SUPPORTED_IN_SAMPLE, final.facts
    assert set(final.facts["scans"]) == set(POOLS.values())
    assert run.record.restoration_proven
    assert run.snapshot["dhcp_runs"] == []
    print(
        f"\nSP2-MIXED product campus calls={run.switching.campus_calls} "
        f"engine calls={run.switching.engine_product_calls} "
        f"stage operations={run.record.budget.used_operations}"
    )
    assert (
        run.switching.campus_calls + run.switching.engine_product_calls
        <= SP2_MIXED_PRODUCT_OPERATIONS
    )
    assert run.record.budget.used_operations <= run.record.budget.max_operations
    assert SP2_MIXED_FINAL_OPERATIONS >= 3 * 2 * 12 + 3


def test_the_campaign_seals_the_product_record_the_mixed_record_cites(
    tmp_path, capsys, monkeypatch
):
    """Episode 8 left its product unsealed; the campaign must pin its bytes.

    The qualification record cites the product record in its product
    measurement. The campaign seals that exact file next to the record, so
    a later archive never depends on a stage-name list.
    """
    run = _run(tmp_path, monkeypatch=monkeypatch, campaign_episode=1, capsys=capsys)

    product = run.measurement("M-SP2-MIXED-PRODUCT")
    assert product.conclusion is MeasurementConclusion.SUPPORTED_IN_SAMPLE
    cited = Path(product.facts["product_record_path"])
    assert cited.is_file()
    assert run.result.summary["campaign"]["archive_findings"] == []
    store = ServerPtCommissioningStore(tmp_path, SP2_CAMPAIGN.campaign_id)
    assert store.external_source_registered(CAMPAIGN_ATTEMPT, "product-record")
    sealed = json.loads(
        (
            tmp_path
            / "data/commissioning"
            / SP2_CAMPAIGN.campaign_id
            / CAMPAIGN_ATTEMPT
            / "source-ref-product-record.json"
        ).read_text(encoding="utf-8")
    )
    raw = cited.read_bytes()
    assert sealed["path"] == cited.resolve().relative_to(tmp_path.resolve()).as_posix()
    assert sealed["sha256"] == hashlib.sha256(raw).hexdigest()
    assert sealed["bytes"] == len(raw)
    assert store.external_source_registered(CAMPAIGN_ATTEMPT, "qualification-record")
    assert store.verify_index() == ()


def test_an_unsealable_product_citation_stops_the_campaign_phase(
    tmp_path, capsys, monkeypatch
):
    """A citation the campaign cannot seal is a finding, never a silent skip."""

    def ambiguous(_record):
        raise ValueError("product_record_path_ambiguous")

    monkeypatch.setattr(service_qualification, "_native_product_record_path", ambiguous)
    run = _run(tmp_path, monkeypatch=monkeypatch, campaign_episode=1, capsys=capsys)

    campaign = run.result.summary["campaign"]
    assert "product_record_unsealed:ValueError" in campaign["archive_findings"]
    assert run.result.code != 0
    store = ServerPtCommissioningStore(tmp_path, SP2_CAMPAIGN.campaign_id)
    assert not store.external_source_registered(CAMPAIGN_ATTEMPT, "product-record")
    assert store.external_source_registered(CAMPAIGN_ATTEMPT, "qualification-record")
    status = store.load_phase_status(CAMPAIGN_ATTEMPT, "qualification")
    assert status["outcome"] == "stopped"


# -- controlled negatives ---------------------------------------------------------


def test_a_relayed_client_served_by_the_native_pool_is_not_supported(tmp_path):
    """A lease from the wrong physical pool never becomes intended-pool evidence."""
    pools = _client_pools()
    pools["BR2-DEFAULT-PC-02"] = "serverPool"

    run = _run(tmp_path, engine_config={"dhcp_client_pools": pools})

    product = run.measurement("M-SP2-MIXED-PRODUCT")
    assert product.conclusion is not MeasurementConclusion.SUPPORTED_IN_SAMPLE
    entry = product.facts["clients"]["BR2-DEFAULT-PC-02"]
    assert entry["checks"]["dhcp_lease"] != "verified"
    assert run.record.primary_failure == "sp2_mixed_product_not_verified"
    assert run.record.restoration_proven


def test_a_changed_intent_is_refused_before_any_product_effect(tmp_path):
    """Only the run's canonical intent may reach the product."""

    def changed(build, run_id):
        contract = sp2_mixed_product_contract(build, run_id)
        payload = json.loads(contract.intent_json)
        for site in payload["sites"]:
            for service in site.get("services", []):
                if service["service_type"] == "http":
                    service["http_content"] = "ANOTHER_RUN"
        return replace(contract, intent_json=json.dumps(payload, sort_keys=True))

    run = _run(tmp_path, contract_factory=changed)

    assert run.record.primary_failure == "sp2_mixed_intent_values_differ_from_run"
    assert run.switching.campus_calls == run.switching.engine_product_calls == 0
    assert run.record.restoration_proven


def test_an_extra_service_candidate_is_refused_before_any_product_effect(tmp_path):
    """The run may carry only the two named private service candidates."""

    def widened(build, run_id):
        contract = sp2_mixed_product_contract(build, run_id)
        records = dict(contract.service_capabilities)
        key = "PC-PT:https_fetch"
        records[key] = records[key].model_copy(
            update={"support": CapabilityStatus.SUPPORTED}
        )
        return replace(contract, service_capabilities=records)

    run = _run(tmp_path, contract_factory=widened)

    assert run.record.primary_failure == "sp2_mixed_service_candidates_changed"
    assert run.switching.campus_calls == run.switching.engine_product_calls == 0


def test_a_route_missing_from_e5_readback_stops_before_any_e6_effect(tmp_path):
    """An E5 contradiction leaves the server's DHCP process untouched."""

    def withhold(campus):
        campus.faults_after_service_apply = False
        campus.withheld_routes.add(("HQ-EDGE-RTR-01", "10.80.33.64"))

    run = _run(tmp_path, campus_config=withhold)

    product = run.measurement("M-SP2-MIXED-PRODUCT")
    assert product.conclusion is not MeasurementConclusion.SUPPORTED_IN_SAMPLE
    summary = product.facts["product_summary"]
    assert summary["refusal_code"] == "e5_contradiction", summary
    assert run.snapshot["dhcp_setter_calls"]["setStartIp"] == 0
    assert all(
        not server["enabled"] for server in run.snapshot["dhcp_servers"].values()
    )
    assert run.record.restoration_proven


def test_a_return_route_lost_after_e6_starts_blocks_only_the_far_branch(tmp_path):
    """A shared-path loss to BR2 blocks BR2's services, not HQ or BR1."""

    def withhold(campus):
        campus.withheld_routes.add(("HQ-EDGE-RTR-01", "10.80.33.64"))

    run = _run(tmp_path, campus_config=withhold)

    product = run.measurement("M-SP2-MIXED-PRODUCT")
    assert product.conclusion is not MeasurementConclusion.SUPPORTED_IN_SAMPLE
    clients = product.facts["clients"]
    for name in SP2_MIXED_SITE_CLIENTS["BR2"]:
        assert clients[name]["checks"]["http_fetch"] != "verified", clients[name]
    for name in (*SP2_MIXED_SITE_CLIENTS["HQ"], *SP2_MIXED_SITE_CLIENTS["BR1"]):
        assert set(clients[name]["checks"].values()) == {"verified"}, (
            name,
            clients[name],
        )
    assert any(
        row["client_segment_id"] == "br2-data" and row["status"] != "admitted"
        for row in product.facts["routed_groups"]
    ), product.facts["routed_groups"]
    final = run.measurement("M-SP2-MIXED-FINAL")
    assert final.facts["routers"], final.facts
    assert run.record.restoration_proven


# -- bounded stops -----------------------------------------------------------------


def test_a_smaller_grant_stops_the_product_and_keeps_terminal_and_cleanup(
    tmp_path, monkeypatch
):
    """Ordinary work stops at its cap; the terminal and owned cleanup still run."""
    run = _run(tmp_path, monkeypatch=monkeypatch, operation_ceiling=300)

    assert run.record.primary_failure
    assert run.record.budget.used_operations <= 300
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
    product = run.measurement("M-SP2-MIXED-PRODUCT")
    assert product.conclusion is not MeasurementConclusion.SUPPORTED_IN_SAMPLE
    # The product's own cap leaves the required terminal its allowance.
    final = run.measurement("M-SP2-MIXED-FINAL")
    assert final.status.value != "not_evaluated", final
    assert final.facts.get("routers"), final.facts
    assert run.record.restoration_proven


def test_a_cancellation_inside_the_product_is_recorded_and_cleaned_up(tmp_path):
    """An operator interrupt mid-product is a cancellation, not a result."""

    def cancel_at(number, _script):
        if number == 120:
            raise KeyboardInterrupt

    run = _run(tmp_path, before_call=cancel_at)

    assert run.record.primary_failure == "cancelled"
    assert getattr(run.result, "cancelled", False)
    product = run.measurement("M-SP2-MIXED-PRODUCT")
    assert product.conclusion is not MeasurementConclusion.SUPPORTED_IN_SAMPLE
    assert run.snapshot["devices"] == []
    assert run.record.restoration_proven


def test_an_unwritable_product_record_refuses_before_any_product_effect(tmp_path):
    """No record, no effect: the product refuses at its write-ahead step."""
    from packet_tracer_mcp.application.ports.service_run_record import (
        RunRecordPersistenceError,
    )
    from packet_tracer_mcp.infrastructure.persistence.service_run_record_store import (
        ServiceRunRecordStore,
    )

    class _Unwritable(ServiceRunRecordStore):
        def begin(self, record):
            raise RunRecordPersistenceError("disk full")

    run = _run(
        tmp_path,
        boundary_overrides={
            "native_product_record_store_factory": lambda: _Unwritable(
                tmp_path / "product-records"
            )
        },
    )

    product = run.measurement("M-SP2-MIXED-PRODUCT")
    assert product.conclusion is not MeasurementConclusion.SUPPORTED_IN_SAMPLE
    summary = product.facts["product_summary"]
    assert summary["refusal_code"] == "record_store_unwritable", summary
    # The terminal still reads the routers; nothing was configured anywhere.
    assert run.switching.engine_product_calls == 0
    assert all(not router.interfaces for router in run.campus.routers.values())
    assert not any(run.snapshot["dhcp_setter_calls"].values())
    assert run.record.restoration_proven


def test_a_failed_client_binding_read_keeps_the_terminal_inconclusive(tmp_path):
    """A row for every client is not an observation of every client."""

    def fail_one_port(script, outcome):
        if "gateway_reads:__gws" not in script or not outcome.body:
            return outcome
        payload = json.loads(outcome.body)
        row = next(
            item for item in payload["clients"] if item["device"] == "BR2-DEFAULT-PC-03"
        )
        row.update(port_found=False, ipv4="", netmask="", error="port lookup failed")
        return replace(outcome, body=json.dumps(payload))

    run = _run(tmp_path, rewrite=fail_one_port)

    assert (
        run.measurement("M-SP2-MIXED-PRODUCT").conclusion
        is MeasurementConclusion.SUPPORTED_IN_SAMPLE
    )
    final = run.measurement("M-SP2-MIXED-FINAL")
    rows = {row["device"]: row for row in final.facts["client_bindings"]}
    assert rows["BR2-DEFAULT-PC-03"]["port_found"] is False
    assert final.conclusion is MeasurementConclusion.INCONCLUSIVE, final.facts
    assert "sp2_mixed_final_inventory_incomplete" in final.causes


def test_a_pool_absent_at_the_terminal_scan_keeps_it_inconclusive(tmp_path):
    """An absent pool is a finding, not a completed scan of that pool."""

    def drop_pool(script, outcome):
        if "__req=" not in script or "getLeaseAt" not in script or not outcome.body:
            return outcome
        payload = json.loads(outcome.body)
        for entry in payload["pools"]:
            if entry["requested"] == "BR2_DATA":
                entry.update(found=False, name="", max=None, entries=[])
        return replace(outcome, body=json.dumps(payload))

    run = _run(tmp_path, rewrite=drop_pool)

    final = run.measurement("M-SP2-MIXED-FINAL")
    assert final.facts["scans"]["BR2_DATA"]["cause"] == "pool_absent"
    assert final.conclusion is MeasurementConclusion.INCONCLUSIVE, final.facts


def test_an_emptied_client_binding_keeps_the_terminal_inconclusive(tmp_path):
    """A readable row with no address is not a usable final binding."""

    def empty_one(script, outcome):
        if "gateway_reads:__gws" not in script or not outcome.body:
            return outcome
        payload = json.loads(outcome.body)
        for row in payload["clients"]:
            if row["device"] == "HQ-DEFAULT-PC-04":
                row.update(ipv4="", netmask="", dns_server="")
                for item in row["gateway_reads"]:
                    item["value"] = ""
        return replace(outcome, body=json.dumps(payload))

    run = _run(tmp_path, rewrite=empty_one)

    final = run.measurement("M-SP2-MIXED-FINAL")
    rows = {row["device"]: row for row in final.facts["client_bindings"]}
    assert rows["HQ-DEFAULT-PC-04"]["ipv4"] == ""
    assert final.conclusion is MeasurementConclusion.INCONCLUSIVE, final.facts


def test_ambiguous_terminal_router_identity_keeps_it_inconclusive(tmp_path):
    """A complete capture of an unproven router is not that router's table."""
    run = _run(tmp_path, ambiguous_terminal_routers=True)

    assert (
        run.measurement("M-SP2-MIXED-PRODUCT").conclusion
        is MeasurementConclusion.SUPPORTED_IN_SAMPLE
    )
    final = run.measurement("M-SP2-MIXED-FINAL")
    assert {row["device_identity_provenance"] for row in final.facts["routers"]} == {
        "ambiguous"
    }
    assert final.conclusion is MeasurementConclusion.INCONCLUSIVE, final.facts


def test_an_unreadable_terminal_pool_scan_keeps_it_inconclusive(tmp_path):
    """A found pool whose every index read failed is not a scanned pool."""

    def unreadable(script, outcome):
        if "__req=" not in script or "getLeaseAt" not in script or not outcome.body:
            return outcome
        payload = json.loads(outcome.body)
        for entry in payload["pools"]:
            if entry["requested"] == "BR1_DATA":
                for item in entry["entries"]:
                    item.update(return_kind="throw", error="read failed", row=None)
        return replace(outcome, body=json.dumps(payload))

    run = _run(tmp_path, rewrite=unreadable)

    final = run.measurement("M-SP2-MIXED-FINAL")
    assert final.facts["scans"]["BR1_DATA"]["rows"] == []
    assert final.conclusion is MeasurementConclusion.INCONCLUSIVE, final.facts


def _rewrite_final(bindings=None, scan=None):
    """Rewrite the terminal binding and lease-scan answers, nothing else."""

    def rewrite(script, outcome):
        if not outcome.body:
            return outcome
        payload = json.loads(outcome.body)
        if bindings and "gateway_reads:__gws" in script:
            bindings(payload)
        elif scan and "__req=" in script and "getLeaseAt" in script:
            scan(payload)
        else:
            return outcome
        return replace(outcome, body=json.dumps(payload))

    return rewrite


def _pool(payload, name):
    return next(item for item in payload["pools"] if item["requested"] == name)


def test_a_foreign_mac_on_a_client_address_keeps_the_terminal_inconclusive(
    tmp_path,
):
    """A row at a client's address with another MAC is not that client's lease."""

    def foreign(payload):
        _pool(payload, "BR1_DATA")["entries"][0]["row"]["macAddress"] = "0000.1111.2222"

    run = _run(tmp_path, rewrite=_rewrite_final(scan=foreign))

    final = run.measurement("M-SP2-MIXED-FINAL")
    assert final.conclusion is MeasurementConclusion.INCONCLUSIVE, final.facts


def test_a_duplicated_final_lease_keeps_the_terminal_inconclusive(tmp_path):
    """Two clients on one address and a repeated row are not two leases."""
    shared = {}

    def bindings(payload):
        rows = {row["device"]: row for row in payload["clients"]}
        shared["ip"] = rows["BR1-DEFAULT-PC-01"]["ipv4"]
        rows["BR1-DEFAULT-PC-02"]["ipv4"] = shared["ip"]

    def scan(payload):
        entries = _pool(payload, "BR1_DATA")["entries"]
        entries[1]["row"] = dict(entries[0]["row"])
        entries[1]["return_kind"] = "object"
        entries[1]["error"] = ""

    run = _run(tmp_path, rewrite=_rewrite_final(bindings=bindings, scan=scan))

    final = run.measurement("M-SP2-MIXED-FINAL")
    assert final.conclusion is MeasurementConclusion.INCONCLUSIVE, final.facts


def test_a_changed_service_value_is_refused_even_with_a_recomputed_hash(tmp_path):
    """The E6 plan is bound to its reviewed shape, not only to its own hash."""
    from packet_tracer_mcp.domain.enterprise.services.service_compiler import (
        ServiceCompiler,
    )

    def moved(build, run_id):
        contract = sp2_mixed_product_contract(build, run_id)
        plan = contract.service_plan.model_copy(deep=True)
        for action in plan.actions:
            if action.action_type.value == "add_dns_record":
                action.address = "10.80.1.99"
        plan.semantic_hash = ServiceCompiler._semantic_hash(plan)
        return replace(contract, service_plan=plan)

    run = _run(tmp_path, contract_factory=moved)

    assert run.record.primary_failure == "sp2_mixed_service_plan_changed"
    assert run.switching.campus_calls == run.switching.engine_product_calls == 0


def test_a_terminal_row_field_failure_is_not_a_table_end(tmp_path):
    """A last row whose field read fails is recorded apart from an index end."""
    run = _run(tmp_path, engine_config={"dhcp_lease_field_throws": "BR1_DATA"})

    final = run.measurement("M-SP2-MIXED-FINAL")
    entries = final.facts["scans"]["BR1_DATA"]["entries"]
    assert [item["return_kind"] for item in entries[:3]] == [
        "object",
        "object",
        "field_throw",
    ]
    assert final.conclusion is MeasurementConclusion.INCONCLUSIVE, final.facts


def test_a_client_out_of_dhcp_mode_keeps_the_terminal_inconclusive(tmp_path):
    """A final address held without DHCP mode is not a DHCP client's lease."""

    def static_mode(script, outcome):
        if "mode_type:__mt" not in script or not outcome.body:
            return outcome
        payload = json.loads(outcome.body)
        for row in payload["clients"]:
            if row["device"] == "BR2-DEFAULT-PC-01":
                row["mode"] = False
        return replace(outcome, body=json.dumps(payload))

    run = _run(tmp_path, rewrite=static_mode)

    final = run.measurement("M-SP2-MIXED-FINAL")
    assert final.facts["client_readings"]["BR2-DEFAULT-PC-01"]["mode"] is False
    assert final.conclusion is MeasurementConclusion.INCONCLUSIVE, final.facts
