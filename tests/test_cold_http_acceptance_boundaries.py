"""The adapter, composition and persistence boundaries of the acceptance envelope.

These are the seams the route tests rely on: the write-once envelope store, the
fixed product channel and its single shared script definitions, the shared
session composition with and without the optional controls, and the out-of-band
adapter, which must refuse under pytest before any channel exists.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest
from mcp.server.fastmcp import FastMCP
from service_entry_fixture import FINGERPRINT, IsolationPreflight

from packet_tracer_mcp.adapters import service_session
from packet_tracer_mcp.adapters.cli import cold_http_acceptance as cli
from packet_tracer_mcp.adapters.mcp import service_tools, tool_registry
from packet_tracer_mcp.application.ports.service_run_record import (
    RunRecordPersistenceError,
)
from packet_tracer_mcp.application.use_cases.apply_enterprise_services import (
    TransportSelection,
)
from packet_tracer_mcp.domain.enterprise.models.cold_http_acceptance import (
    ColdHttpAcceptanceEnvelope,
)
from packet_tracer_mcp.domain.enterprise.models.service_entry import (
    ServiceStageResult,
)
from packet_tracer_mcp.domain.enterprise.models.service_run_record import (
    ServiceRunRecord,
    SourceTreeIdentity,
)
from packet_tracer_mcp.infrastructure.execution import product_channel
from packet_tracer_mcp.infrastructure.execution.product_channel import (
    FixedChannelProductTransport,
)
from packet_tracer_mcp.infrastructure.persistence.cold_http_acceptance_store import (
    ColdHttpAcceptanceStore,
)
from packet_tracer_mcp.infrastructure.persistence.service_run_record_store import (
    ServiceRunRecordStore,
)

_ATTEMPT = "0f1e2d3c4b5a69788796a5b4c3d2e1f0"
_REPO = Path(__file__).resolve().parents[1]


def _envelope(**update) -> ColdHttpAcceptanceEnvelope:
    envelope = ColdHttpAcceptanceEnvelope(
        attempt_id=_ATTEMPT, started_at=datetime(2026, 9, 22, tzinfo=UTC)
    )
    return envelope.model_copy(update=update)


# -- the envelope store -------------------------------------------------------------


def test_an_envelope_is_begun_once_and_completed_once(tmp_path: Path):
    """C10: write-ahead create-only, one completion, then immutable."""
    store = ColdHttpAcceptanceStore(tmp_path)
    begun = _envelope()
    path = Path(store.begin(begun))
    written_ahead = path.read_bytes()

    with pytest.raises(RunRecordPersistenceError, match="already exists"):
        store.begin(begun)
    done = begun.model_copy(update={"completed_at": datetime.now(UTC)})
    completed = Path(store.complete(done))
    with pytest.raises(RunRecordPersistenceError, match="immutable"):
        store.complete(done)
    assert completed == store.completed_path_for(_ATTEMPT)
    assert path.read_bytes() == written_ahead
    assert store.load(_ATTEMPT).completed_at is not None
    assert not list(tmp_path.glob("*.tmp"))


def test_a_completion_that_loses_a_race_never_replaces_the_winner(tmp_path: Path):
    """C10: completion is one atomic creation, never check-then-replace."""
    store = ColdHttpAcceptanceStore(tmp_path)
    begun = _envelope()
    store.begin(begun)
    winner = store.completed_path_for(_ATTEMPT)
    winner.write_text('{"winner": true}', encoding="utf-8")

    with pytest.raises(RunRecordPersistenceError, match="immutable"):
        store.complete(begun.model_copy(update={"completed_at": datetime.now(UTC)}))

    assert winner.read_text(encoding="utf-8") == '{"winner": true}'


@pytest.mark.parametrize(
    ("setup", "envelope", "message"),
    [
        (False, _envelope(completed_at=datetime.now(UTC)), "begun before"),
        (True, _envelope(completed_at=None), "needs completed_at"),
        (
            True,
            _envelope(
                completed_at=datetime.now(UTC),
                started_at=datetime(2026, 9, 23, tzinfo=UTC),
            ),
            "another invocation",
        ),
    ],
)
def test_an_envelope_completion_is_refused_unless_it_is_its_own(
    tmp_path: Path, setup, envelope, message
):
    """C10: a completion never creates, overwrites or adopts another envelope."""
    store = ColdHttpAcceptanceStore(tmp_path)
    if setup:
        store.begin(_envelope())

    with pytest.raises(RunRecordPersistenceError, match=message):
        store.complete(envelope)


@pytest.mark.parametrize("attempt", ["", "../escape", "a/b"])
def test_an_unsafe_attempt_identity_never_reaches_a_path(tmp_path: Path, attempt):
    """Path containment: only a safe attempt identity names a file."""
    store = ColdHttpAcceptanceStore(tmp_path)

    with pytest.raises(RunRecordPersistenceError, match="safe name"):
        store.path_for(attempt)


def test_a_begun_envelope_cannot_claim_completion(tmp_path: Path):
    """C10: the write-ahead file is never already a terminal one."""
    store = ColdHttpAcceptanceStore(tmp_path)

    with pytest.raises(RunRecordPersistenceError, match="cannot be completed"):
        store.begin(_envelope(completed_at=datetime.now(UTC)))


def test_the_run_record_evidence_read_digests_the_bytes_it_validated(tmp_path: Path):
    """C9: the cited digest is of the very bytes the envelope interpreted."""
    store = ServiceRunRecordStore(tmp_path)
    record = ServiceRunRecord(
        run_id="run-1", created_at=datetime.now(UTC), deployment_id="deploy-hq-1"
    )
    written = Path(store.begin(record))

    loaded, path, digest = store.load_evidence("deploy-hq-1", "run-1")

    assert Path(path) == written
    assert digest == hashlib.sha256(written.read_bytes()).hexdigest()
    assert loaded.run_id == "run-1"
    written.write_text("{", encoding="utf-8")
    with pytest.raises(RunRecordPersistenceError, match="unreadable"):
        store.load_evidence("deploy-hq-1", "run-1")


# -- the fixed channel ------------------------------------------------------------------


class _Transport:
    def __init__(self, answer: str | None = None) -> None:
        self.answer = answer
        self.sent: list[str] = []
        self.waited: list[tuple[str, float]] = []

    def send(self, js_code: str) -> bool:
        self.sent.append(js_code)
        return True

    def send_and_wait(self, js_code: str, timeout: float):
        self.waited.append((js_code, timeout))
        return self.answer

    def dispatch_and_wait(self, js_code: str, timeout: float):
        self.waited.append((js_code, timeout))
        return None


def test_the_fixed_channel_applies_the_registry_guards():
    """C4/C11: one definition of each guard serves both routes."""
    transport = _Transport("{}")
    fixed = FixedChannelProductTransport("file", transport)

    assert fixed.send_payload("configurePcIp(1);", "file") is True
    fixed.dispatch_and_wait("reportResult(1);", 5.0, "file")

    assert transport.sent == [
        product_channel.fire_and_forget_guard("configurePcIp(1);")
    ]
    assert transport.waited == [(product_channel.waited_guard("reportResult(1);"), 5.0)]
    assert tool_registry.waited_guard is product_channel.waited_guard
    assert tool_registry.fire_and_forget_guard is product_channel.fire_and_forget_guard
    assert tool_registry.targeted_inventory_js is product_channel.targeted_inventory_js


def test_the_fixed_channel_inventory_is_always_target_directed():
    """The product never reads the whole workspace through the fixed channel."""
    answer = json.dumps({"devices": [{"name": "A", "model": "PC-PT", "ports": []}]})
    transport = _Transport(answer)
    fixed = FixedChannelProductTransport("file", transport)

    assert fixed.query_inventory(["A", "A"], "file") == [
        {"name": "A", "model": "PC-PT", "ports": []}
    ]
    script, timeout = transport.waited[0]
    assert '["A"]' in script
    assert timeout == product_channel.INVENTORY_TIMEOUT_SECONDS
    with pytest.raises(ValueError, match="target-directed"):
        fixed.query_inventory([], "file")


@pytest.mark.parametrize("answer", [None, "PT_ERROR: x", "ERROR:y", "not json"])
def test_an_unusable_inventory_answer_is_no_devices(answer):
    """The registry's parse, shared: an unusable answer names no device."""
    assert product_channel.parse_inventory_devices(answer) == []


def test_the_fixed_channel_reads_the_environment_on_its_own_channel():
    """C4: the environment is observed fresh, over the bound channel only."""
    answer = json.dumps(
        {
            "found": True,
            "backend": "packet_tracer",
            "backend_version": "9.0.1.0858",
            "extension_version": "",
            "runtime_mode": "logical-workspace",
        }
    )
    fixed = FixedChannelProductTransport("file", _Transport(answer))

    observed = fixed.observe_environment("file")

    assert observed.backend_version == "9.0.1.0858"
    assert observed.bridge_transport == "file"


# -- the shared composition -------------------------------------------------------------


class _Callables:
    def __init__(self) -> None:
        self.selected = 0

    def send_and_wait(self, script, timeout, channel):
        return None

    def dispatch_and_wait(self, script, timeout, channel):
        return None

    def send_payload(self, script, channel):
        return True

    def query_inventory(self, names, channel):
        return []

    def observe_environment(self, channel):
        return FINGERPRINT

    def select(self) -> TransportSelection:
        self.selected += 1
        return TransportSelection(channel="file", fixed_at=datetime.now(UTC))


def _compose(callables: _Callables, tmp_path: Path, controls=None):
    return service_session.compose_service_session(
        send_and_wait=callables.send_and_wait,
        dispatch_and_wait=callables.dispatch_and_wait,
        send_payload=callables.send_payload,
        query_inventory=callables.query_inventory,
        observe_environment=callables.observe_environment,
        select_transport=callables.select,
        record_store_factory=lambda: ServiceRunRecordStore(tmp_path),
        observe_source_tree=lambda: SourceTreeIdentity(sha="a" * 40, tree="b" * 40),
        controls=controls,
    )


def test_the_composition_is_lazy_and_inert_without_controls(tmp_path: Path):
    """C11: nothing is selected before A5, and no default control is composed."""
    callables = _Callables()
    factory = _compose(callables, tmp_path)
    assert callables.selected == 0

    binding = factory()

    assert callables.selected == 1
    assert binding.effect_admission is None
    configuration = binding.runtimes.configuration
    services = binding.runtimes.services
    assert configuration._wait_allowance is None
    assert services._owned_release is None
    assert configuration._ios._remaining_budget is None
    assert binding.transport_selection.channel == "file"


def test_the_composition_wires_every_governing_control(tmp_path: Path):
    """C6/C7/C5: clock, sleeper, allowance, release scope and admission arrive."""

    def clock() -> float:
        return 0.0

    def sleeper(seconds: float) -> None:
        return None

    def allowance() -> float:
        return 1.0

    def release(expectation_id: str):
        raise AssertionError("not entered here")

    def admission(closure) -> str:
        return ""

    controls = service_session.SessionControls(
        clock=clock,
        sleeper=sleeper,
        wait_allowance=allowance,
        owned_release=release,
        effect_admission=admission,
    )

    binding = _compose(_Callables(), tmp_path, controls)()

    configuration = binding.runtimes.configuration
    services = binding.runtimes.services
    assert configuration._wait_allowance is allowance
    assert configuration._clock is clock and configuration._sleeper is sleeper
    assert configuration._ios._remaining_budget is allowance
    assert services._owned_release is release
    assert services._clock is clock and services._sleep is sleeper
    assert binding.effect_admission is admission


def test_the_public_tool_composes_no_governing_control(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """C11: the four-string MCP tool shares the composition and none of its hooks."""
    seen = {}

    def inspect(_intent_json: str, **kwargs) -> ServiceStageResult:
        binding = kwargs["session_factory"]()
        seen["binding"] = binding
        return ServiceStageResult(run_id="inspected", transport="file")

    monkeypatch.setattr(service_tools, "apply_enterprise_services", inspect)
    monkeypatch.setattr(
        service_tools, "ImportIsolationPreflight", lambda _root: IsolationPreflight()
    )
    monkeypatch.setattr(
        service_tools,
        "ServiceRunRecordStore",
        lambda *args, **kwargs: ServiceRunRecordStore(tmp_path),
    )
    callables = _Callables()
    mcp = FastMCP("controls")
    service_tools.register_service_tools(
        mcp,
        send_and_wait=callables.send_and_wait,
        dispatch_and_wait=callables.dispatch_and_wait,
        send_payload=callables.send_payload,
        query_inventory=callables.query_inventory,
        pick_channel=lambda: "file",
        observe_environment=callables.observe_environment,
    )
    tools = asyncio.run(mcp.list_tools())
    asyncio.run(
        mcp.call_tool(
            "pt_apply_enterprise_services",
            {
                "intent_json": "{}",
                "deployment_id": "d",
                "packet_tracer_version": "9.0.1.0858",
            },
        )
    )

    binding = seen["binding"]
    assert binding.effect_admission is None
    assert binding.runtimes.configuration._wait_allowance is None
    assert binding.runtimes.services._owned_release is None
    assert set(tools[0].inputSchema["properties"]) == {
        "intent_json",
        "deployment_id",
        "packet_tracer_version",
        "run_label",
    }


# -- the out-of-band adapter --------------------------------------------------------------


def _write_inputs(tmp_path: Path) -> tuple[str, str]:
    from cold_http_acceptance_harness import (
        acceptance_manifest,
        cold_http_intent,
        grant_document,
    )

    intent = cold_http_intent()
    grant = grant_document(acceptance_manifest(), intent)
    grant_path = tmp_path / "grant.json"
    intent_path = tmp_path / "intent.json"
    grant_path.write_text(json.dumps(grant), encoding="utf-8", newline="\n")
    intent_path.write_bytes(intent.encode("utf-8"))
    return str(grant_path), str(intent_path)


def test_the_adapter_refuses_without_execute_and_reads_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    """Nothing runs by default; the grant path is not even opened."""
    code = cli.main(["--grant", str(tmp_path / "absent.json")], environ={})

    assert code == 2
    assert "--execute is required" in capsys.readouterr().out


def test_the_adapter_refuses_without_a_governed_root(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    """The governed checkout is declared by the operator, never defaulted."""
    code = cli.main(["--execute"], environ={})

    assert code == 2
    assert "PT_MCP_GOVERNED_ROOT" in capsys.readouterr().out


@pytest.mark.parametrize("problem", ["missing", "oversize", "not_json"])
def test_the_adapter_refuses_an_unreadable_input(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], problem
):
    """An operator file that cannot be read whole refuses before composition."""
    grant_path, intent_path = _write_inputs(tmp_path)
    if problem == "missing":
        grant_path = str(tmp_path / "absent.json")
    elif problem == "oversize":
        Path(grant_path).write_text(" " * (cli.MAX_GRANT_BYTES + 1), encoding="utf-8")
    else:
        Path(grant_path).write_text("{", encoding="utf-8")
    composed: list[Path] = []

    code = cli.main(
        ["--execute", "--grant", grant_path, "--intent", intent_path],
        environ={"PT_MCP_GOVERNED_ROOT": str(tmp_path)},
        boundaries_factory=lambda root: composed.append(root),
    )

    assert code == 2
    assert composed == []
    assert "input_unreadable" in capsys.readouterr().out


def test_the_production_wiring_refuses_under_pytest_before_any_channel(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    """C2: the real preflight names this process a test run before contact."""
    grant_path, intent_path = _write_inputs(tmp_path)
    touched: list[str] = []

    def trap(name: str):
        def refuse(*args, **kwargs):
            touched.append(name)
            raise AssertionError(f"{name} was reached")

        return refuse

    class TrappedCoordinator:
        claim = staticmethod(trap("campaign_claim"))

    def boundaries(root: Path):
        composed = cli.production_boundaries(root)
        return replace(
            composed,
            open_channel=trap("open_channel"),
            lifecycle=trap("lifecycle"),
            campaign_coordinator=TrappedCoordinator(),
            repository=trap("repository"),
            record_store=ServiceRunRecordStore(tmp_path / "records"),
            envelope_store=ColdHttpAcceptanceStore(tmp_path / "envelopes"),
        )

    code = cli.main(
        ["--execute", "--grant", grant_path, "--intent", intent_path],
        environ={"PT_MCP_GOVERNED_ROOT": str(_REPO)},
        boundaries_factory=boundaries,
    )

    summary = json.loads(capsys.readouterr().out)
    assert code == 2
    assert touched == []
    assert summary["campaign_outcome"] == "refused"
    assert summary["admission"][0]["subject"] == "isolation"
    assert "TEST_PROCESS" in summary["admission"][0]["detail"]
    assert not (tmp_path / "envelopes").exists()


def test_composing_the_production_boundaries_performs_no_io(tmp_path: Path):
    """Building the LIVE boundaries creates, reads and opens nothing."""
    root = tmp_path / "root"

    boundaries = cli.production_boundaries(root)

    assert not root.exists()
    assert boundaries.record_store.base_dir == (root / "data" / "services").absolute()
    assert (
        boundaries.envelope_store.base_dir
        == (root / "data" / "acceptance" / "cold-http").absolute()
    )
    assert boundaries.open_channel is cli.open_file_channel


def test_the_adapter_opens_only_the_envelopes_channel():
    """C4: any other channel name is refused without constructing a transport."""
    opened = cli.open_file_channel("http")

    assert opened.transport is None
    assert opened.live is False
