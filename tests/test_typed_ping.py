"""Pruebas offline del ping cerrado y de su ventana de evidencia fresca."""

from __future__ import annotations

import json
import shutil
import subprocess

import pytest

from src.packet_tracer_mcp.infrastructure.execution.typed_ping import TypedPingExecutor


@pytest.mark.parametrize(
    ("received", "reachable"),
    ((4, True), (0, False)),
)
def test_typed_ping_distinguishes_fresh_positive_and_negative(received, reachable):
    scripts: list[str] = []
    before = "C:\\>"
    output = (
        before
        + "ping 10.0.50.10\n"
        + f"Packets: Sent = 4, Received = {received}, Lost = {4 - received}\nC:\\>"
    )

    def send_and_wait(script, _timeout):
        scripts.append(script)
        if "enterCommand" in script:
            return json.dumps({"started": True, "before": before})
        return json.dumps({"found": True, "output": output})

    result = TypedPingExecutor(send_and_wait, timeout_seconds=0).ping(
        "GUEST-PC", "10.0.50.10",
    )

    assert result.reachable is reachable
    assert result.fresh_output_observed
    assert result.window_strategy == "prefix_delta"
    assert any('enterCommand("ping 10.0.50.10")' in script for script in scripts)
    assert any("getCommandPrompt" in script for script in scripts)
    assert any("getCommandLine" in script for script in scripts)


def test_typed_ping_rejects_stale_output_as_evidence():
    before = (
        "C:\\>ping 10.0.50.10\n"
        "Packets: Sent = 4, Received = 4, Lost = 0\nC:\\>"
    )

    def send_and_wait(script, _timeout):
        if "enterCommand" in script:
            return json.dumps({"started": True, "before": before})
        return json.dumps({"found": True, "output": before})

    result = TypedPingExecutor(send_and_wait, timeout_seconds=0).ping(
        "GUEST-PC", "10.0.50.10",
    )

    assert not result.reachable
    assert not result.fresh_output_observed
    assert result.window_strategy == "no_fresh_window"


def test_typed_ping_rejects_invalid_destination_before_bridge_call():
    scripts: list[str] = []

    result = TypedPingExecutor(
        lambda script, _timeout: scripts.append(script) or None,
    ).ping("GUEST-PC", "not-an-ip")

    assert not result.reachable
    assert not result.fresh_output_observed
    assert result.failure_reason == "invalid_destination"
    assert scripts == []


def test_typed_ping_rejects_destination_command_injection_before_bridge_call():
    scripts: list[str] = []

    result = TypedPingExecutor(
        lambda script, _timeout: scripts.append(script) or None,
    ).ping("GUEST-PC", "10.0.50.10\nconfigure terminal")

    assert not result.reachable
    assert not result.fresh_output_observed
    assert result.failure_reason == "invalid_destination"
    assert scripts == []


def test_typed_ping_requires_the_current_command_echo_for_attribution():
    before = "C:\\>"
    unrelated_delta = (
        before
        + "Packets: Sent = 4, Received = 4, Lost = 0 (0% loss)\nC:\\>"
    )

    def send_and_wait(script, _timeout):
        if "enterCommand" in script:
            return json.dumps({"started": True, "before": before})
        return json.dumps({"found": True, "output": unrelated_delta})

    result = TypedPingExecutor(send_and_wait, timeout_seconds=0).ping(
        "GUEST-PC", "10.0.50.10",
    )

    assert not result.reachable
    assert not result.fresh_output_observed
    assert result.failure_reason == "current_ping_echo_not_observed"


def test_typed_ping_retains_ambiguous_identity_candidates_for_diagnosis():
    before = "PC>"
    output = (
        before
        + "ping 10.0.50.10\n"
        + "Packets: Sent = 4, Received = 4, Lost = 0\nPC>"
    )

    def send_and_wait(script, _timeout):
        if "enterCommand" in script:
            return json.dumps({"started": True, "before": before})
        if "owner_candidate_names" in script:
            return json.dumps({
                "found": True,
                "output": output,
                "owner_name": "",
                "owner_evidence": "none",
                "owner_candidates": 2,
                "owner_candidate_evidence": "dispatch_transcript_delta",
                "owner_candidate_names": ["PC-A", "PC-B"],
            })
        return json.dumps({"found": True, "output": output})

    result = TypedPingExecutor(send_and_wait, timeout_seconds=0).ping(
        "PC-B", "10.0.50.10",
    )

    assert result.device_identity_provenance == "ambiguous"
    assert result.device_identity_candidate_evidence == (
        "dispatch_transcript_delta"
    )
    assert result.device_identity_candidate_names == ("PC-A", "PC-B")


@pytest.mark.parametrize(
    "evidence",
    [
        # La continuidad de transcripcion ya fue falsada en vivo por Router3, y
        # la identidad de objeto sale de la misma busqueda por nombre.
        "session_transcript_continuity",
        "terminal_object_identity",
        "because_it_was_requested",
    ],
)
def test_typed_ping_identity_accepts_only_the_dispatch_delta_authority(evidence):
    before = "C:\\>"
    output = (
        before
        + "ping 10.0.50.10\n"
        + "Packets: Sent = 4, Received = 4, Lost = 0\nC:\\>"
    )

    def send_and_wait(script, _timeout):
        if "enterCommand" in script:
            return json.dumps({"started": True, "before": before})
        if "owner_candidate_names" in script:
            return json.dumps({
                "found": True,
                "output": output,
                "owner_name": "PC-B",
                "owner_evidence": evidence,
                "owner_candidates": 1,
            })
        return json.dumps({"found": True, "output": output})

    result = TypedPingExecutor(send_and_wait, timeout_seconds=0).ping(
        "PC-B", "10.0.50.10",
    )

    assert result.observed_device_name == ""
    assert result.device_identity_provenance == "not_observed"


# La red simulada ejecuta en node los scripts PRODUCTIVOS del ping, sin
# reescribirlos. Las terminales son objetos nuevos en cada llamada, como muestra
# la evidencia LIVE archivada (`cl===t` nunca coincidio); en el run c6075f0
# tampoco coincidio `dev===d`, pero se exige cada invariante con ambas
# semanticas de objeto device. Las transcripciones son sinteticas.
_SIMULATED_NETWORK_JS = r"""
const __hExecute = (index, command) => {
  const device = __hState.devices[index];
  device.output += command + (device.kind === 'pc'
    ? '\nPackets: Sent = 4, Received = 4, Lost = 0 (0% loss),\n'
    : '\nSuccess rate is 100 percent (5/5)\n') + device.prompt;
};
const __hTerminal = (index) => ({
  getOutput: () => __hState.devices[index].output,
  getPrompt: () => __hState.devices[index].prompt,
  enterCommand: (command) => {
    const routed = __hState.route[String(index)];
    __hExecute(routed === undefined ? index : routed, command);
    for (const extra of __hState.mirror) { __hExecute(extra, command); }
    if (__hState.prepend_on_command) {
      __hState.devices.unshift(__hState.prepend_on_command);
      __hState.prepend_on_command = null;
    }
  },
});
const __hDevices = new Map();
const __hDeviceAt = (index) => {
  if (index < 0 || index >= __hState.devices.length) { return null; }
  if (__hState.stable && __hDevices.has(index)) { return __hDevices.get(index); }
  const device = {getName: () => __hState.devices[index].name};
  if (__hState.devices[index].kind === 'pc') {
    device.getCommandPrompt = () => __hTerminal(index);
  } else {
    device.getCommandLine = () => __hTerminal(index);
  }
  if (__hState.stable) { __hDevices.set(index, device); }
  return device;
};
global.ipc = {network: () => ({
  getDevice: (name) => {
    const wanted = Object.prototype.hasOwnProperty.call(__hState.lookup, name)
      ? __hState.lookup[name] : name;
    const index = __hState.devices.findIndex((device) => device.name === wanted);
    return index < 0 ? null : __hDeviceAt(index);
  },
  getDeviceCount: () => __hState.devices.length,
  getDeviceAt: (index) => __hDeviceAt(index),
})};
let __hReported = null;
global.reportResult = (value) => { __hReported = String(value); };
new Function(__hScript)();
process.stdout.write(JSON.stringify({reported: __hReported, state: __hState}));
"""


class _SimulatedPacketTracer:
    """Transporte `send_and_wait` respaldado por la red simulada."""

    def __init__(
        self, devices, *, stable_device_objects: bool, lookup=None, route=None,
        mirror=(), prepend_on_command=None, drop_snapshot: bool = False,
    ) -> None:
        self._state = {
            "devices": [dict(device) for device in devices],
            "stable": stable_device_objects,
            # Nombre pedido -> nombre del device que devuelve `getDevice`.
            "lookup": dict(lookup or {}),
            # Indice cuya terminal recibe el comando -> indice que lo ejecuta.
            "route": {str(index): target for index, target in (route or {}).items()},
            # Indices que ademas reciben el mismo comando en la misma ventana.
            "mirror": list(mirror),
            "prepend_on_command": prepend_on_command,
        }
        self._drop_snapshot = drop_snapshot
        self.scripts: list[str] = []

    def send_and_wait(self, script: str, _timeout: float) -> str | None:
        self.scripts.append(script)
        program = (
            "const __hState = " + json.dumps(self._state) + ";\n"
            "const __hScript = " + json.dumps(script) + ";\n"
            + _SIMULATED_NETWORK_JS
        )
        completed = subprocess.run(
            [shutil.which("node"), "-"],
            input=program,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        observed = json.loads(completed.stdout)
        self._state = observed["state"]
        reported = observed["reported"]
        if self._drop_snapshot and reported and reported.startswith("{"):
            value = json.loads(reported)
            if isinstance(value, dict) and "snapshot" in value:
                del value["snapshot"]
                reported = json.dumps(value)
        return reported


_PC_BANNER = "Synthetic PC banner\nC:\\>"
_PING_REPLY = "\nPackets: Sent = 4, Received = 4, Lost = 0 (0% loss),\nC:\\>"
_PING = "ping 172.17.10.8"


def _pc(name: str, *history: str) -> dict:
    return {
        "name": name, "kind": "pc", "prompt": "C:\\>",
        "output": _PC_BANNER + "".join(item + _PING_REPLY for item in history),
    }


def _simulated_ping(simulated: _SimulatedPacketTracer):
    return TypedPingExecutor(
        simulated.send_and_wait, timeout_seconds=0, sleeper=lambda _seconds: None,
    ).ping("LARGE-PC", "172.17.10.8")


_NEEDS_NODE = pytest.mark.skipif(
    shutil.which("node") is None, reason="Node is unavailable",
)

# (red simulada, (procedencia, nombre observado, candidatos, rechazo))
_DISPATCH_ATTRIBUTION = {
    # Forma LIVE de Router3 (runs b1cdfee y 759807): otro PC ya habia ejecutado
    # el MISMO ping sobre el mismo banner, y las transcripciones quedan iguales.
    "same-ping-already-in-another-transcript": (
        {"devices": [_pc("MULTI-PC", _PING), _pc("SMALL-PC", "ping 172.18.10.13"),
                     _pc("LARGE-PC")]},
        ("confirmed_unique", "LARGE-PC", {"LARGE-PC"}, "none"),
    ),
    "ping-lands-on-another-terminal": (
        {"devices": [_pc("MULTI-PC"), _pc("LARGE-PC")], "route": {1: 0}},
        ("mismatched", "MULTI-PC", {"MULTI-PC"}, "none"),
    ),
    "lookup-resolves-another-pc": (
        {"devices": [_pc("MULTI-PC", _PING), _pc("LARGE-PC", _PING)],
         "lookup": {"LARGE-PC": "MULTI-PC"}},
        ("mismatched", "MULTI-PC", {"MULTI-PC"}, "none"),
    ),
    "same-ping-reaches-two-terminals": (
        {"devices": [_pc("MULTI-PC"), _pc("LARGE-PC")], "mirror": [0]},
        ("ambiguous", "", {"MULTI-PC", "LARGE-PC"}, "none"),
    ),
    "owner-name-not-unique": (
        {"devices": [_pc("LARGE-PC"), _pc("LARGE-PC", _PING)]},
        ("ambiguous", "", {"LARGE-PC"}, "none"),
    ),
    "device-added-ahead-during-query": (
        {"devices": [_pc("MULTI-PC", _PING), _pc("LARGE-PC")],
         "prepend_on_command": _pc("LATE-PC")},
        ("confirmed_unique", "LARGE-PC", {"LARGE-PC"}, "none"),
    ),
    # Sin huella no hay autoridad: ni con colision ni sin ella se vuelve a la
    # continuidad de transcripcion que Router3 ya falso.
    "snapshot-unavailable-with-collision": (
        {"devices": [_pc("MULTI-PC", _PING), _pc("LARGE-PC")], "drop_snapshot": True},
        ("not_observed", "", set(), "dispatch_snapshot_unavailable"),
    ),
    "snapshot-unavailable-without-collision": (
        {"devices": [_pc("MULTI-PC"), _pc("LARGE-PC")], "drop_snapshot": True},
        ("not_observed", "", set(), "dispatch_snapshot_unavailable"),
    ),
}


@_NEEDS_NODE
@pytest.mark.parametrize(
    "stable_device_objects", [True, False],
    ids=["stable-device-objects", "fresh-device-objects"],
)
@pytest.mark.parametrize(
    ("network", "expected"), list(_DISPATCH_ATTRIBUTION.values()),
    ids=list(_DISPATCH_ATTRIBUTION),
)
def test_typed_ping_identity_is_the_terminal_that_changed_during_dispatch(
    network, expected, stable_device_objects,
):
    """Ni el nombre pedido ni el objeto que devolvio su busqueda son prueba."""
    result = _simulated_ping(_SimulatedPacketTracer(
        stable_device_objects=stable_device_objects, **network,
    ))

    provenance, observed, candidates, refusal = expected
    assert result.device_identity_provenance == provenance
    assert result.observed_device_name == observed
    assert set(result.device_identity_candidate_names) == candidates
    assert result.device_identity_refusal == refusal
    if provenance == "confirmed_unique":
        assert result.fresh_output_observed and result.reachable
        assert result.device_identity_evidence == "dispatch_transcript_delta"
    if provenance == "mismatched":
        assert not result.fresh_output_observed


@_NEEDS_NODE
def test_dispatch_evidence_does_not_grow_with_unrelated_transcripts():
    """290 devices en vivo: la huella no puede cargar cada transcripcion ajena."""

    def attribution_script_length(idle_devices: int) -> int:
        idle = [
            {"name": f"IDLE-{index:03d}", "kind": "ios", "prompt": "Router>",
             "output": "Synthetic router log line\n" * 80 + "Router>"}
            for index in range(idle_devices)
        ]
        simulated = _SimulatedPacketTracer(
            [*idle, _pc("MULTI-PC", _PING), _pc("LARGE-PC")],
            stable_device_objects=False,
        )
        result = _simulated_ping(simulated)
        assert result.device_identity_provenance == "confirmed_unique"
        return max(
            len(script) for script in simulated.scripts
            if "owner_candidate_names" in script
        )

    growth = attribution_script_length(40) - attribution_script_length(0)

    # Un device que no contiene el comando solo aporta su nombre al script.
    assert growth / 40 < 64


def test_typed_ping_recognizes_fresh_ios_success_rate_output():
    scripts: list[str] = []
    before = "Router#"
    output = (
        before
        + "ping 10.0.50.10\n"
        + "Success rate is 80 percent (4/5), round-trip min/avg/max = 1/2/4 ms\n"
        + "Router#"
    )

    def send_and_wait(script, _timeout):
        scripts.append(script)
        if "enterCommand" in script:
            return json.dumps({"started": True, "before": before})
        return json.dumps({"found": True, "output": output})

    result = TypedPingExecutor(send_and_wait, timeout_seconds=0).ping(
        "HQ-R1", "10.0.50.10",
    )

    assert result.reachable
    assert result.fresh_output_observed
    assert result.window_strategy == "prefix_delta"
    assert "getCommandLine" in next(
        script for script in scripts if "enterCommand" in script
    )


def test_typed_ping_rejects_noncanonical_source_before_bridge_call():
    scripts: list[str] = []

    result = TypedPingExecutor(
        lambda script, _timeout: scripts.append(script) or None,
    ).ping(" HQ-R1", "10.0.50.10")

    assert not result.reachable
    assert not result.fresh_output_observed
    assert result.failure_reason == "invalid_source_device"
    assert scripts == []


@pytest.mark.parametrize(
    "kwargs",
    [
        {"timeout_seconds": -0.1},
        {"interval_seconds": -0.1},
    ],
)
def test_typed_ping_rejects_negative_wait_budgets(kwargs):
    with pytest.raises(ValueError):
        TypedPingExecutor(lambda _script, _timeout: None, **kwargs)
NEWLINE = chr(10)


# Prompt sin backslash: la ventana no depende de su forma exacta.
_BEFORE = "PC>"
_ANSWERED = (
    _BEFORE + "ping 198.18.140.1" + NEWLINE
    + "Packets: Sent = 4, Received = 4, Lost = 0" + NEWLINE + _BEFORE
)
_UNANSWERED = (
    _BEFORE + "ping 198.18.140.1" + NEWLINE
    + "Packets: Sent = 4, Received = 0, Lost = 4" + NEWLINE + _BEFORE
)


def _endpoint_that_attributes_on_attempt(n: int, answered: str = _ANSWERED):
    """Guiona un endpoint cuya ventana solo es atribuible en el intento n.

    Reproduce lo medido contra PT 9.0.1.0858: un PC ya listo devolvio
    ``no_fresh_ping_result`` y despues ``current_ping_echo_not_observed``
    antes de entregar una ventana valida al tercer intento.
    """
    state = {"attempt": 0, "commands": 0}

    def send_and_wait(script, _timeout):
        if "enterCommand" in script:
            state["attempt"] += 1
            state["commands"] += 1
            return json.dumps({"started": True, "before": _BEFORE})
        if state["attempt"] < n:
            return json.dumps({"found": True, "output": _BEFORE})
        return json.dumps({"found": True, "output": answered})

    send_and_wait.state = state
    return send_and_wait


def test_a_single_attempt_stays_the_default_for_existing_callers():
    result = TypedPingExecutor(
        _endpoint_that_attributes_on_attempt(3), timeout_seconds=0,
    ).ping("PC0", "198.18.140.1")

    assert not result.fresh_output_observed
    assert result.attempts == 1


def test_bounded_attempts_recover_an_endpoint_that_attributes_late():
    result = TypedPingExecutor(
        _endpoint_that_attributes_on_attempt(3),
        timeout_seconds=0, measurement_attempts=4, sleeper=lambda _s: None,
    ).ping("PC0", "198.18.140.1")

    assert result.reachable
    assert result.fresh_output_observed
    assert result.attempts == 3


def test_attempts_stop_at_the_declared_budget():
    result = TypedPingExecutor(
        _endpoint_that_attributes_on_attempt(99),
        timeout_seconds=0, measurement_attempts=3, sleeper=lambda _s: None,
    ).ping("PC0", "198.18.140.1")

    assert not result.fresh_output_observed
    assert result.attempts == 3


def test_a_fresh_unreachable_result_is_not_retried():
    """El reintento busca evidencia atribuible, nunca un resultado favorable."""
    endpoint = _endpoint_that_attributes_on_attempt(1, answered=_UNANSWERED)

    result = TypedPingExecutor(
        endpoint, timeout_seconds=0, measurement_attempts=5,
        sleeper=lambda _s: None,
    ).ping("PC0", "198.18.140.1")

    assert not result.reachable
    assert result.fresh_output_observed
    assert result.attempts == 1
    assert endpoint.state["commands"] == 1


def test_a_non_positive_attempt_budget_is_rejected():
    with pytest.raises(ValueError):
        TypedPingExecutor(lambda _s, _t: None, measurement_attempts=0)
