"""R-ENTRY-01: the public MCP surface of the enterprise-services entry point.

The tool is a translation layer, so what has to be proven about it is exactly
that: one registration, the four declared inputs, and a route into the SAME
application use case the rest of the tests drive. The important test here is
the last one - the default production wiring refuses under pytest, before any
channel is contacted - because that is the gate a test process must never be
able to talk its way past.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from mcp.server.fastmcp import FastMCP
from service_entry_fixture import (
    BACKEND_VERSION,
    DEPLOYMENT_ID,
    FINGERPRINT,
    IsolationPreflight,
    deployment_manifest,
    intent_json,
)

from packet_tracer_mcp.adapters.mcp import service_tools, tool_registry
from packet_tracer_mcp.adapters.mcp.public_surface import PublicMcpSurface
from packet_tracer_mcp.adapters.mcp.tool_registry import register_tools
from packet_tracer_mcp.domain.enterprise.models.execution import (
    DispatchFact,
    ResultFact,
)
from packet_tracer_mcp.domain.enterprise.models.service_entry import (
    ServiceEntryRefusal,
    ServiceStageResult,
)
from packet_tracer_mcp.infrastructure.execution.transport_outcome import (
    BridgeDispatchOutcome,
)
from packet_tracer_mcp.infrastructure.persistence.deployment_manifest_store import (
    DeploymentManifestStore,
)
from packet_tracer_mcp.infrastructure.persistence.service_run_record_store import (
    ServiceRunRecordStore,
)

TOOL_NAME = "pt_apply_enterprise_services"


def _registered_tools(surface: PublicMcpSurface = PublicMcpSurface.ENTERPRISE):
    mcp = FastMCP("surface-probe")
    register_tools(mcp, public_surface=surface)
    return asyncio.run(mcp.list_tools())


def test_exactly_one_enterprise_services_tool_is_registered():
    """A second registration would mean two routes into one workflow."""
    names = [item.name for item in _registered_tools()]

    assert names.count(TOOL_NAME) == 1


def test_the_schema_is_the_four_declared_inputs():
    """R-ENTRY-01: the published contract, not whatever the body happens to use."""
    tool = next(item for item in _registered_tools() if item.name == TOOL_NAME)

    schema = tool.inputSchema
    assert set(schema["properties"]) == {
        "intent_json",
        "deployment_id",
        "packet_tracer_version",
        "run_label",
    }
    assert set(schema.get("required", [])) == {
        "intent_json",
        "deployment_id",
        "packet_tracer_version",
    }


def test_the_existing_surface_is_unchanged_apart_from_the_new_tool():
    """R-REG-01: one tool added, nothing removed and nothing renamed."""
    names = {item.name for item in _registered_tools()}

    assert TOOL_NAME in names
    for existing in (
        "pt_live_deploy",
        "pt_query_topology",
        "pt_bridge_status",
    ):
        assert existing in names


@dataclass
class _Channel:
    """A recording stand-in for the registry transport closures."""

    channel: str = "http"
    sends: list[str] = field(default_factory=list)
    waits: list[str] = field(default_factory=list)
    inventories: int = 0
    health_reads: int = 0
    channels: list[str | None] = field(default_factory=list)
    dispatch_outcome: BridgeDispatchOutcome | None = None

    def send_and_wait(
        self, script: str, timeout: float, channel: str | None = None
    ) -> str | None:
        """Record the dispatch; a real one would reach Packet Tracer here."""
        self.waits.append(script)
        self.channels.append(channel)
        return None

    def dispatch_and_wait(
        self, script: str, timeout: float, channel: str | None = None
    ) -> BridgeDispatchOutcome:
        """Record a typed dispatch on the selected channel."""
        self.waits.append(script)
        self.channels.append(channel)
        return self.dispatch_outcome or BridgeDispatchOutcome(
            dispatch=DispatchFact.NOT_SUBMITTED,
            result=ResultFact.NOT_APPLICABLE,
        )

    def send_payload(self, script: str, channel: str | None = None) -> bool:
        """Record the fire-and-forget dispatch."""
        self.sends.append(script)
        self.channels.append(channel)
        return True

    def query_inventory(
        self, names: tuple[str, ...], channel: str | None = None
    ) -> list[dict]:
        """Record the inventory read."""
        self.inventories += 1
        self.channels.append(channel)
        return [{"name": name, "model": "PC-PT", "ports": []} for name in names]

    def observe_environment(self, channel: str):
        """Return a controlled current observation after admission."""
        self.waits.append("environment")
        self.channels.append(channel)
        return FINGERPRINT

    def pick_channel(self) -> str:
        """Model the registry picker, whose health checks contact transports."""
        self.health_reads += 1
        return self.channel

    @property
    def contacted(self) -> bool:
        """Whether anything at all reached the bridge."""
        return bool(self.sends or self.waits or self.inventories or self.health_reads)


def _invoke(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    channel: _Channel,
    manifest_store_type: type | None = None,
    **kwargs: str,
) -> dict:
    """Call the registered tool over the production wiring, with a real store."""
    manifest, _inventory = deployment_manifest()

    class Store:
        def latest_by_deployment_id(self, deployment_id: str):
            return manifest if deployment_id == DEPLOYMENT_ID else None

    monkeypatch.setattr(
        service_tools,
        "DeploymentManifestStore",
        manifest_store_type or Store,
    )
    monkeypatch.setattr(
        service_tools,
        "ServiceRunRecordStore",
        lambda *args, **kw: ServiceRunRecordStore(tmp_path),
    )
    mcp = FastMCP("surface-probe")
    service_tools.register_service_tools(
        mcp,
        send_and_wait=channel.send_and_wait,
        dispatch_and_wait=channel.dispatch_and_wait,
        send_payload=channel.send_payload,
        query_inventory=channel.query_inventory,
        pick_channel=channel.pick_channel,
        observe_environment=channel.observe_environment,
    )
    payload = {
        "intent_json": intent_json(),
        "deployment_id": DEPLOYMENT_ID,
        "packet_tracer_version": BACKEND_VERSION,
        **kwargs,
    }
    rendered = asyncio.run(mcp.call_tool(TOOL_NAME, payload))
    return json.loads(rendered[0][0].text)


def _invoke_actual_registry(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    intent_json_value: str,
) -> tuple[dict, list[str]]:
    """Call the real registry while every external health seam is a tripwire."""
    manifest, _inventory = deployment_manifest()
    contacts: list[str] = []

    class Store:
        def latest_by_deployment_id(self, deployment_id: str):
            return manifest if deployment_id == DEPLOYMENT_ID else None

    class TrappedFileBridge:
        def __init__(self) -> None:
            self.dir = tmp_path / "mailbox"

        def pt_alive(self) -> bool:
            contacts.append("file-heartbeat")
            raise AssertionError("A1/A4 contacted the file heartbeat")

    def trapped_urlopen(*_args, **_kwargs):
        contacts.append("http-health")
        raise AssertionError("A1/A4 contacted HTTP health")

    monkeypatch.setattr(service_tools, "DeploymentManifestStore", Store)
    monkeypatch.setattr(
        service_tools,
        "ServiceRunRecordStore",
        lambda *args, **kwargs: ServiceRunRecordStore(tmp_path),
    )
    monkeypatch.setattr(tool_registry, "FileBridge", TrappedFileBridge)
    monkeypatch.setattr(tool_registry.urllib.request, "urlopen", trapped_urlopen)
    mcp = FastMCP("actual-registry-probe")
    register_tools(mcp)
    rendered = asyncio.run(
        mcp.call_tool(
            TOOL_NAME,
            {
                "intent_json": intent_json_value,
                "deployment_id": DEPLOYMENT_ID,
                "packet_tracer_version": BACKEND_VERSION,
            },
        )
    )
    return json.loads(rendered[0][0].text), contacts


def test_the_production_wiring_refuses_under_pytest_before_any_channel(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    """The TEST_PROCESS gate, through the real tool and the real preflight.

    Nothing is stubbed here except the two local stores and the transport
    closures, and the transport closures exist to prove they were never used.
    A suite run must not be able to reach Packet Tracer through this tool, and
    with one namespace the only thing that distinguishes this process is that
    pytest is loaded, which is exactly what the preflight checks.
    """
    channel = _Channel()

    result = _invoke(monkeypatch, tmp_path, channel)

    assert result["refusal_code"] == ServiceEntryRefusal.IMPORT_ISOLATION_REFUSED.value
    assert "TEST_PROCESS" in result["blocked_reason"]
    assert not channel.contacted


def test_actual_registry_test_process_refusal_precedes_external_health(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    """The real `register_tools` closures do not hide picker side effects."""
    result, contacts = _invoke_actual_registry(
        monkeypatch,
        tmp_path,
        intent_json_value=intent_json(),
    )

    assert result["refusal_code"] == (
        ServiceEntryRefusal.IMPORT_ISOLATION_REFUSED.value
    )
    assert "TEST_PROCESS" in result["blocked_reason"]
    assert contacts == []


def test_invalid_json_through_the_public_route_contacts_no_channel(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    """R-ENTRY-01, via the tool rather than a helper."""
    channel = _Channel()

    result = _invoke(monkeypatch, tmp_path, channel, intent_json="{not json")

    assert result["refusal_code"] == ServiceEntryRefusal.INTENT_INVALID.value
    assert not channel.contacted


def test_actual_registry_invalid_json_precedes_external_health(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    """Malformed input exits through A1 before either registry health path."""
    result, contacts = _invoke_actual_registry(
        monkeypatch,
        tmp_path,
        intent_json_value="{not json",
    )

    assert result["refusal_code"] == ServiceEntryRefusal.INTENT_INVALID.value
    assert contacts == []


def test_invalid_json_does_not_construct_a_manifest_store(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    """A1 precedes even local collaborator initialization."""

    class ExplodingStore:
        def __init__(self) -> None:
            raise OSError("manifest base denied")

    channel = _Channel()

    result = _invoke(
        monkeypatch,
        tmp_path,
        channel,
        manifest_store_type=ExplodingStore,
        intent_json="{not json",
    )

    assert result["refusal_code"] == ServiceEntryRefusal.INTENT_INVALID.value
    assert not channel.contacted


def test_manifest_store_construction_failure_is_a_typed_public_refusal(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    """A real collaborator initialization failure cannot escape the tool."""

    class ExplodingStore:
        def __init__(self) -> None:
            raise OSError("manifest base denied")

    channel = _Channel()

    result = _invoke(
        monkeypatch,
        tmp_path,
        channel,
        manifest_store_type=ExplodingStore,
    )

    assert result["refusal_code"] == (
        ServiceEntryRefusal.DEPLOYMENT_MANIFEST_UNREADABLE.value
    )
    assert result["record_path"] == ""
    assert not channel.contacted


def test_manifest_store_construction_is_filesystem_side_effect_free(
    tmp_path: Path,
):
    """The lazy factory may be created without creating its base directory."""
    base = tmp_path / "deployment-manifests"

    DeploymentManifestStore(base)

    assert not base.exists()


def test_the_response_is_the_documented_json_shape(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    """R-ENTRY-05: the keys a caller is told to depend on are all present."""
    channel = _Channel()

    result = _invoke(monkeypatch, tmp_path, channel, run_label="nightly")

    for key in (
        "run_id",
        "run_label",
        "stage",
        "status",
        "refusal_code",
        "transport",
        "packet_tracer_version",
        "provenance",
        "e5_effect_scope",
        "e5_effect_uncertain",
        "services",
        "clients",
        "releases",
        "dirty_state",
        "persisted_stage",
        "record_path",
        "persist_error",
        "limitations",
    ):
        assert key in result, key
    assert result["run_label"] == "nightly"


def test_the_tool_routes_into_the_application_use_case(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    """Not a test-only helper: the public route is the same function.

    A tool that reimplemented the workflow would pass every other test in this
    module and share none of the admission guarantees the rest of the suite
    proves.
    """
    seen: list[str] = []
    real = service_tools.apply_enterprise_services

    def recording(intent_json_value: str, **kwargs):
        seen.append(kwargs["deployment_id"])
        return real(intent_json_value, **kwargs)

    monkeypatch.setattr(service_tools, "apply_enterprise_services", recording)
    _invoke(monkeypatch, tmp_path, _Channel())

    assert seen == [DEPLOYMENT_ID]


def test_the_channel_is_selected_once_for_the_whole_invocation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    """A5: E5 and E6 cannot end up on different transports mid-run."""
    calls: list[str] = []

    class CountingChannel(_Channel):
        def pick_channel(self) -> str:
            calls.append("pick")
            return self.channel

    monkeypatch.setattr(
        service_tools,
        "ImportIsolationPreflight",
        lambda _root: IsolationPreflight(),
    )
    _invoke(monkeypatch, tmp_path, CountingChannel())

    assert calls == ["pick"]


def test_an_absent_channel_is_reported_as_unavailable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    """No bridge is a typed refusal, not an exception out of the tool."""
    result = _invoke(monkeypatch, tmp_path, _Channel(channel="none"))

    assert result["refusal_code"] in {
        ServiceEntryRefusal.TRANSPORT_UNAVAILABLE.value,
        ServiceEntryRefusal.IMPORT_ISOLATION_REFUSED.value,
    }


def test_every_session_collaborator_keeps_the_admitted_channel(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    """A picker change after A5 cannot redirect any E5/E6 collaborator."""

    class SwitchingChannel(_Channel):
        def pick_channel(self) -> str:
            self.health_reads += 1
            return "http" if self.health_reads == 1 else "file"

    channel = SwitchingChannel()

    def inspect_binding(_intent_json: str, **kwargs) -> ServiceStageResult:
        binding = kwargs["session_factory"]()
        binding.inventory_reader(["PC-1"])
        channel.channel = "file"
        binding.runtimes.configuration._send("configuration")
        typed = binding.runtimes.services._dispatch_and_wait("service", 1.0)
        binding.endpoint_observer.observe("PC-1", "FastEthernet0")
        assert typed.dispatch is DispatchFact.NOT_SUBMITTED
        assert binding.source_tree.sha
        return ServiceStageResult(run_id="inspected", transport="http")

    monkeypatch.setattr(service_tools, "apply_enterprise_services", inspect_binding)
    monkeypatch.setattr(
        service_tools,
        "ImportIsolationPreflight",
        lambda _root: IsolationPreflight(),
    )

    _invoke(monkeypatch, tmp_path, channel)

    assert channel.health_reads == 1
    assert channel.channels
    assert set(channel.channels) == {"http"}


@pytest.mark.parametrize(
    ("dispatch", "result_fact"),
    [
        (DispatchFact.NOT_SUBMITTED, ResultFact.NOT_APPLICABLE),
        (DispatchFact.REJECTED, ResultFact.NOT_APPLICABLE),
        (DispatchFact.ACCEPTANCE_UNKNOWN, ResultFact.NOT_OBSERVED),
    ],
)
def test_bound_typed_dispatch_facts_reach_e6_unchanged(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    dispatch: DispatchFact,
    result_fact: ResultFact,
):
    """The production binding never reconstructs typed transport evidence."""
    channel = _Channel(
        dispatch_outcome=BridgeDispatchOutcome(
            dispatch=dispatch,
            result=result_fact,
            detail="controlled",
        )
    )

    def inspect_binding(_intent_json: str, **kwargs) -> ServiceStageResult:
        binding = kwargs["session_factory"]()
        observation = binding.runtimes.services._observe("service", 1.0)
        assert observation.outcome.dispatch is dispatch
        assert observation.outcome.result is result_fact
        assert observation.outcome.detail == "controlled"
        return ServiceStageResult(run_id="inspected", transport="http")

    monkeypatch.setattr(service_tools, "apply_enterprise_services", inspect_binding)
    monkeypatch.setattr(
        service_tools,
        "ImportIsolationPreflight",
        lambda _root: IsolationPreflight(),
    )

    _invoke(monkeypatch, tmp_path, channel)
