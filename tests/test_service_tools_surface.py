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
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from mcp.server.fastmcp import FastMCP
from service_entry_fixture import (
    BACKEND_VERSION,
    DEPLOYMENT_ID,
    FINGERPRINT,
    SERVER_ADDRESS,
    IsolationPreflight,
    deployment_manifest,
    intent_json,
    intent_payload,
)
from service_product_simulation import (
    SimulatedProductTransport as _SimulatedProductTransport,
)
from service_product_simulation import (
    run_environment_javascript as _run_environment_javascript,
)
from test_apply_enterprise_services import _harness
from test_service_dhcp_integration import _ModeConfigurationRuntime

from packet_tracer_mcp.adapters.cli.service_qualification import (
    _native_dhcp_http_intent,
)
from packet_tracer_mcp.adapters.mcp import service_tools, tool_registry
from packet_tracer_mcp.adapters.mcp.public_surface import PublicMcpSurface
from packet_tracer_mcp.adapters.mcp.tool_registry import register_tools
from packet_tracer_mcp.application.use_cases.apply_enterprise_services import (
    ServiceInvocationBinding,
    ServiceStageRuntimes,
    TransportSelection,
)
from packet_tracer_mcp.domain.enterprise.models.configuration_runtime import (
    ActionExecutionStatus,
)
from packet_tracer_mcp.domain.enterprise.models.execution import (
    DispatchFact,
    ResultFact,
)
from packet_tracer_mcp.domain.enterprise.models.service_entry import (
    ServiceEntryRefusal,
    ServiceStageResult,
)
from packet_tracer_mcp.domain.enterprise.models.service_plan import (
    ServiceVerificationKind,
)
from packet_tracer_mcp.domain.enterprise.models.service_run_record import (
    SourceTreeIdentity,
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


def test_registered_four_input_native_route_uses_default_catalog_and_store(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The public MCP handler reaches A1-E6 and persists scoped DHCP state."""
    payload = _native_dhcp_http_intent().model_dump(mode="json")
    harness = _harness(tmp_path, payload)
    harness.configuration = _ModeConfigurationRuntime(
        targets=harness.configuration.targets
    )
    harness.transport = TransportSelection(channel="file")
    monkeypatch.setattr(
        service_tools, "DeploymentManifestStore", lambda: harness.manifest_store
    )
    monkeypatch.setattr(
        service_tools, "ServiceRunRecordStore", lambda *_, **__: harness.record_store
    )
    monkeypatch.setattr(
        service_tools, "ImportIsolationPreflight", lambda _root: harness.preflight
    )
    monkeypatch.setattr(
        service_tools,
        "compose_service_session",
        lambda **_: (
            lambda: ServiceInvocationBinding(
                runtimes=ServiceStageRuntimes(
                    configuration=harness.configuration,
                    services=harness.services,
                ),
                record_store=harness.record_store,
                environment_fingerprint=harness.fingerprint,
                transport_selection=harness.transport,
                source_tree=SourceTreeIdentity(sha="offline-public", dirty=True),
                endpoint_observer=harness.observer,
            )
        ),
    )
    mcp = FastMCP("native-public-route")
    service_tools.register_service_tools(
        mcp,
        send_and_wait=lambda *_: None,
        dispatch_and_wait=lambda *_: BridgeDispatchOutcome(
            dispatch=DispatchFact.NOT_SUBMITTED,
            result=ResultFact.NOT_APPLICABLE,
        ),
        send_payload=lambda *_: False,
        query_inventory=lambda *_: [],
        pick_channel=lambda: "file",
        observe_environment=lambda _: FINGERPRINT,
    )
    rendered = asyncio.run(
        mcp.call_tool(
            TOOL_NAME,
            {
                "intent_json": json.dumps(payload),
                "deployment_id": harness.deployment_id,
                "packet_tracer_version": BACKEND_VERSION,
                "run_label": "offline public native route",
            },
        )
    )
    result = json.loads(rendered[0][0].text)

    assert result["refusal_code"] == ServiceEntryRefusal.NONE.value
    assert result["status"] == "verified"
    stored = ServiceRunRecordStore(tmp_path).load(
        result["deployment_id"], result["run_id"]
    )
    assert stored.status.value == "verified"
    assert stored.dhcp_authorities[0].effective_pool_name == "serverPool"


def _captured_environment_observer(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    responder,
):
    """Capture the real registry closure while replacing only transport seams."""
    captured = {}

    class FileTransport:
        def __init__(self) -> None:
            self.dir = tmp_path / "mailbox"

        def pt_alive(self) -> bool:
            return True

        def send_and_wait(self, script: str, timeout: float):
            return responder(script)

    def http_send(script, *_args, **_kwargs):
        return responder(script)

    def capture_registration(_mcp, **kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(tool_registry, "FileBridge", FileTransport)
    monkeypatch.setattr(tool_registry, "correlated_http_send_and_wait", http_send)
    monkeypatch.setattr(tool_registry, "register_service_tools", capture_registration)
    register_tools(FastMCP("environment-observer"))
    return captured["observe_environment"]


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


def _registered_product_simulation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    channel: str,
    application_version: str = BACKEND_VERSION,
    saved_file_version: str = "8.2.2.0400",
):
    """Register the real public route over one deterministic bridge channel."""
    manifest, inventory = deployment_manifest()
    manifest = manifest.model_copy(
        update={
            "environment_fingerprint": FINGERPRINT.model_copy(
                update={
                    "bridge_transport": channel,
                    "runtime_mode": "logical-workspace",
                }
            )
        }
    )
    transport = _SimulatedProductTransport(
        tmp_path,
        inventory,
        application_version=application_version,
        saved_file_version=saved_file_version,
    )

    class Store:
        def latest_by_deployment_id(self, deployment_id: str):
            return manifest if deployment_id == DEPLOYMENT_ID else None

    class HttpResponse:
        def __init__(self, body: str = "") -> None:
            self.status = 200
            self._body = body.encode("utf-8")

        def __enter__(self):
            return self

        def __exit__(self, *_args) -> None:
            return None

        def read(self) -> bytes:
            return self._body

    def urlopen(request, timeout=None):
        del timeout
        url = request.full_url if hasattr(request, "full_url") else str(request)
        if channel != "http":
            raise OSError("simulated HTTP transport unavailable")
        if "/ping" in url:
            return HttpResponse(
                json.dumps(
                    {
                        "service": "pt-mcp-bridge",
                        "id": tool_registry.token_fingerprint("test-token"),
                    }
                )
            )
        if "/status" in url:
            return HttpResponse(json.dumps({"connected": True}))
        if "/queue" in url and hasattr(request, "data"):
            transport.send(request.data.decode("utf-8"))
            return HttpResponse("queued")
        raise AssertionError(f"Unexpected simulated HTTP request: {url}")

    def http_read(script, timeout, **_kwargs):
        return transport.send_and_wait(script, timeout)

    def http_dispatch(script, timeout, **_kwargs):
        return transport.dispatch_and_wait(script, timeout)

    monkeypatch.setattr(service_tools, "DeploymentManifestStore", Store)
    monkeypatch.setattr(
        service_tools,
        "ServiceRunRecordStore",
        lambda *args, **kwargs: ServiceRunRecordStore(tmp_path),
    )
    monkeypatch.setattr(
        service_tools,
        "ImportIsolationPreflight",
        lambda _root: IsolationPreflight(),
    )
    monkeypatch.setattr(tool_registry, "FileBridge", lambda: transport)
    monkeypatch.setattr(tool_registry, "get_bridge_token", lambda: "test-token")
    monkeypatch.setattr(tool_registry.urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(tool_registry, "correlated_http_send_and_wait", http_read)
    monkeypatch.setattr(tool_registry, "correlated_http_dispatch", http_dispatch)

    mcp = FastMCP(f"actual-product-{channel}")
    register_tools(mcp)
    return mcp, transport


def _call_enterprise_services_text(
    mcp: FastMCP,
    intent: str | None = None,
    *,
    run_label: str = "",
) -> str:
    """Return the exact JSON text emitted by the registered public tool."""
    rendered = asyncio.run(
        mcp.call_tool(
            TOOL_NAME,
            {
                "intent_json": intent if intent is not None else intent_json(),
                "deployment_id": DEPLOYMENT_ID,
                "packet_tracer_version": BACKEND_VERSION,
                "run_label": run_label,
            },
        )
    )
    return rendered[0][0].text


def _call_enterprise_services(mcp: FastMCP, intent: str | None = None) -> dict:
    return json.loads(_call_enterprise_services_text(mcp, intent))


def _mail_intent(*, required: bool) -> str:
    """Return the fixture intent plus an SMTP and a POP3 service for its PCs."""
    payload = intent_payload()
    payload["sites"][0]["services"] += [
        {
            "name": "lab-mail",
            "service_type": "smtp",
            "required": required,
            "domain_name": "lab.example",
            "email_accounts": [
                {"username": "user1", "secret_ref": "mail.user1"},
                {"username": "user2", "secret_ref": "mail.user2"},
            ],
            "email_clients": [
                {
                    "client_device_id": "endpoint/hq/default/user_pc/001",
                    "username": "user1",
                },
                {
                    "client_device_id": "endpoint/hq/default/user_pc/002",
                    "username": "user2",
                },
            ],
        },
        {"name": "lab-pop3", "service_type": "pop3", "required": required},
    ]
    return json.dumps(payload)


_MAIL_MEMBERS = (
    "addUser",
    "sendMail",
    "setPassword",
    "getMailIpc",
    "EmailClient",
    "EmailServer",
    "SmtpServer",
    "Pop3Server",
)


@pytest.mark.skipif(shutil.which("node") is None, reason="Node is unavailable")
@pytest.mark.parametrize("channel", ["http", "file"])
def test_the_default_catalog_keeps_every_mail_effect_off_the_public_route(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    channel: str,
):
    """S2-11: optional mail is excluded and no mail script leaves the product."""
    mcp, transport = _registered_product_simulation(
        monkeypatch, tmp_path, channel=channel
    )

    result = _call_enterprise_services(mcp, _mail_intent(required=False))

    assert result["refusal_code"] == ServiceEntryRefusal.NONE.value, result[
        "blocked_reason"
    ]
    mail = [
        item for item in result["services"] if item["service_type"] in {"smtp", "pop3"}
    ]
    assert len(mail) == 2
    assert all(item["usability_status"] == "skipped" for item in mail)
    for script in [*transport.send_payloads, *transport.dispatch_payloads]:
        for member in _MAIL_MEMBERS:
            assert member not in script, member


@pytest.mark.skipif(shutil.which("node") is None, reason="Node is unavailable")
def test_a_required_mail_service_is_refused_on_the_public_route(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    """S2-08/11: required and UNKNOWN refuses before any effect."""
    mcp, transport = _registered_product_simulation(
        monkeypatch, tmp_path, channel="http"
    )

    result = _call_enterprise_services(mcp, _mail_intent(required=True))

    assert result["refusal_code"] == ServiceEntryRefusal.SERVICE_INELIGIBLE.value
    assert transport.send_payloads == []
    assert transport.dispatch_payloads == []


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


@pytest.mark.skipif(shutil.which("node") is None, reason="Node is unavailable")
@pytest.mark.parametrize("channel", ["http", "file"])
def test_runtime_provenance_uses_application_version_on_each_fixed_channel(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    channel: str,
):
    """The generated script observes the executable, not saved-file metadata."""

    def saved_match_application_differs(script: str) -> str:
        return _run_environment_javascript(
            script,
            application_version="9.0.1.9999",
            saved_file_version=BACKEND_VERSION,
        )

    observer = _captured_environment_observer(
        monkeypatch,
        tmp_path,
        saved_match_application_differs,
    )
    mismatching = observer(channel)
    assert mismatching.backend_version == "9.0.1.9999"
    assert mismatching.bridge_transport == channel

    def application_match_saved_differs(script: str) -> str:
        return _run_environment_javascript(
            script,
            application_version=BACKEND_VERSION,
            saved_file_version="8.2.2.0400",
        )

    observer = _captured_environment_observer(
        monkeypatch,
        tmp_path,
        application_match_saved_differs,
    )
    matching = observer(channel)
    assert matching.backend_version == BACKEND_VERSION
    assert matching.bridge_transport == channel


@pytest.mark.skipif(shutil.which("node") is None, reason="Node is unavailable")
@pytest.mark.parametrize("channel", ["http", "file"])
@pytest.mark.parametrize(
    "case",
    [
        "missing_getter",
        "partial_version",
        "getter_exception",
        "malformed_response",
        "missing_active_file",
    ],
)
def test_runtime_provenance_refuses_unavailable_or_incomplete_application_version(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    channel: str,
    case: str,
):
    """Exact-build admission never fabricates or falls back to a file version."""

    def responder(script: str) -> str:
        if case == "malformed_response":
            return "{not-json"
        raw = _run_environment_javascript(
            script,
            application_version=(
                "9.0.1" if case == "partial_version" else BACKEND_VERSION
            ),
            saved_file_version=BACKEND_VERSION,
            active_file=case != "missing_active_file",
            application_getter=case != "missing_getter",
            application_raises=case == "getter_exception",
        )
        if case == "missing_getter":
            assert json.loads(raw)["found"] is False
        return raw

    observer = _captured_environment_observer(monkeypatch, tmp_path, responder)

    observed = observer(channel)

    assert observed.backend == "packet_tracer"
    assert observed.backend_version == ""
    assert observed.bridge_transport == ""


@pytest.mark.skipif(shutil.which("node") is None, reason="Node is unavailable")
@pytest.mark.parametrize("channel", ["http", "file"])
def test_actual_public_entry_requests_complete_e5_inventory_and_reuses_retained_actions(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    channel: str,
):
    """The complete public route succeeds with an exact-name bridge provider."""
    mcp, transport = _registered_product_simulation(
        monkeypatch,
        tmp_path,
        channel=channel,
    )
    _manifest, inventory = deployment_manifest()
    expected_names = {item.device_name for item in inventory}

    first = _call_enterprise_services(mcp)

    assert first["refusal_code"] == ServiceEntryRefusal.NONE.value, first[
        "blocked_reason"
    ]
    assert first["status"] == "verified", (first, transport.unhandled)
    assert first["transport"] == channel
    assert len(first["clients"]) == 2
    assert all(
        outcome["status"] == ActionExecutionStatus.VERIFIED.value
        for client in first["clients"]
        for outcome in client["results"].values()
        if outcome["required"]
    )
    assert len(transport.inventory_requests) == 1
    assert set(transport.inventory_requests[0]) == expected_names
    assert any(
        name.endswith("ACCESS-SW-01") for name in transport.inventory_requests[0]
    )
    first_e5_dispatches = len(transport.send_payloads)
    assert first_e5_dispatches > 0
    first_record = ServiceRunRecordStore(tmp_path).load(DEPLOYMENT_ID, first["run_id"])
    assert first_record.configuration_result is not None
    assert first_record.service_result is not None

    second = _call_enterprise_services(mcp)

    assert second["status"] == "verified", (second, transport.unhandled)
    assert second["refusal_code"] == ServiceEntryRefusal.NONE.value
    assert second["e5_effect_scope"]["retained"]
    assert second["e5_effect_scope"]["mutated"] == []
    assert len(transport.send_payloads) == first_e5_dispatches
    assert len(transport.inventory_requests) == 2
    assert all(set(names) == expected_names for names in transport.inventory_requests)
    second_record = ServiceRunRecordStore(tmp_path).load(
        DEPLOYMENT_ID, second["run_id"]
    )
    assert second_record.e5_effect_scope.retained
    assert second_record.configuration_result is not None
    assert second_record.service_result is not None
    assert transport.unhandled == []


@pytest.mark.skipif(shutil.which("node") is None, reason="Node is unavailable")
def test_actual_admitted_public_entry_measures_record_and_mcp_response_serialization(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    """Measure the complete persisted invocation and exact public JSON text."""
    mcp, transport = _registered_product_simulation(
        monkeypatch,
        tmp_path,
        channel="file",
    )

    raw = _call_enterprise_services_text(mcp)
    response = json.loads(raw)
    record_path = Path(response["record_path"])
    persisted = record_path.read_bytes()
    stored = ServiceRunRecordStore(tmp_path).load(DEPLOYMENT_ID, response["run_id"])

    response_bytes = len(raw.encode("utf-8"))
    record_bytes = len(persisted)
    assert response_bytes == len(
        json.dumps(response, indent=2, ensure_ascii=False).encode("utf-8")
    )
    assert record_bytes == len(
        (stored.model_dump_json(indent=2) + "\n").encode("utf-8")
    )
    assert record_bytes > response_bytes > 0
    assert stored.operational_readiness == response["operational_readiness"]
    assert stored.operational_readiness
    for row in stored.operational_readiness:
        sample = row["sample"]
        assert len(sample["sample_history"]) == sample["samples"]
    assert transport.unhandled == []


@pytest.mark.skipif(shutil.which("node") is None, reason="Node is unavailable")
def test_cold_http_preparation_uses_each_clients_first_by_ip_request(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    """Prepare the product trace without a ping, DNS read or warming fetch."""
    marker = "COLD_HTTP_PREP_ATTEMPT_001"
    payload = intent_payload()
    payload["sites"][0]["services"] = [
        service
        for service in payload["sites"][0]["services"]
        if service["service_type"] == "http"
    ]
    payload["sites"][0]["services"][0]["http_content"] = marker
    mcp, transport = _registered_product_simulation(
        monkeypatch,
        tmp_path,
        channel="file",
    )
    assert transport.page_content == "STALE_WEB_PAGE"
    assert not list(tmp_path.rglob("*.json"))

    raw = _call_enterprise_services_text(
        mcp,
        json.dumps(payload),
        run_label="cold-http-preparation",
    )
    response = json.loads(raw)
    stored = ServiceRunRecordStore(tmp_path).load(DEPLOYMENT_ID, response["run_id"])

    assert response["status"] == "verified", (response, transport.unhandled)
    assert response["refusal_code"] == ServiceEntryRefusal.NONE.value
    assert response["run_label"] == "cold-http-preparation"
    assert response["transport"] == "file"
    assert response["e5_effect_scope"]["retained"] == []
    mutated = response["e5_effect_scope"]["mutated"]
    assert len(mutated) == 7
    assert not [item for item in mutated if item.startswith("cfg/hostname/")]
    assert sum(item.startswith("cfg/vlan/") for item in mutated) == 1
    assert sum(item.startswith("cfg/access/") for item in mutated) == 3
    assert sum(item.startswith("cfg/endpoint-static/") for item in mutated) == 3
    excluded = response["e5_effect_scope"]["excluded"]
    assert len(excluded) == 1
    assert excluded[0].startswith("cfg/hostname/")
    assert stored.status.value == response["status"]
    assert stored.e5_effect_scope.retained == []
    assert stored.e5_effect_scope.mutated == mutated
    assert [item.model_dump(mode="json") for item in stored.clients] == response[
        "clients"
    ]
    assert stored.operational_readiness == response["operational_readiness"]
    assert [item.model_dump(mode="json") for item in stored.releases] == response[
        "releases"
    ]
    assert re.fullmatch(r"[0-9a-f]{40}", stored.source_tree.sha)
    assert re.fullmatch(r"[0-9a-f]{40}", stored.source_tree.tree)

    readiness = stored.operational_readiness
    assert len(readiness) == 1
    sample = readiness[0]["sample"]
    assert sample["vlan_id"] == 10
    assert set(sample["requested_interfaces"]) == {
        "FastEthernet1/1",
        "FastEthernet1/2",
        "FastEthernet1/3",
    }
    assert len(sample["sample_history"]) == sample["samples"]
    assert {item["state"] for item in sample["sample_history"][-1]["rows"]} == {"FWD"}

    expected_owner_by_check = {
        check.expectation_id: client.deployed_name
        for client in stored.clients
        for outcome in client.results.values()
        for check in outcome.checks
        if check.kind is ServiceVerificationKind.HTTP_FETCH
    }
    http_rows = [
        row
        for row in stored.service_result.verification_results
        if row.expectation_id in expected_owner_by_check
    ]
    assert len(http_rows) == 2
    for row in http_rows:
        expected_owner = expected_owner_by_check[row.expectation_id]
        assert row.status is ActionExecutionStatus.VERIFIED
        assert row.observed["selected_url"] == f"http://{SERVER_ADDRESS}/"
        assert row.observed["selected_path"] == "/"
        assert row.observed["selected_url_is_input"] is True
        assert row.observed["marker"] == marker
        assert row.observed["owner_device"] == expected_owner
        assert row.observed["owner_read"] is True
        assert row.observed["client_mode"] == "http"
        assert row.observed["go_result"] is True
        assert row.observed["go_result_type"] == "boolean"
        assert row.observed["released"] == "released"
        assert row.trace[0].label == "start"
        assert row.trace[0].outcome == "request_started"
        assert row.trace[0].content_length == 0
        assert row.trace[0].marker_present is False
        assert any(step.marker_present for step in row.trace if step.performed)

    starts = [item for item in transport.events if item.startswith("http_start:")]
    assert len(starts) == 2
    assert set(starts) == {
        "http_start:HQ-DEFAULT-PC-01",
        "http_start:HQ-DEFAULT-PC-02",
    }
    assert transport.events.count("http_release") == 2
    content_event = f"http_content_set:{marker}"
    assert transport.events.count(content_event) == 1
    assert transport.page_content == marker
    assert not [item for item in transport.events if item.startswith("dns_start:")]
    assert transport.last_dns_command == ""
    assert transport.events.index(content_event) < transport.events.index(
        "http_direct_readback"
    )
    assert (
        max(
            index
            for index, event in enumerate(transport.events)
            if event.startswith("e5_readback:")
        )
        < transport.events.index("readiness:FWD")
        < min(
            index
            for index, event in enumerate(transport.events)
            if event.startswith("http_start:")
        )
    )
    assert transport.unhandled == []


@pytest.mark.skipif(shutil.which("node") is None, reason="Node is unavailable")
@pytest.mark.parametrize("channel", ["http", "file"])
def test_actual_public_entry_refuses_executable_version_mismatch_before_effects(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    channel: str,
):
    """A matching saved file cannot stand in for the executing application."""
    mcp, transport = _registered_product_simulation(
        monkeypatch,
        tmp_path,
        channel=channel,
        application_version="9.0.1.9999",
        saved_file_version=BACKEND_VERSION,
    )

    result = _call_enterprise_services(mcp)

    assert result["refusal_code"] == (
        ServiceEntryRefusal.ENVIRONMENT_FINGERPRINT_MISMATCH.value
    )
    assert result["status"] == "refused"
    assert result["transport"] == channel
    assert transport.inventory_requests == []
    assert transport.send_payloads == []
    assert transport.dispatch_payloads == []
    assert transport.unhandled == []


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
        assert binding.source_tree.tree
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
