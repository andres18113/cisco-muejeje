"""Stage 3A4: fresh serial-controller evidence orients a deployment manifest."""

from __future__ import annotations

import json

import pytest

from src.packet_tracer_mcp.application.use_cases.observe_serial_orientation import (
    SerialControllerObservation,
    SerialOrientationObserver,
    SerialOrientationStatus,
)
from src.packet_tracer_mcp.domain.enterprise.models.configuration_runtime import (
    RuntimeConfigurationTarget,
)
from src.packet_tracer_mcp.domain.enterprise.models.deployment import (
    DeploymentLinkBinding,
    DeploymentLinkEndpoint,
    EnvironmentFingerprint,
    SerialEndpointOrientation,
    build_deployment_manifest,
)
from src.packet_tracer_mcp.domain.enterprise.services.topology_identity import (
    stamp_topology_hashes,
)
from src.packet_tracer_mcp.domain.models.plans import DevicePlan, LinkPlan, TopologyPlan
from src.packet_tracer_mcp.infrastructure.execution.ios_terminal import (
    ControlledIosExecutor,
    IosCommandResult,
    OperationalQueryId,
)
from src.packet_tracer_mcp.infrastructure.execution.serial_orientation_runtime import (
    PacketTracerSerialOrientationRuntime,
)


def _topology() -> TopologyPlan:
    topology = TopologyPlan(
        id="e4/serial-orientation",
        devices=[
            DevicePlan(id="r1", name="MCP-R1", model="2911", category="router"),
            DevicePlan(id="r2", name="MCP-R2", model="2911", category="router"),
        ],
        links=[
            LinkPlan(
                id="link/wan/r1-r2",
                device_a_id="r1",
                device_a="MCP-R1",
                port_a="Serial0/0/0",
                device_b_id="r2",
                device_b="MCP-R2",
                port_b="Serial0/0/0",
                cable="serial",
                link_role="wan_link",
            ),
        ],
    )
    stamp_topology_hashes(topology)
    return topology


def _manifest(topology: TopologyPlan):
    return build_deployment_manifest(
        topology,
        [
            RuntimeConfigurationTarget(
                device_name="MCP-R1", model="2911", interfaces=["Serial0/0/0"],
            ),
            RuntimeConfigurationTarget(
                device_name="MCP-R2", model="2911", interfaces=["Serial0/0/0"],
            ),
        ],
        fingerprint=EnvironmentFingerprint(
            backend="packet_tracer",
            backend_version="9.0.1.0858",
            bridge_transport="file",
        ),
        deployment_id="deployment/serial-orientation",
        link_bindings=[DeploymentLinkBinding(
            semantic_link_id="link/wan/r1-r2",
            endpoint_a=DeploymentLinkEndpoint(
                semantic_device_id="r1", interface="Serial0/0/0",
            ),
            endpoint_b=DeploymentLinkEndpoint(
                semantic_device_id="r2", interface="Serial0/0/0",
            ),
            runtime_link_identifier="runtime-link-1",
            runtime_link_identity_observed=True,
        )],
    )


def _observation(
    device_name: str,
    orientation: SerialEndpointOrientation,
    *,
    interface: str = "Serial0/0/0",
    observed: bool = True,
    fresh: bool = True,
    truncated: bool = False,
    complete: bool = True,
) -> SerialControllerObservation:
    """Una observacion utilizable: cada dimension explicita, ninguna asumida."""
    return SerialControllerObservation(
        device_name=device_name,
        interface=interface,
        orientation=orientation,
        clock_rate_bps=(2_000_000 if orientation is SerialEndpointOrientation.DCE else None),
        observed=observed,
        executed=True,
        fresh_evidence=fresh,
        complete=complete,
        truncated=truncated,
        parseable=True,
        interface_identity_match=True,
        pages_captured=1,
        pagination="not_encountered",
        evidence_method="fresh_show_controllers_serial",
    )


class _FakeRuntime:
    def __init__(self, observations) -> None:
        self.observations = observations
        self.calls: list[tuple[str, str]] = []

    def observe_serial_controller(
        self, device_name: str, interface: str,
    ) -> SerialControllerObservation:
        self.calls.append((device_name, interface))
        return self.observations[(device_name, interface)]


def test_fresh_dce_and_dte_return_a_new_oriented_manifest_without_changing_e4():
    topology = _topology()
    manifest = _manifest(topology)
    topology_before = topology.model_dump(mode="json")
    manifest_before = manifest.model_dump(mode="json")
    physical_hash = topology.physical_identity_hash
    runtime = _FakeRuntime({
        ("MCP-R1", "Serial0/0/0"): _observation(
            "MCP-R1", SerialEndpointOrientation.DCE,
        ),
        ("MCP-R2", "Serial0/0/0"): _observation(
            "MCP-R2", SerialEndpointOrientation.DTE,
        ),
    })

    result = SerialOrientationObserver(runtime).observe(topology, manifest)

    assert result.status is SerialOrientationStatus.VERIFIED
    assert result.oriented_manifest is not None
    assert result.oriented_manifest is not manifest
    oriented = result.oriented_manifest.link_binding_for("link/wan/r1-r2")
    assert oriented.endpoint_a.orientation is SerialEndpointOrientation.DCE
    assert oriented.endpoint_b.orientation is SerialEndpointOrientation.DTE
    assert result.oriented_manifest.physical_topology_hash == physical_hash
    assert result.oriented_manifest.semantic_hash != manifest.semantic_hash
    assert topology.model_dump(mode="json") == topology_before
    assert topology.physical_identity_hash == physical_hash
    assert manifest.model_dump(mode="json") == manifest_before
    assert runtime.calls == [
        ("MCP-R1", "Serial0/0/0"),
        ("MCP-R2", "Serial0/0/0"),
    ]


@pytest.mark.parametrize(
    "left,right",
    [
        (SerialEndpointOrientation.DCE, SerialEndpointOrientation.DCE),
        (SerialEndpointOrientation.DTE, SerialEndpointOrientation.DTE),
    ],
)
def test_a_serial_link_requires_exactly_one_dce_and_one_dte(left, right):
    topology = _topology()
    manifest = _manifest(topology)
    runtime = _FakeRuntime({
        ("MCP-R1", "Serial0/0/0"): _observation("MCP-R1", left),
        ("MCP-R2", "Serial0/0/0"): _observation("MCP-R2", right),
    })

    result = SerialOrientationObserver(runtime).observe(topology, manifest)

    assert result.status is SerialOrientationStatus.FAILED
    assert result.oriented_manifest is None
    assert "exactly one DCE and one DTE" in " ".join(result.errors)
    # The first bad role never prevents observing the other bound endpoint.
    assert runtime.calls == [
        ("MCP-R1", "Serial0/0/0"),
        ("MCP-R2", "Serial0/0/0"),
    ]


@pytest.mark.parametrize(
    "defect",
    ["not_observed", "stale", "truncated", "wrong_interface", "unresolved"],
)
def test_incomplete_or_inexact_endpoint_evidence_fails_closed(defect: str):
    topology = _topology()
    manifest = _manifest(topology)
    bad = _observation("MCP-R1", SerialEndpointOrientation.DCE)
    if defect == "not_observed":
        bad = bad.model_copy(update={"observed": False})
    elif defect == "stale":
        bad = bad.model_copy(update={"fresh_evidence": False})
    elif defect == "truncated":
        bad = bad.model_copy(update={"truncated": True, "complete": False})
    elif defect == "wrong_interface":
        bad = bad.model_copy(update={"interface": "Serial0/0/1"})
    else:
        bad = bad.model_copy(update={
            "orientation": SerialEndpointOrientation.UNRESOLVED,
        })
    runtime = _FakeRuntime({
        ("MCP-R1", "Serial0/0/0"): bad,
        ("MCP-R2", "Serial0/0/0"): _observation(
            "MCP-R2", SerialEndpointOrientation.DTE,
        ),
    })

    result = SerialOrientationObserver(runtime).observe(topology, manifest)

    assert result.status is SerialOrientationStatus.FAILED
    assert result.oriented_manifest is None
    assert len(runtime.calls) == 2


def test_a_manifest_for_another_physical_topology_fails_before_any_query():
    topology = _topology()
    manifest = _manifest(topology).model_copy(update={
        "physical_topology_hash": "another-physical-topology",
    })
    runtime = _FakeRuntime({})

    result = SerialOrientationObserver(runtime).observe(topology, manifest)

    assert result.status is SerialOrientationStatus.FAILED
    assert result.oriented_manifest is None
    assert "physical topology hash" in " ".join(result.errors).casefold()
    assert runtime.calls == []


class _FakeIosExecutor:
    def __init__(self, result: IosCommandResult) -> None:
        self.result = result
        self.calls: list[tuple[str, OperationalQueryId, str]] = []

    def execute(self, device_name, query_id, *, interface=""):
        self.calls.append((device_name, query_id, interface))
        return self.result


@pytest.mark.parametrize(
    "defect",
    ["stale", "truncated", "wrong_interface", "unparsed", "wrong_query"],
)
def test_packet_tracer_runtime_rejects_non_authoritative_controller_output(defect: str):
    output = (
        "Interface Serial0/0/0\n"
        "Hardware is GT96K\n"
        "DCE V.35, clock rate 2000000\n"
    )
    result = IosCommandResult(
        device_name="MCP-R1",
        query_id=OperationalQueryId.SHOW_CONTROLLERS_SERIAL,
        executed=True,
        output=output,
        fresh_output_observed=True,
        output_complete=True,
    )
    if defect == "stale":
        result = IosCommandResult(
            device_name="MCP-R1",
            query_id=OperationalQueryId.SHOW_CONTROLLERS_SERIAL,
            executed=True,
            output=output,
            fresh_output_observed=False,
            output_complete=True,
        )
    elif defect == "truncated":
        result = IosCommandResult(
            device_name="MCP-R1",
            query_id=OperationalQueryId.SHOW_CONTROLLERS_SERIAL,
            executed=True,
            output=output,
            fresh_output_observed=True,
            truncated_by_pager=True,
        )
    elif defect == "wrong_interface":
        result = IosCommandResult(
            device_name="MCP-R1",
            query_id=OperationalQueryId.SHOW_CONTROLLERS_SERIAL,
            executed=True,
            output=output.replace("Serial0/0/0", "Serial0/0/1"),
            fresh_output_observed=True,
            output_complete=True,
        )
    elif defect == "unparsed":
        result = IosCommandResult(
            device_name="MCP-R1",
            query_id=OperationalQueryId.SHOW_CONTROLLERS_SERIAL,
            executed=True,
            output="Interface Serial0/0/0\ncontroller state unavailable\n",
            fresh_output_observed=True,
            output_complete=True,
        )
    elif defect == "wrong_query":
        result = IosCommandResult(
            device_name="MCP-R1",
            query_id=OperationalQueryId.SHOW_INTERFACE,
            executed=True,
            output=output,
            fresh_output_observed=True,
            output_complete=True,
        )
    ios = _FakeIosExecutor(result)
    runtime = PacketTracerSerialOrientationRuntime(
        lambda _script, _timeout: None,
        ios_executor=ios,
    )

    observed = runtime.observe_serial_controller("MCP-R1", "Serial0/0/0")

    assert not observed.observed
    assert observed.orientation is SerialEndpointOrientation.UNRESOLVED
    assert ios.calls == [(
        "MCP-R1", OperationalQueryId.SHOW_CONTROLLERS_SERIAL, "Serial0/0/0",
    )]


def test_packet_tracer_runtime_uses_controlled_registered_query_and_parser():
    sent: list[str] = []
    output = (
        "Router#show controllers Serial0/0/0\n"
        "Interface Serial0/0/0\n"
        "Hardware is GT96K\n"
        "DCE V.35, clock rate 2000000\n"
        "Router#"
    )
    responses = iter((
        json.dumps({
            "found": True,
            "booting": False,
            "terminal": True,
            "prompt": "Router>",
            "output": "Router>",
        }),
        json.dumps({
            "found": True,
            "booting": False,
            "terminal": True,
            "prompt": "Router>",
            "output": "Router>",
        }),
        '{"ok":true}',
        json.dumps({
            "found": True,
            "booting": False,
            "terminal": True,
            "prompt": "Router#",
            "output": "Router#",
        }),
        json.dumps({"ok": True, "before": "Router#"}),
        json.dumps({
            "found": True,
            "configuration_channel": True,
            "output": output,
        }),
        json.dumps({
            "found": True,
            "configuration_channel": True,
            "output": output,
        }),
        '{"ok":true}',
    ))
    runtime = PacketTracerSerialOrientationRuntime(
        lambda script, _timeout: sent.append(script) or next(responses),
    )

    observed = runtime.observe_serial_controller("MCP-R1", "Serial0/0/0")

    assert isinstance(runtime.ios_executor, ControlledIosExecutor)
    assert observed.observed and observed.fresh_evidence
    assert observed.interface == "Serial0/0/0"
    assert observed.orientation is SerialEndpointOrientation.DCE
    assert observed.clock_rate_bps == 2_000_000
    assert any(
        'enterCommand("show controllers Serial0/0/0")' in script
        for script in sent
    )
