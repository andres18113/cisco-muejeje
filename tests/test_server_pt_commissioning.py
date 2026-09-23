"""Commissioning starts from a maintained, parameterized campus intent."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from test_configuration_application import FakeConfigurationRuntime
from test_e95_physical_deployment_manifest import _double_port_inventory

from packet_tracer_mcp.application.use_cases.compose_enterprise_reference import (
    compose_enterprise_reference,
)
from packet_tracer_mcp.domain.enterprise.models.capabilities import CapabilityStatus
from packet_tracer_mcp.domain.enterprise.models.configuration_runtime import (
    ActionExecutionStatus,
    FieldVerificationStatus,
    RuntimeVerification,
)
from packet_tracer_mcp.domain.enterprise.models.deployment import EnvironmentFingerprint
from packet_tracer_mcp.domain.enterprise.models.execution import MutationDisposition
from packet_tracer_mcp.domain.enterprise.models.physical_deployment import (
    PhysicalDeviceObservation,
    PhysicalLinkObservation,
    PhysicalMutationResult,
    PhysicalObjectKind,
    PhysicalWorkspaceDeviceObservation,
    PhysicalWorkspaceObservation,
)
from packet_tracer_mcp.domain.enterprise.scenarios.server_pt_campus import (
    server_pt_campus_intent,
)
from packet_tracer_mcp.domain.models.plans import TopologyPlan


def _qualified_trunk_catalog():
    """Simulate a later measured capability without altering production data."""
    from packet_tracer_mcp.application.use_cases.plan_enterprise_hardware import (
        capability_catalog_for,
    )

    catalog = capability_catalog_for(BUILD)
    original = catalog.capabilities_for

    def observed(model, version=None):
        result = original(model, version)
        return (
            result.model_copy(update={"supports_trunk": CapabilityStatus.SUPPORTED})
            if model == "2950T-24" and result is not None
            else result
        )

    catalog.capabilities_for = observed
    return catalog


BUILD = "9.0.1.0858"
MARKER = "COLD_HTTP_0f1e2d3c4b5a69788796a5b4c3d2e1f0"


@pytest.mark.parametrize(("clients", "sites"), [(2, 1), (20, 1), (200, 1), (1000, 3)])
def test_maintained_campus_recipe_compiles_for_scale_cases(clients: int, sites: int):
    """The recipe, not a hand-built plan, reaches the real compiler."""
    intent = server_pt_campus_intent(clients, MARKER, sites=sites)
    composed = compose_enterprise_reference(intent, packet_tracer_version=BUILD)

    assert composed.valid, composed.issues
    assert composed.topology is not None
    assert len(intent.sites) == sites
    assert (
        sum(
            endpoint.count
            for site in intent.sites
            for endpoint in site.endpoints
            if endpoint.role == "user_pc"
        )
        == clients
    )
    if clients == 20:
        assert len(composed.topology.devices) == 25
        assert len(composed.topology.links) == 26


def test_live_recipe_keeps_the_reviewed_shape_and_marker():
    """The 30-client selection keeps the reviewed one-server campus shape."""
    intent = server_pt_campus_intent(30, MARKER)
    composed = compose_enterprise_reference(intent, packet_tracer_version=BUILD)

    assert composed.valid, composed.issues
    assert composed.topology is not None
    assert len(composed.topology.devices) == 35
    assert len(composed.topology.links) == 36
    assert [site.name for site in intent.sites] == ["HQ"]
    assert any(
        service.http_content == MARKER
        for service in intent.sites[0].services
        if service.service_type == "http"
    )


def test_export_contains_the_full_plan_and_dependency_closed_l2_setup():
    """E4 receives the persisted full plan; setup selects only trunk foundations."""
    from packet_tracer_mcp.application.use_cases.prepare_server_pt_commissioning import (
        prepare_server_pt_commissioning,
    )

    bundle = prepare_server_pt_commissioning(30, MARKER)
    plan = TopologyPlan.model_validate_json(bundle.topology_json)

    assert len(plan.devices) == 35
    assert len(plan.links) == 36
    assert (
        bundle.intent_sha256
        == hashlib.sha256(bundle.intent_json.encode("utf-8")).hexdigest()
    )
    assert (
        bundle.topology_sha256
        == hashlib.sha256(bundle.topology_json.encode("utf-8")).hexdigest()
    )
    assert bundle.physical_topology_hash == plan.physical_identity_hash
    assert len(bundle.configuration_semantic_hash) == 64
    assert bundle.setup_action_types == {
        "create_vlan": 4,
        "configure_trunk": 10,
    }


def test_maintained_recipe_prepares_the_exact_http_only_grant(tmp_path: Path):
    """The real product closure admits all 30 clients without a DNS effect."""
    from packet_tracer_mcp.application.use_cases.prepare_http_acceptance import (
        prepare_http_acceptance,
    )
    from packet_tracer_mcp.application.use_cases.prepare_server_pt_commissioning import (
        prepare_server_pt_commissioning,
    )
    from packet_tracer_mcp.domain.enterprise.models.configuration_runtime import (
        RuntimeConfigurationTarget,
    )
    from packet_tracer_mcp.domain.enterprise.models.deployment import (
        build_deployment_manifest,
    )
    from packet_tracer_mcp.domain.enterprise.models.service_run_record import (
        SourceTreeIdentity,
    )
    from packet_tracer_mcp.infrastructure.persistence.deployment_manifest_store import (
        DeploymentManifestStore,
    )

    bundle = prepare_server_pt_commissioning(30, MARKER)
    topology = TopologyPlan.model_validate_json(bundle.topology_json)
    inventory = [
        RuntimeConfigurationTarget(
            device_name=device.name,
            model=device.model,
            interfaces=sorted(
                {
                    port
                    for link in topology.links
                    for endpoint, port in (
                        (link.device_a_id, link.port_a),
                        (link.device_b_id, link.port_b),
                    )
                    if endpoint == device.id
                }
            ),
        )
        for device in topology.devices
    ]
    manifest = build_deployment_manifest(
        topology,
        inventory,
        fingerprint=EnvironmentFingerprint(
            backend="packet_tracer",
            backend_version=BUILD,
            bridge_transport="file",
            runtime_mode="logical-workspace",
        ),
        deployment_id="deploy-c31-01",
    )
    store = DeploymentManifestStore(tmp_path / "data" / "deployments")
    store.save_verified(manifest)

    prepared = prepare_http_acceptance(
        bundle.intent_json,
        deployment_id="deploy-c31-01",
        build=BUILD,
        marker=MARKER,
        manifest_store=store,
        source_tree=SourceTreeIdentity(sha="a" * 40, tree="b" * 40),
    )

    assert prepared.findings == ()
    assert prepared.scope is not None
    assert len(prepared.scope.clients) == 30
    assert prepared.scope.cost.max_operations == 7849
    assert prepared.scope.cost.max_seconds == 2792


def test_bundle_store_is_immutable_and_independent_of_current_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """E4's exact bytes reload from the declared root, not the process CWD."""
    from packet_tracer_mcp.application.use_cases.prepare_server_pt_commissioning import (
        prepare_server_pt_commissioning,
    )
    from packet_tracer_mcp.infrastructure.persistence.server_pt_commissioning_store import (
        ServerPtCommissioningStore,
    )

    root = tmp_path / "governed"
    root.mkdir()
    store = ServerPtCommissioningStore(root)
    bundle = prepare_server_pt_commissioning(30, MARKER)
    path = store.save_bundle("attempt-01", bundle)
    other = tmp_path / "elsewhere"
    other.mkdir()
    monkeypatch.chdir(other)

    reloaded = store.load_bundle("attempt-01")
    assert path.is_relative_to(root)
    assert reloaded == bundle
    assert store.intent_path_for(
        "attempt-01"
    ).read_bytes() == bundle.intent_json.encode("utf-8")
    assert store.topology_path_for(
        "attempt-01"
    ).read_bytes() == bundle.topology_json.encode("utf-8")
    assert TopologyPlan.model_validate_json(
        reloaded.topology_json
    ).physical_identity_hash == (bundle.physical_topology_hash)
    with pytest.raises(ValueError, match="already exists"):
        store.save_bundle("attempt-01", bundle)


def test_bundle_store_refuses_escaped_id_and_lost_input(tmp_path: Path):
    """An escaped attempt or altered full plan cannot authorize setup."""
    from packet_tracer_mcp.application.use_cases.prepare_server_pt_commissioning import (
        prepare_server_pt_commissioning,
    )
    from packet_tracer_mcp.infrastructure.persistence.server_pt_commissioning_store import (
        ServerPtCommissioningStore,
    )

    store = ServerPtCommissioningStore(tmp_path)
    bundle = prepare_server_pt_commissioning(30, MARKER)
    with pytest.raises(ValueError, match="safe"):
        store.save_bundle("../foreign", bundle)
    path = store.save_bundle("attempt-01", bundle)
    path.write_text(path.read_text(encoding="utf-8") + " ", encoding="utf-8")
    with pytest.raises(ValueError, match="bundle bytes changed"):
        store.load_bundle("attempt-01")


class _EmptyCampusPhysical:
    """Only the external PT device/link boundary is simulated for setup."""

    def __init__(self, topology: TopologyPlan, *, foreign: bool = False) -> None:
        self.topology = topology
        self.foreign = foreign
        self.created: set[str] = set()
        self.linked: set[str] = set()
        self.effects: list[str] = []

    def observe_workspace(self):
        devices = (
            [PhysicalWorkspaceDeviceObservation(name="Foreign", model="PC-PT")]
            if self.foreign
            else []
        )
        return PhysicalWorkspaceObservation(devices=devices)

    def ensure_device(self, device):
        self.effects.append(f"device:{device.name}")
        self.created.add(device.id)
        return PhysicalMutationResult(
            target_id=device.id,
            target_kind=PhysicalObjectKind.DEVICE,
            disposition=MutationDisposition.CHANGED,
            applied=True,
            inverse_available=True,
            inverse_action_id=f"remove-device:{device.id}",
        )

    def observe_device(self, device):
        ports = sorted(
            {
                port
                for link in self.topology.links
                for endpoint, port in (
                    (link.device_a_id, link.port_a),
                    (link.device_b_id, link.port_b),
                )
                if endpoint == device.id
            }
        )
        return PhysicalDeviceObservation(
            target_id=device.id,
            observed=device.id in self.created,
            deployed_name=device.name,
            model=device.model,
            interfaces=ports,
        )

    def ensure_link(self, link):
        self.effects.append(f"link:{link.id}")
        self.linked.add(link.id)
        return PhysicalMutationResult(
            target_id=link.id,
            target_kind=PhysicalObjectKind.LINK,
            disposition=MutationDisposition.CHANGED,
            applied=True,
            inverse_available=True,
            inverse_action_id=f"remove-link:{link.id}",
        )

    def observe_link(self, link):
        names = {device.id: device.name for device in self.topology.devices}
        return PhysicalLinkObservation(
            target_id=link.id,
            observed=link.id in self.linked,
            device_a=names[link.device_a_id],
            port_a=link.port_a,
            device_b=names[link.device_b_id],
            port_b=link.port_b,
        )

    def module_effect_capability(self, *_args):
        raise AssertionError("the campus requires no modules")

    ensure_module = module_effect_capability
    observe_module_effect = module_effect_capability


class _BlockedRedundantTrunkConfiguration(FakeConfigurationRuntime):
    """Return genuine structural fields while one redundant edge is blocked."""

    def verify(self, expectations):
        rows = super().verify(expectations)
        for index, expectation in enumerate(expectations):
            if expectation.kind.value != "trunk":
                continue
            fields = dict(rows[index].fields)
            fields.update(
                {
                    "status": FieldVerificationStatus.VERIFIED,
                    "active_vlans": FieldVerificationStatus.VERIFIED,
                    "forwarding_vlans": FieldVerificationStatus.FAILED,
                }
            )
            rows[index] = RuntimeVerification(
                expectation_id=expectation.id,
                status=ActionExecutionStatus.FAILED,
                evidence_method="simulated_ios_trunk_readback",
                fresh_evidence=True,
                fields=fields,
            )
        return rows


def test_setup_from_empty_workspace_persists_full_e4_e5_and_manifest(tmp_path: Path):
    """A blocked redundant STP edge does not erase proven trunk structure."""
    from packet_tracer_mcp.application.use_cases.prepare_server_pt_commissioning import (
        prepare_server_pt_commissioning,
    )
    from packet_tracer_mcp.application.use_cases.setup_server_pt_commissioning import (
        run_server_pt_setup,
    )
    from packet_tracer_mcp.infrastructure.persistence.server_pt_commissioning_store import (
        ServerPtCommissioningStore,
    )

    store = ServerPtCommissioningStore(tmp_path)
    bundle = prepare_server_pt_commissioning(30, MARKER)
    store.save_bundle("attempt-01", bundle)
    topology = TopologyPlan.model_validate_json(bundle.topology_json)
    physical = _EmptyCampusPhysical(topology)
    configuration = _BlockedRedundantTrunkConfiguration(topology)

    result = run_server_pt_setup(
        "attempt-01",
        deployment_id="deploy-c31-01",
        store=store,
        physical_runtime=physical,
        configuration_runtime=configuration,
        environment_fingerprint=EnvironmentFingerprint(
            backend="packet_tracer",
            backend_version=BUILD,
            bridge_transport="file",
            runtime_mode="logical-workspace",
        ),
        admission=lambda: (),
        port_inventory=_double_port_inventory(topology),
        capability_catalog=_qualified_trunk_catalog(),
    )

    assert result.ready is True, result.reason
    assert len(physical.created) == 35
    assert len(physical.linked) == 36
    assert set(result.configuration.mutation_action_ids) == set(bundle.setup_action_ids)
    assert result.physical.manifest is not None
    assert store.load_e4("attempt-01") == result.physical
    assert store.load_e5("attempt-01") == result.configuration
    assert store.load_baseline("attempt-01").safe_for_disposable_mutation
    assert not (tmp_path / "data" / "services").exists()


def test_setup_refuses_foreign_workspace_before_effect(tmp_path: Path):
    """The first E4 mutation is unreachable from a nonempty workspace."""
    from packet_tracer_mcp.application.use_cases.prepare_server_pt_commissioning import (
        prepare_server_pt_commissioning,
    )
    from packet_tracer_mcp.application.use_cases.setup_server_pt_commissioning import (
        run_server_pt_setup,
    )
    from packet_tracer_mcp.infrastructure.persistence.server_pt_commissioning_store import (
        ServerPtCommissioningStore,
    )

    store = ServerPtCommissioningStore(tmp_path)
    bundle = prepare_server_pt_commissioning(30, MARKER)
    store.save_bundle("attempt-01", bundle)
    topology = TopologyPlan.model_validate_json(bundle.topology_json)
    physical = _EmptyCampusPhysical(topology, foreign=True)

    result = run_server_pt_setup(
        "attempt-01",
        deployment_id="deploy-c31-01",
        store=store,
        physical_runtime=physical,
        configuration_runtime=_BlockedRedundantTrunkConfiguration(topology),
        environment_fingerprint=EnvironmentFingerprint(
            backend="packet_tracer",
            backend_version=BUILD,
            bridge_transport="file",
            runtime_mode="logical-workspace",
        ),
        admission=lambda: (),
        port_inventory=_double_port_inventory(topology),
        capability_catalog=_qualified_trunk_catalog(),
    )

    assert result.ready is False
    assert "not empty" in result.reason
    assert physical.effects == []


def _setup_case(tmp_path: Path):
    from packet_tracer_mcp.application.use_cases.prepare_server_pt_commissioning import (
        prepare_server_pt_commissioning,
    )
    from packet_tracer_mcp.infrastructure.persistence.server_pt_commissioning_store import (
        ServerPtCommissioningStore,
    )

    store = ServerPtCommissioningStore(tmp_path)
    bundle = prepare_server_pt_commissioning(30, MARKER)
    store.save_bundle("attempt-01", bundle)
    topology = TopologyPlan.model_validate_json(bundle.topology_json)
    physical = _EmptyCampusPhysical(topology)
    configuration = _BlockedRedundantTrunkConfiguration(topology)
    fingerprint = EnvironmentFingerprint(
        backend="packet_tracer",
        backend_version=BUILD,
        bridge_transport="file",
        runtime_mode="logical-workspace",
    )
    return store, bundle, topology, physical, configuration, fingerprint


def test_real_catalog_refuses_the_unmeasured_server_port_before_effect(tmp_path: Path):
    """The known Server-PT catalog gap remains a hard E4 preflight failure."""
    from packet_tracer_mcp.application.use_cases.setup_server_pt_commissioning import (
        run_server_pt_setup,
    )

    store, _, _, physical, configuration, fingerprint = _setup_case(tmp_path)
    result = run_server_pt_setup(
        "attempt-01",
        deployment_id="deploy-c31-01",
        store=store,
        physical_runtime=physical,
        configuration_runtime=configuration,
        environment_fingerprint=fingerprint,
        admission=lambda: (),
    )

    assert result.ready is False
    assert (
        "No backend-verified port inventory exists for model 'Server-PT'"
        in result.reason
    )
    assert physical.effects == []
    assert store.load_e4("attempt-01") == result.physical


@pytest.mark.parametrize("deployment_id", ["", "../foreign", "deploy/foreign"])
def test_setup_refuses_unsafe_deployment_identity_before_effect(
    tmp_path: Path, deployment_id: str
):
    """A slash or missing deployment ID is refused before E4 dispatch."""
    from packet_tracer_mcp.application.use_cases.setup_server_pt_commissioning import (
        run_server_pt_setup,
    )

    store, _, topology, physical, configuration, fingerprint = _setup_case(tmp_path)
    result = run_server_pt_setup(
        "attempt-01",
        deployment_id=deployment_id,
        store=store,
        physical_runtime=physical,
        configuration_runtime=configuration,
        environment_fingerprint=fingerprint,
        admission=lambda: (),
        port_inventory=_double_port_inventory(topology),
        capability_catalog=_qualified_trunk_catalog(),
    )

    assert result.reason == "unsafe_deployment_id"
    assert physical.effects == []


def test_receiver_loss_after_e4_blocks_e5_and_keeps_e4(tmp_path: Path):
    """A fresh denial between phases cannot dispatch any configuration."""
    from packet_tracer_mcp.application.use_cases.setup_server_pt_commissioning import (
        run_server_pt_setup,
    )

    store, _, topology, physical, configuration, fingerprint = _setup_case(tmp_path)
    calls = 0

    def admission():
        nonlocal calls
        calls += 1
        return () if calls == 1 else ("receiver_lost",)

    result = run_server_pt_setup(
        "attempt-01",
        deployment_id="deploy-c31-01",
        store=store,
        physical_runtime=physical,
        configuration_runtime=configuration,
        environment_fingerprint=fingerprint,
        admission=admission,
        port_inventory=_double_port_inventory(topology),
        capability_catalog=_qualified_trunk_catalog(),
    )

    assert result.reason == "setup_admission:receiver_lost"
    assert store.load_e4("attempt-01") == result.physical
    assert configuration.apply_calls == []


def test_lost_e4_persistence_blocks_e5(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """A physical effect without a durable full E4 result stops the chain."""
    from packet_tracer_mcp.application.use_cases.setup_server_pt_commissioning import (
        run_server_pt_setup,
    )

    store, _, topology, physical, configuration, fingerprint = _setup_case(tmp_path)

    def lost(*_args):
        raise OSError("controlled loss")

    monkeypatch.setattr(store, "save_e4", lost)
    result = run_server_pt_setup(
        "attempt-01",
        deployment_id="deploy-c31-01",
        store=store,
        physical_runtime=physical,
        configuration_runtime=configuration,
        environment_fingerprint=fingerprint,
        admission=lambda: (),
        port_inventory=_double_port_inventory(topology),
        capability_catalog=_qualified_trunk_catalog(),
    )

    assert result.reason == "e4_persistence_failed:OSError"
    assert physical.effects
    assert configuration.apply_calls == []


def test_baseline_persistence_loss_blocks_all_physical_effects(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """A baseline that cannot be retained cannot authorize E4 creation."""
    from packet_tracer_mcp.application.use_cases.setup_server_pt_commissioning import (
        run_server_pt_setup,
    )

    store, _, topology, physical, configuration, fingerprint = _setup_case(tmp_path)

    def lost(*_args):
        raise OSError("controlled baseline loss")

    monkeypatch.setattr(store, "save_baseline", lost, raising=False)
    result = run_server_pt_setup(
        "attempt-01",
        deployment_id="deploy-c31-01",
        store=store,
        physical_runtime=physical,
        configuration_runtime=configuration,
        environment_fingerprint=fingerprint,
        admission=lambda: (),
        port_inventory=_double_port_inventory(topology),
        capability_catalog=_qualified_trunk_catalog(),
    )

    assert result.reason == "baseline_persistence_failed:OSError"
    assert physical.effects == []
    assert configuration.apply_calls == []


def test_typed_manifest_persistence_error_has_a_named_exit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """The store's typed failure preserves E4 and blocks E5."""
    from packet_tracer_mcp.application.use_cases.setup_server_pt_commissioning import (
        run_server_pt_setup,
    )
    from packet_tracer_mcp.infrastructure.persistence.deployment_manifest_store import (
        DeploymentManifestStore,
        ManifestPersistenceError,
    )

    store, _, topology, physical, configuration, fingerprint = _setup_case(tmp_path)

    def unavailable(*_args):
        raise ManifestPersistenceError("controlled disk loss")

    monkeypatch.setattr(DeploymentManifestStore, "save_verified", unavailable)
    result = run_server_pt_setup(
        "attempt-01",
        deployment_id="deploy-c31-01",
        store=store,
        physical_runtime=physical,
        configuration_runtime=configuration,
        environment_fingerprint=fingerprint,
        admission=lambda: (),
        port_inventory=_double_port_inventory(topology),
        capability_catalog=_qualified_trunk_catalog(),
    )

    assert result.reason == "manifest_persistence_failed:ManifestPersistenceError"
    assert store.load_e4("attempt-01") == result.physical
    assert configuration.apply_calls == []


def test_contradicted_l2_field_blocks_setup(tmp_path: Path):
    """An observed VLAN mismatch is not excused as redundant STP blocking."""
    from packet_tracer_mcp.application.use_cases.setup_server_pt_commissioning import (
        run_server_pt_setup,
    )

    store, _, topology, physical, configuration, fingerprint = _setup_case(tmp_path)
    original = configuration.verify

    def contradicted(expectations):
        rows = original(expectations)
        for row in rows:
            if "vlan_id" in row.fields:
                row.fields["vlan_id"] = FieldVerificationStatus.FAILED
                row.status = ActionExecutionStatus.FAILED
                break
        return rows

    configuration.verify = contradicted
    result = run_server_pt_setup(
        "attempt-01",
        deployment_id="deploy-c31-01",
        store=store,
        physical_runtime=physical,
        configuration_runtime=configuration,
        environment_fingerprint=fingerprint,
        admission=lambda: (),
        port_inventory=_double_port_inventory(topology),
        capability_catalog=_qualified_trunk_catalog(),
    )

    assert result.ready is False
    assert "setup_structure_not_verified" in result.reason
    assert store.load_e5("attempt-01") == result.configuration


def test_unknown_l2_mutation_outcome_blocks_setup(tmp_path: Path):
    """An unobserved setter outcome cannot become a verified foundation."""
    from packet_tracer_mcp.application.use_cases.setup_server_pt_commissioning import (
        run_server_pt_setup,
    )

    store, _, topology, physical, configuration, fingerprint = _setup_case(tmp_path)
    original = configuration.apply_actions

    def unknown(actions):
        rows = original(actions)
        if rows:
            rows[0].applied = False
            rows[0].disposition = MutationDisposition.UNKNOWN
        return rows

    configuration.apply_actions = unknown
    result = run_server_pt_setup(
        "attempt-01",
        deployment_id="deploy-c31-01",
        store=store,
        physical_runtime=physical,
        configuration_runtime=configuration,
        environment_fingerprint=fingerprint,
        admission=lambda: (),
        port_inventory=_double_port_inventory(topology),
        capability_catalog=_qualified_trunk_catalog(),
    )

    assert result.ready is False
    assert "setup_action_not_applied" in result.reason
    assert store.load_e5("attempt-01") == result.configuration


def test_resealed_out_of_scope_action_is_refused_before_e4(tmp_path: Path):
    """A matching outer digest cannot expand the compiled setup selection."""
    from packet_tracer_mcp.application.use_cases.setup_server_pt_commissioning import (
        run_server_pt_setup,
    )

    store, _, topology, physical, configuration, fingerprint = _setup_case(tmp_path)
    path = store.bundle_path_for("attempt-01")
    data = json.loads(path.read_text(encoding="utf-8"))
    data["setup_action_ids"] = ["cfg/outside-charter"]
    raw = (json.dumps(data) + "\n").encode("utf-8")
    path.write_bytes(raw)
    path.with_name("bundle.sha256").write_text(
        hashlib.sha256(raw).hexdigest() + "\n", encoding="ascii"
    )

    result = run_server_pt_setup(
        "attempt-01",
        deployment_id="deploy-c31-01",
        store=store,
        physical_runtime=physical,
        configuration_runtime=configuration,
        environment_fingerprint=fingerprint,
        admission=lambda: (),
        port_inventory=_double_port_inventory(topology),
        capability_catalog=_qualified_trunk_catalog(),
    )

    assert result.reason == "setup_input_unavailable:ValueError"
    assert physical.effects == []


def test_live_prepare_refuses_a_planner_shape_change(monkeypatch: pytest.MonkeyPatch):
    """An extra device cannot be advertised as the reviewed 35-device campus."""
    from importlib import import_module

    module = import_module(
        "packet_tracer_mcp.application.use_cases.prepare_server_pt_commissioning"
    )
    original = module.compose_enterprise_reference

    def extra_device(*args, **kwargs):
        composition = original(*args, **kwargs)
        first = composition.topology.devices[0]
        composition.topology.devices.append(
            first.model_copy(update={"id": "extra-device", "name": "EXTRA-DEVICE"})
        )
        return composition

    monkeypatch.setattr(module, "compose_enterprise_reference", extra_device)
    with pytest.raises(ValueError, match="reviewed campaign shape changed"):
        module.prepare_server_pt_commissioning(30, MARKER)


def test_live_prepare_refuses_a_transit_vlan_change(monkeypatch: pytest.MonkeyPatch):
    """A compiled setup VLAN other than 10 is outside the charter."""
    from importlib import import_module

    module = import_module(
        "packet_tracer_mcp.application.use_cases.prepare_server_pt_commissioning"
    )
    original = module.compile_enterprise_configuration

    def wrong_vlan(*args, **kwargs):
        compiled = original(*args, **kwargs)
        for action in compiled.plan.actions:
            if action.action_type.value == "create_vlan":
                action.vlan_id = 20
        return compiled

    monkeypatch.setattr(module, "compile_enterprise_configuration", wrong_vlan)
    with pytest.raises(ValueError, match="reviewed campaign shape changed"):
        module.prepare_server_pt_commissioning(30, MARKER)
