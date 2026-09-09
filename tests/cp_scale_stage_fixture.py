"""Small noncanonical topology with real E5/E9/Voice applicators, no PT I/O."""

from __future__ import annotations

from types import SimpleNamespace

from src.packet_tracer_mcp.application.cp_scale_live.configuration_stage import CPScaleConfigurationStage
from src.packet_tracer_mcp.application.cp_scale_live.control_plane_stage import CPScaleControlPlaneStage
from src.packet_tracer_mcp.application.cp_scale_live.contracts import CPScaleStageExecutionInput
from src.packet_tracer_mcp.application.cp_scale_live.forwarding_stage import CPScaleForwardingStage
from src.packet_tracer_mcp.application.cp_scale_live.reconciliation import CPScaleReconciliation
from src.packet_tracer_mcp.application.cp_scale_live.voice_stage import CPScaleVoiceStage
from src.packet_tracer_mcp.application.use_cases.apply_configuration import ConfigurationApplicator
from src.packet_tracer_mcp.application.use_cases.apply_control_plane import ControlPlaneApplicator
from src.packet_tracer_mcp.application.use_cases.apply_voice import VoiceApplicator
from src.packet_tracer_mcp.application.use_cases.compose_cp_scale_canonical import CPScaleCanonicalStage, CPScaleCanonicalStageProjection
from src.packet_tracer_mcp.application.use_cases.compose_enterprise_reference import EnterpriseReferenceComposition
from src.packet_tracer_mcp.application.use_cases.observe_serial_orientation import SerialOrientationObserver
from src.packet_tracer_mcp.domain.enterprise.models.capabilities import DeviceCapabilities
from src.packet_tracer_mcp.domain.enterprise.models.configuration import ConfigurationPlan, ConfigurationPhase, ConfigureHostname, VerificationExpectation, VerificationKind
from src.packet_tracer_mcp.domain.enterprise.models.configuration_runtime import ActionExecutionStatus, ConfigurationApplicationStatus, RuntimeConfigurationTarget, RuntimeActionMutation, RuntimeVerification
from src.packet_tracer_mcp.domain.enterprise.models.control_plane import ControlPlanePlan, ControlPlaneCapabilityProfile
from src.packet_tracer_mcp.domain.enterprise.models.control_plane_runtime import RuntimeControlPlaneVerification, ControlPlaneExecutionStage
from tests.test_control_plane_application import _routing_plan
from src.packet_tracer_mcp.domain.enterprise.models.deployment import EnvironmentFingerprint, DeploymentManifest, DeploymentBinding, deployment_manifest_semantic_hash
from src.packet_tracer_mcp.domain.enterprise.models.execution import ApplicationExecutionJournal
from src.packet_tracer_mcp.domain.enterprise.models.physical_deployment import PhysicalDeploymentResult, PhysicalDeploymentStatus, PhysicalWorkspaceObservation, PhysicalWorkspaceDeviceObservation
from src.packet_tracer_mcp.domain.models.plans import DevicePlan, TopologyPlan


def stage_fixture(executor_type, *, partial=False, unobservable=False, reread=False, omit_journal=False):
    trace = []
    configuration_results = []
    control_results = []
    workspaces = []
    topology = TopologyPlan(id="synthetic", semantic_hash="synthetic-physical", devices=[
        DevicePlan(id="r", name="R", model="2911", category="router"),
    ])
    config = ConfigurationPlan(
        id="c", semantic_hash="synthetic-configuration", source_topology_id="synthetic",
        source_topology_hash="synthetic-physical", actions=[ConfigureHostname(
            id="hostname", phase=ConfigurationPhase.IDENTITY, device_id="r", device_name="R",
            site_id="lab", hostname="R",
        )], verification_expectations=[VerificationExpectation(
            id="read-hostname", action_id="hostname", kind=VerificationKind.HOSTNAME,
            device_id="r", device_name="R", expected={"hostname": "R"},
        )],
    )
    control = ControlPlanePlan(
        id="cp", source_topology_id=topology.id, source_topology_hash="synthetic-physical",
        source_configuration_id=config.id, source_configuration_hash=config.semantic_hash,
        semantic_hash="synthetic-control",
    )
    routing = _routing_plan()
    for action in routing.actions:
        action.device_id = "r"
        action.device_name = "R"
    for expectation in routing.verification_expectations:
        expectation.device_id = "r"
        if expectation.peer_device_id:
            expectation.peer_device_id = "r"
    control.actions = routing.actions
    control.verification_expectations = routing.verification_expectations
    projection = CPScaleCanonicalStageProjection(CPScaleCanonicalStage.ROUTING_CORE, topology, config, control, {})
    fingerprint = EnvironmentFingerprint()
    manifest = DeploymentManifest(
        deployment_id="synthetic-session", physical_topology_hash="synthetic-physical",
        bindings=[DeploymentBinding(semantic_device_id="r", deployed_name="R", model="2911")],
    )
    manifest.semantic_hash = deployment_manifest_semantic_hash(manifest)
    deployment = PhysicalDeploymentResult(
        topology_id=topology.id, physical_topology_hash="synthetic-physical",
        deployment_id=manifest.deployment_id, environment_fingerprint=fingerprint,
        status=PhysicalDeploymentStatus.VERIFIED, manifest=manifest,
        execution_journal=ApplicationExecutionJournal(plan_id=topology.id),
    )

    class Runtime:
        def __init__(self):
            self.apply_calls = []
            self.reads = 0

        def inventory(self):
            return [RuntimeConfigurationTarget(device_name="R", model="2911")]

        def apply_actions(self, actions):
            self.apply_calls.append([item.id for item in actions])
            return [RuntimeActionMutation(action_id=item.id, applied=True) for item in actions]

        def verify(self, expectations):
            self.reads += 1
            status = ActionExecutionStatus.VERIFIED
            if partial:
                status = ActionExecutionStatus.PARTIAL
            if unobservable or (reread and self.reads == 1):
                status = ActionExecutionStatus.UNOBSERVABLE
            return [RuntimeVerification(
                expectation_id=item.id, status=status, fresh_evidence=status is ActionExecutionStatus.VERIFIED,
                evidence_method="synthetic_readback",
            ) for item in expectations]

    runtime = Runtime()

    class Configuration(ConfigurationApplicator):
        def apply(self, *args, **kwargs):
            if not configuration_results:
                trace.append("configuration")
            result = super().apply(*args, **kwargs)
            if omit_journal:
                result = result.model_copy(update={"execution_journal": None})
            configuration_results.append(result)
            return result

    class Control(ControlPlaneApplicator):
        def apply(self, *args, **kwargs):
            trace.append("control_plane")
            result = super().apply(*args, **kwargs)
            control_results.append(result)
            return result

    class ControlRuntime(Runtime):
        def verify(self, expectations):
            return [RuntimeControlPlaneVerification(
                expectation_id=item.id,
                stage=(ControlPlaneExecutionStage.BEHAVIOR if item.kind.value == "end_to_end_reachability" else ControlPlaneExecutionStage.OBSERVED),
                status=ActionExecutionStatus.VERIFIED, fresh_evidence=True,
                evidence_method="synthetic_routing_readback",
            ) for item in expectations]

    class Voice(CPScaleVoiceStage):
        def apply(self, *args, **kwargs):
            trace.append("voice")
            return super().apply(*args, **kwargs)

    class Observations:
        def network_state(self, projection, *, boundary):
            if boundary == "after_physical_delta":
                trace.append("physical_delta")
            return {"boundary": boundary, "status": "observed"}

        def serial_orientation(self, projection, manifest, *retained):
            return SerialOrientationObserver(None).observe(projection.topology, manifest)

        def serial_interfaces(self, projection):
            return True, []

        def stp(self, projection, *, edge):
            return {"edge": edge}

        def core_forwarding(self, checks):
            trace.append("forwarding")
            return ()

        def workspace(self):
            trace.append("workspace")
            value = PhysicalWorkspaceObservation(devices=[PhysicalWorkspaceDeviceObservation(name="R", model="2911")])
            workspaces.append(value)
            return value

    class Reconciliation(CPScaleReconciliation):
        def execute(self, topology):
            trace.append("reconciliation")
            return super().execute(topology)

    observations = Observations()

    def acceptance(plan, result, **kwargs):
        if result.status is ConfigurationApplicationStatus.VERIFIED:
            return ""
        if partial and result.status is ConfigurationApplicationStatus.PARTIAL:
            return ""
        return "Synthetic required readback was unobservable"

    configuration = CPScaleConfigurationStage(
        Configuration(runtime), serial_wait=observations.serial_interfaces,
        acceptance_policy=acceptance, retry_policy=lambda *args, **kwargs: reread,
    )
    executor = executor_type(
        configuration=configuration, voice=Voice(VoiceApplicator(None), None),
        control_plane=CPScaleControlPlaneStage(Control(ControlRuntime()), {"2911": ControlPlaneCapabilityProfile.supported("2911")}),
        observations=observations, diagnostics=None,
        forwarding=CPScaleForwardingStage(observations), reconciliation=Reconciliation(observations),
    )
    request = CPScaleStageExecutionInput(
        projection, EnterpriseReferenceComposition(capabilities={"2911": DeviceCapabilities(model="2911", category="router")}),
        deployment, None, fingerprint, "synthetic",
    )
    return SimpleNamespace(
        executor=executor, request=request, trace=trace,
        configuration_results=configuration_results, control_results=control_results,
        configuration_runtime=runtime, workspaces=workspaces,
    )


def voice_window_trace(*, after_simulating=False, diagnostic_raises=False):
    from dataclasses import replace
    from src.packet_tracer_mcp.application.cp_scale_live.stage_executor import CPScaleStageExecutor
    from src.packet_tracer_mcp.application.cp_scale_live.contracts import CPScaleVoiceStageResult, CPScaleDiagnosticRecord
    from src.packet_tracer_mcp.domain.enterprise.models.voice_plan import VoicePlan
    from tests.test_voice_runtime import _compile

    fixture = stage_fixture(CPScaleStageExecutor)
    fixture.request = replace(fixture.request, projection=replace(
        fixture.request.projection, voice=_compile().plan,
    ))
    trace = []
    states = iter([False, after_simulating])
    def read():
        trace.append("before" if "before" not in trace else "after")
        return {"observed": True, "simulation_mode": next(states)}
    fixture.executor.observations.voice_window_state = read
    fixture.executor.observations.stp = lambda projection, edge: trace.append("stp_" + edge) or {}
    fixture.executor.observations.bindings = lambda projection: trace.append("bindings") or []
    fixture.executor.voice.apply = lambda *args, **kwargs: trace.append("voice") or CPScaleVoiceStageResult(None, True, error="primary voice contradiction")
    def diagnose(request):
        trace.append("diagnostic")
        if diagnostic_raises:
            raise RuntimeError("secondary diagnostic failure")
        return CPScaleDiagnosticRecord(request.projection.stage, {"status": "diagnostic"})
    fixture.executor.diagnostics = SimpleNamespace(diagnose=diagnose)
    return fixture.executor.execute(fixture.request), trace
