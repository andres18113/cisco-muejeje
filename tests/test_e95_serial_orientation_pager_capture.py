"""Stage 3A4 — bounded multi-page capture for the registered serial controller.

TD-ORIENTATION-PAGER-001, branch A. MEG-4 run 3 reached serial orientation and
refused both endpoints because `show controllers Serial0/0/0` on a 2911 with an
HWIC-2T exceeds one page on PT 9.0.1.0858, and that build rejects
`terminal length 0` (`ios_terminal.py:462`, `:1153`, `command_dispatch.py:154`).

This slice qualifies one thing: the registered `SHOW_CONTROLLERS_SERIAL` query
may walk its own pager until the output closes at a prompt. Pager traversal is
always allow-listed by registered query id; other independently qualified
queries, including trunk and ephone observation, retain their own regressions.
An unqualified pager still means truncated and the claim ceiling still applies.

The fakes below drive the real `ControlledIosExecutor` through the same JS
bridge the production path uses. Nothing here assigns `truncated_by_pager` or a
DCE/DTE role directly into a result: the orientation has to come out of the
capture or not at all.
"""

from __future__ import annotations

import json

import pytest

from src.packet_tracer_mcp.application.use_cases.execute_enterprise_reference import (
    EnterpriseExecutionStage,
    EnterpriseExecutionStatus,
    EnterpriseRuntimes,
    execute_enterprise_reference,
)
from src.packet_tracer_mcp.application.use_cases.compose_enterprise_reference import (
    compose_enterprise_reference,
)
from src.packet_tracer_mcp.application.use_cases.observe_serial_orientation import (
    SerialControllerObservation,
    SerialOrientationObserver,
    SerialOrientationStatus,
)
from src.packet_tracer_mcp.domain.enterprise.models.deployment import (
    SerialEndpointOrientation,
)
from src.packet_tracer_mcp.infrastructure.execution.ios_terminal import (
    ControlledIosExecutor,
    OperationalQueryId,
    PagerContinuation,
)
from src.packet_tracer_mcp.infrastructure.execution.serial_orientation_runtime import (
    PacketTracerSerialOrientationRuntime,
)
from tests.test_e95_serial_orientation_observer import _manifest, _topology
from tests.test_enterprise_reference_execution import _isolated_preflight
from tests.test_stage3a4_offline_adversarial_matrix import (
    FINGERPRINT,
    _QUALIFIED,
    _bounded_intent,
    _control_plane_intent,
    _ForbiddenControlPlaneRuntime,
    _GenericPhysicalRuntime,
)

_MORE = "--More--"
_COMMAND = "show controllers Serial0/0/0"

#: Forma medida en PT 9.0.1.0858 (Slice 2A y MEG-4 run 3): el DCE reporta su
#: reloj, el DTE no tiene reloj propio. Los registros SCC posteriores son lo
#: que empuja la salida mas alla de una pagina.
_PAGE_HEAD = (
    "Interface Serial0/0/0\n"
    "Hardware is GT96K\n"
)
_PAGE_ROLE_DCE = "DCE V.35, clock rate 2000000\n"
_PAGE_ROLE_DTE = "DTE V.35 TX and RX clocks detected\n"
_PAGE_REGISTERS = (
    "idb at 0x1A2B3C40, driver data structure at 0x1A2B4E80\n"
    "SCC Registers:\n"
    "General [GSMR]=0x2:0x00000000, Protocol-specific [PSMR]=0x8\n"
    "Events [SCCE]=0x0000, Mask [SCCM]=0x001F, Status [SCCS]=0x00\n"
)
_PAGE_BUFFERS = (
    "Transmit on Demand [TODR]=0x0, Data Sync [DSR]=0x7E7E\n"
    "Interrupt Registers:\n"
    "Config [CICR]=0x00367F80, Pending [CIPR]=0x00000000\n"
    "Mask   [CIMR]=0x40204000, In-srv [CISR]=0x00000000\n"
)


def _dce_pages() -> list[str]:
    return [_PAGE_HEAD + _PAGE_ROLE_DCE, _PAGE_REGISTERS, _PAGE_BUFFERS]


def _dte_pages() -> list[str]:
    return [_PAGE_HEAD + _PAGE_ROLE_DTE, _PAGE_REGISTERS, _PAGE_BUFFERS]


class _FakeClock:
    """Reloj inyectado: la espera acotada se mide, no se duerme."""

    def __init__(self, step: float = 0.5) -> None:
        self.step = step
        self.now = 0.0

    def __call__(self) -> float:
        value = self.now
        self.now += self.step
        return value


class _PagedTerminal:
    """TerminalLine falso con la mecanica de paginado medida en PT 9.0.1.0858.

    Entre pagina y pagina IOS imprime su propio `--More--` y espera exactamente
    una tecla; al recibirla borra el marcador y sigue imprimiendo. Esa
    reescritura de cola es la que `fresh_command_window` ya sabe atribuir.
    """

    def __init__(
        self,
        pages: list[str],
        *,
        prompt: str = "Router#",
        command: str = _COMMAND,
        final_tail: str | None = None,
    ) -> None:
        self.pages = list(pages)
        self.prompt = prompt
        self.command = command
        self.final_tail = prompt if final_tail is None else final_tail
        self.output = prompt
        self.index = -1
        self.sent: list[str] = []
        self.advances = 0
        self.cancels = 0

    # -- mecanica del pager -------------------------------------------------
    def _tail(self) -> str:
        return _MORE if self.index < len(self.pages) - 1 else self.final_tail

    def _emit_first_page(self) -> None:
        self.index = 0
        self.output += self.command + "\n" + self.pages[0] + self._tail()

    def _advance(self) -> None:
        if self.index >= len(self.pages) - 1:
            return
        self.output = self.output[: -len(_MORE)]
        self.index += 1
        self.output += self.pages[self.index] + self._tail()

    def _state(self) -> str:
        return json.dumps({
            "found": True, "booting": False, "terminal": True,
            "prompt": self.prompt, "output": self.output,
        })

    def __call__(self, js: str, _timeout: float) -> str:
        self.sent.append(js)
        if "String.fromCharCode(32)" in js:
            self.advances += 1
            self._advance()
            return '{"ok":true}'
        if "String.fromCharCode(3)" in js:
            self.cancels += 1
            self.output += "\n^C\n" + self.prompt
            return '{"ok":true}'
        if "terminal_kind:'ios_command_line'" in js:
            return self._state()
        if "var before=String(t.getOutput())" in js:
            before = self.output
            self._emit_first_page()
            return json.dumps({"ok": True, "before": before})
        if "configuration_channel" in js:
            return json.dumps({
                "found": True, "configuration_channel": True,
                "output": self.output,
            })
        raise AssertionError(f"Unexpected terminal interaction: {js}")


class _StallingTerminal(_PagedTerminal):
    """La tecla se entrega y el pager no imprime nunca la pagina siguiente."""

    def _advance(self) -> None:
        return


class _RepeatingTerminal(_PagedTerminal):
    """El pager reimprime exactamente la misma pagina: no hay progreso real."""

    def _advance(self) -> None:
        self.output = self.output[: -len(_MORE)] + self.pages[self.index] + _MORE


class _EndlessTerminal(_PagedTerminal):
    """Un pager que nunca llega al prompt."""

    def __init__(self, *args, width: int = 0, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._width = width

    def _advance(self) -> None:
        # Cada pagina es distinta de la anterior: lo que corta esta corrida es
        # la cota bajo prueba, no la guarda de pagina repetida.
        chunk = f"register line {self.advances}".ljust(self._width) + "\n"
        self.output = self.output[: -len(_MORE)] + chunk + _MORE


class _RefusingTerminal(_PagedTerminal):
    """El bridge no confirma la entrega de la tecla de continuacion."""

    def __call__(self, js: str, timeout: float) -> str:
        if "String.fromCharCode(32)" in js:
            self.sent.append(js)
            self.advances += 1
            return '{"ok":false}'
        return super().__call__(js, timeout)


class _ForeignTranscriptTerminal(_PagedTerminal):
    """La observacion siguiente trae un transcript que no continua a este."""

    def _advance(self) -> None:
        self.output = "Switch#show vlan brief\nVLAN Name Status\nSwitch#"


class _RollingPagedTerminal(_PagedTerminal):
    """The terminal drops its head while erasing the active pager marker."""

    def __init__(self, *args, max_chars: int, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.max_chars = max_chars

    def _advance(self) -> None:
        super()._advance()
        if len(self.output) > self.max_chars:
            self.output = self.output[-self.max_chars:]


class _AnsiPagedTerminal(_PagedTerminal):
    marker = "\x1b[31m--More--\x1b[0m"

    def _tail(self) -> str:
        return self.marker if self.index < len(self.pages) - 1 else self.final_tail

    def _advance(self) -> None:
        if self.index >= len(self.pages) - 1:
            return
        self.output = self.output[:-len(self.marker)]
        self.index += 1
        self.output += self.pages[self.index] + self._tail()


class _SyslogPagedTerminal(_PagedTerminal):
    marker = (
        "--More-- %SPANTREE-2-LOOPGUARD_BLOCK: event\n"
        "%LINK-3-UPDOWN: interface changed\n"
    )

    def _tail(self) -> str:
        return self.marker if self.index < len(self.pages) - 1 else self.final_tail

    def _advance(self) -> None:
        if self.index >= len(self.pages) - 1:
            return
        self.output = self.output[:-len(self.marker)]
        self.index += 1
        self.output += self.pages[self.index] + self._tail()


class _TransitionalPagedTerminal(_PagedTerminal):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.pending = ""

    def _advance(self) -> None:
        if self.index >= len(self.pages) - 1:
            return
        self.output = self.output[:-len(_MORE)]
        self.index += 1
        self.pending = self.pages[self.index] + self._tail()

    def __call__(self, js: str, timeout: float) -> str:
        if "terminal_kind:'ios_command_line'" in js and self.pending:
            state = self._state()
            self.output += self.pending
            self.pending = ""
            self.sent.append(js)
            return state
        return super().__call__(js, timeout)


class _SyslogBeforePageTerminal(_PagedTerminal):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.pending = ""

    def _advance(self) -> None:
        if self.index >= len(self.pages) - 1:
            return
        self.index += 1
        self.output += " %LINK-3-UPDOWN: transient event\n"
        self.pending = self.pages[self.index] + self._tail()

    def __call__(self, js: str, timeout: float) -> str:
        if "terminal_kind:'ios_command_line'" in js and self.pending:
            state = self._state()
            marker = self.output.rfind(_MORE)
            self.output = self.output[:marker] + self.pending
            self.pending = ""
            self.sent.append(js)
            return state
        return super().__call__(js, timeout)


class _SyslogOnlyPagedTerminal(_PagedTerminal):
    def _advance(self) -> None:
        self.output += " %LINK-3-UPDOWN: transient event\n"


class _SwitchedSessionTerminal(_PagedTerminal):
    """El transcript sigue creciendo pero el prompt ya es de otro equipo."""

    def _advance(self) -> None:
        super()._advance()
        self.prompt = "Switch#"


def _executor(terminal, *, step: float = 0.5) -> ControlledIosExecutor:
    return ControlledIosExecutor(
        terminal, clock=_FakeClock(step=step), sleeper=lambda _seconds: None,
    )


def _execute(terminal, *, step: float = 0.5):
    return _executor(terminal, step=step).execute(
        "MCP-R1",
        OperationalQueryId.SHOW_CONTROLLERS_SERIAL,
        interface="Serial0/0/0",
    )


# --------------------------------------------------------------------------
# 1-4: la captura logica completa
# --------------------------------------------------------------------------


def test_a_single_page_controller_query_still_succeeds_without_continuation():
    terminal = _PagedTerminal([_PAGE_HEAD + _PAGE_ROLE_DCE])

    result = _execute(terminal)

    assert result.executed and result.fresh_output_observed
    assert result.output_complete
    assert not result.truncated_by_pager
    assert result.pager_pages_captured == 1
    assert result.pager_continuation == PagerContinuation.NOT_ENCOUNTERED.value
    assert terminal.advances == 0
    assert terminal.cancels == 0
    assert not any("terminal length 0" in item for item in terminal.sent)


def test_one_pager_boundary_is_continued_into_one_complete_logical_result():
    terminal = _PagedTerminal([_PAGE_HEAD + _PAGE_ROLE_DCE, _PAGE_REGISTERS])

    result = _execute(terminal)

    assert result.executed and result.output_complete
    assert not result.truncated_by_pager
    assert result.pager_pages_captured == 2
    assert result.pager_continuation == PagerContinuation.COMPLETED.value
    assert terminal.advances == 1
    # El marcador lo escribio el pager, no el dispositivo: no puede quedar
    # dentro de la lectura logica reconstruida.
    assert _MORE not in result.output
    assert "clock rate 2000000" in result.output
    assert "SCC Registers:" in result.output
    assert result.output.rstrip().endswith("Router#")


def test_next_page_leading_dash_is_not_consumed_with_pager_marker():
    terminal = _PagedTerminal(["first page\n", "-second page\n"])

    result = _execute(terminal)

    assert result.executed
    assert result.output_complete
    assert "-second page" in result.output


def test_ansi_decorated_pager_marker_enters_registered_capture():
    terminal = _AnsiPagedTerminal(["first page\n", "second page\n"])

    result = _execute(terminal)

    assert result.executed
    assert result.output_complete
    assert result.pager_pages_captured == 2
    assert terminal.advances == 1
    assert "first page" in result.output
    assert "second page" in result.output


def test_syslogs_after_pager_marker_still_enter_registered_capture():
    terminal = _SyslogPagedTerminal(["first page\n", "second page\n"])

    result = _execute(terminal)

    assert result.executed
    assert result.output_complete
    assert result.pager_pages_captured == 2
    assert terminal.advances == 1
    assert "second page" in result.output


def test_pager_progress_waits_past_marker_erasure_for_complete_page():
    terminal = _TransitionalPagedTerminal(["first page\n", "second page\n"])

    result = _execute(terminal)

    assert result.executed
    assert result.output_complete
    assert result.pager_pages_captured == 2
    assert terminal.advances == 1
    assert "second page" in result.output


def test_pager_progress_ignores_syslog_before_next_page():
    terminal = _SyslogBeforePageTerminal(["first page\n", "second page\n"])

    result = _execute(terminal)

    assert result.executed
    assert result.output_complete
    assert result.pager_pages_captured == 2
    assert terminal.advances == 1
    assert "second page" in result.output
    assert "transient event" not in result.output


def test_timed_out_syslog_only_growth_is_never_ingested_as_a_page():
    terminal = _SyslogOnlyPagedTerminal(["first page\n", "second page\n"])

    result = _execute(terminal)

    assert result.executed
    assert not result.output_complete
    assert result.pager_pages_captured == 1
    assert terminal.advances == 1
    assert "no command continuation page" in result.failure_reason.casefold()
    assert "transient event" not in result.output


def test_pager_capture_survives_combined_head_roll_and_marker_rewrite():
    pages = [
        f"PAGE-{index}\n" + chr(64 + index) * 500 + "\n"
        for index in range(1, 5)
    ]
    terminal = _RollingPagedTerminal(pages, max_chars=1_200)

    result = _execute(terminal)

    assert result.executed
    assert result.output_complete
    assert result.pager_pages_captured == 4
    assert result.pager_continuation == PagerContinuation.COMPLETED.value
    assert all(f"PAGE-{index}" in result.output for index in range(1, 5))


def test_multiple_pages_reconstruct_deterministically():
    first = _execute(_PagedTerminal(_dce_pages()))
    second = _execute(_PagedTerminal(_dce_pages()))

    assert first.output == second.output
    assert first.pager_pages_captured == second.pager_pages_captured == 3
    assert first.output_complete and second.output_complete
    expected = "".join(_dce_pages())
    assert expected in first.output.replace("\r", "")


def test_a_role_line_split_across_a_page_boundary_parses_only_when_complete():
    """La linea DCE queda partida por el pager; ninguna pagina sola la dice."""
    pages = [_PAGE_HEAD + "DCE V.3", "5, clock rate 2000000\n" + _PAGE_REGISTERS]
    runtime = PacketTracerSerialOrientationRuntime(
        lambda _script, _timeout: None,
        ios_executor=_executor(_PagedTerminal(pages)),
    )

    observed = runtime.observe_serial_controller("MCP-R1", "Serial0/0/0")

    assert observed.observed
    assert observed.complete and observed.pages_captured == 2
    assert observed.orientation is SerialEndpointOrientation.DCE
    assert observed.clock_rate_bps == 2_000_000


def test_a_first_page_carrying_the_role_is_refused_when_the_capture_cannot_finish():
    """El rol esta en la pagina 1 y aun asi no se lee: incompleto es incompleto."""
    terminal = _StallingTerminal(_dce_pages())
    runtime = PacketTracerSerialOrientationRuntime(
        lambda _script, _timeout: None,
        ios_executor=_executor(terminal, step=1.0),
    )

    observed = runtime.observe_serial_controller("MCP-R1", "Serial0/0/0")

    assert "DCE V.35, clock rate 2000000" in terminal.output
    assert not observed.observed
    assert not observed.complete
    assert observed.truncated
    assert observed.orientation is SerialEndpointOrientation.UNRESOLVED
    assert observed.clock_rate_bps is None


# --------------------------------------------------------------------------
# 6-12: cotas y fallo cerrado
# --------------------------------------------------------------------------


def test_a_page_that_never_arrives_fails_closed():
    terminal = _StallingTerminal(_dce_pages())

    result = _execute(terminal, step=1.0)

    assert not result.output_complete
    assert result.truncated_by_pager
    assert result.pager_continuation == PagerContinuation.FAILED.value
    assert "no continuation page" in result.failure_reason.casefold()
    # Aislar el terminal sigue siendo obligatorio tras fallar la captura.
    assert terminal.cancels == 1


def test_a_repeated_identical_page_fails_closed():
    terminal = _RepeatingTerminal(_dce_pages())

    result = _execute(terminal)

    assert not result.output_complete
    assert result.pager_continuation == PagerContinuation.FAILED.value
    assert "repeated" in result.failure_reason.casefold()


def test_the_bounded_page_limit_fails_closed():
    terminal = _EndlessTerminal(_dce_pages())

    result = _execute(terminal)

    assert not result.output_complete
    assert result.pager_continuation == PagerContinuation.FAILED.value
    assert "page limit" in result.failure_reason.casefold()
    assert terminal.advances < 32


def test_the_bounded_byte_limit_fails_closed():
    terminal = _EndlessTerminal(_dce_pages(), width=9000)

    result = _execute(terminal)

    assert not result.output_complete
    assert result.pager_continuation == PagerContinuation.FAILED.value
    assert "byte limit" in result.failure_reason.casefold()


def test_the_bounded_capture_deadline_fails_closed():
    terminal = _EndlessTerminal(_dce_pages())

    result = _execute(terminal, step=10.0)

    assert not result.output_complete
    assert result.pager_continuation == PagerContinuation.FAILED.value
    assert "deadline" in result.failure_reason.casefold()


def test_a_continuation_key_that_is_not_confirmed_fails_closed():
    terminal = _RefusingTerminal(_dce_pages())

    result = _execute(terminal)

    assert not result.output_complete
    assert "continuation key" in result.failure_reason.casefold()


def test_a_foreign_transcript_fails_closed():
    terminal = _ForeignTranscriptTerminal(_dce_pages())

    result = _execute(terminal)

    assert not result.output_complete
    assert result.pager_continuation == PagerContinuation.FAILED.value
    assert "attribut" in result.failure_reason.casefold()


def test_a_changed_terminal_session_fails_closed():
    terminal = _SwitchedSessionTerminal(_dce_pages())

    result = _execute(terminal)

    assert not result.output_complete
    assert "session" in result.failure_reason.casefold()


def test_a_capture_that_ends_without_a_prompt_is_ambiguous_and_fails_closed():
    terminal = _PagedTerminal(_dce_pages(), final_tail="")

    result = _execute(terminal)

    assert not result.output_complete
    assert result.pager_continuation == PagerContinuation.FAILED.value
    assert "prompt" in result.failure_reason.casefold()


def test_complete_output_for_another_interface_fails_closed():
    pages = [
        _PAGE_HEAD.replace("Serial0/0/0", "Serial0/0/1") + _PAGE_ROLE_DCE,
        _PAGE_REGISTERS,
    ]
    runtime = PacketTracerSerialOrientationRuntime(
        lambda _script, _timeout: None,
        ios_executor=_executor(_PagedTerminal(pages)),
    )

    observed = runtime.observe_serial_controller("MCP-R1", "Serial0/0/0")

    assert observed.complete and observed.parseable
    assert not observed.interface_identity_match
    assert not observed.observed


def test_an_unqualified_registered_query_is_never_continued():
    """La cualificacion es por consulta registrada, no por encontrar un pager."""
    terminal = _PagedTerminal(
        ["Interface IP-Address OK? Method Status Protocol\n", "Vlan1 unassigned\n"],
        command="show ip interface brief",
    )

    result = _executor(terminal).execute(
        "MCP-R1", OperationalQueryId.SHOW_IP_INTERFACE_BRIEF,
    )

    assert result.truncated_by_pager
    assert not result.output_complete
    assert result.pager_pages_captured == 1
    assert result.pager_continuation == PagerContinuation.NOT_QUALIFIED.value
    assert terminal.advances == 0
    assert terminal.cancels == 1


def test_the_registered_trunk_query_reaches_its_forwarding_vlan_section():
    terminal = _PagedTerminal(
        [
            (
                "Port Mode Encapsulation Status Native vlan\n"
                "Gig0/1 on 802.1q trunking 1\n"
                "Port Vlans allowed on trunk\n"
                "Gig0/1 10,20,30\n"
            ),
            (
                "Port Vlans allowed and active in management domain\n"
                "Gig0/1 10,20,30\n"
                "Port Vlans in spanning tree forwarding state and not pruned\n"
                "Gig0/1 10,20,30\n"
            ),
        ],
        prompt="Switch#",
        command="show interfaces trunk",
    )

    result = _executor(terminal).execute(
        "MCP-SW1", OperationalQueryId.SHOW_INTERFACES_TRUNK,
    )

    assert result.executed and result.output_complete
    assert result.pager_continuation == PagerContinuation.COMPLETED.value
    assert result.pager_pages_captured == 2
    assert "Vlans in spanning tree forwarding state and not pruned" in result.output
    assert terminal.advances == 1


# --------------------------------------------------------------------------
# 13-16: la orientacion de dos extremos sobre la captura real
# --------------------------------------------------------------------------


def _paged_orientation_runtime(pages_by_device: dict[str, list[str]]):
    class _Runtime:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str]] = []

        def observe_serial_controller(self, device_name: str, interface: str):
            self.calls.append((device_name, interface))
            terminal = _PagedTerminal(pages_by_device[device_name])
            return PacketTracerSerialOrientationRuntime(
                lambda _script, _timeout: None,
                ios_executor=_executor(terminal),
            ).observe_serial_controller(device_name, interface)

    return _Runtime()


def test_two_paged_endpoints_orient_one_serial_link():
    topology = _topology()
    manifest = _manifest(topology)
    runtime = _paged_orientation_runtime({
        "MCP-R1": _dce_pages(), "MCP-R2": _dte_pages(),
    })

    result = SerialOrientationObserver(runtime).observe(topology, manifest)

    assert result.status is SerialOrientationStatus.VERIFIED
    assert result.oriented_manifest is not None
    assert [item.pages_captured for item in result.observations] == [3, 3]
    assert all(item.complete for item in result.observations)
    assert result.oriented_manifest.physical_topology_hash == (
        topology.physical_identity_hash
    )


@pytest.mark.parametrize("role", [_PAGE_ROLE_DCE, _PAGE_ROLE_DTE])
def test_two_paged_endpoints_of_the_same_role_fail_closed(role: str):
    topology = _topology()
    manifest = _manifest(topology)
    pages = [_PAGE_HEAD + role, _PAGE_REGISTERS, _PAGE_BUFFERS]
    runtime = _paged_orientation_runtime({"MCP-R1": pages, "MCP-R2": list(pages)})

    result = SerialOrientationObserver(runtime).observe(topology, manifest)

    assert result.status is SerialOrientationStatus.FAILED
    assert result.oriented_manifest is None
    assert len(runtime.calls) == 2


def test_one_complete_endpoint_and_one_truncated_endpoint_fail_closed():
    topology = _topology()
    manifest = _manifest(topology)

    class _MixedRuntime:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str]] = []

        def observe_serial_controller(self, device_name: str, interface: str):
            self.calls.append((device_name, interface))
            terminal = (
                _PagedTerminal(_dce_pages()) if device_name == "MCP-R1"
                else _StallingTerminal(_dte_pages())
            )
            step = 0.5 if device_name == "MCP-R1" else 1.0
            return PacketTracerSerialOrientationRuntime(
                lambda _script, _timeout: None,
                ios_executor=_executor(terminal, step=step),
            ).observe_serial_controller(device_name, interface)

    runtime = _MixedRuntime()
    result = SerialOrientationObserver(runtime).observe(topology, manifest)

    assert result.status is SerialOrientationStatus.FAILED
    assert result.oriented_manifest is None
    assert [item.complete for item in result.observations] == [True, False]


def test_a_complete_capture_with_contradictory_role_evidence_fails_closed():
    """Un DTE que reporta reloj propio es ambiguo, aunque la captura cerrara."""
    pages = [
        _PAGE_HEAD + "DTE V.35 TX and RX clocks detected, clock rate 2000000\n",
        _PAGE_REGISTERS,
    ]
    runtime = PacketTracerSerialOrientationRuntime(
        lambda _script, _timeout: None,
        ios_executor=_executor(_PagedTerminal(pages)),
    )

    observed = runtime.observe_serial_controller("MCP-R1", "Serial0/0/0")

    assert observed.complete and observed.pages_captured == 2
    assert not observed.observed
    assert observed.orientation is SerialEndpointOrientation.UNRESOLVED


# --------------------------------------------------------------------------
# 17-20: lo que un fallo de paginado NO puede tocar
# --------------------------------------------------------------------------


class _ForbiddenConfigurationRuntime:
    def __getattr__(self, name):
        def _forbidden(*_args, **_kwargs):
            raise AssertionError(
                f"configuration.{name} must not be reached after a failed "
                "serial orientation",
            )
        return _forbidden


class _PagerBlockedOrientationRuntime:
    """Lo que el producto observa cuando la captura acotada no puede cerrar."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def observe_serial_controller(self, device_name: str, interface: str):
        self.calls.append((device_name, interface))
        return PacketTracerSerialOrientationRuntime(
            lambda _script, _timeout: None,
            ios_executor=_executor(_StallingTerminal(_dce_pages()), step=1.0),
        ).observe_serial_controller(device_name, interface)


def _run_with_blocked_orientation(*, preexisting: list[str] | None = None):
    intent = _bounded_intent()
    topology = compose_enterprise_reference(
        intent, policy=_QUALIFIED, packet_tracer_version="9.0.1.0858",
    ).topology
    physical = _GenericPhysicalRuntime(preexisting=preexisting or [])
    physical.bind(topology)
    orientation = _PagerBlockedOrientationRuntime()
    result = execute_enterprise_reference(
        intent,
        EnterpriseRuntimes(
            physical=physical,
            serial_orientation=orientation,
            configuration=_ForbiddenConfigurationRuntime(),
            control_plane=_ForbiddenControlPlaneRuntime(),
        ),
        _control_plane_intent(topology),
        environment_fingerprint=FINGERPRINT,
        import_preflight=_isolated_preflight(),
        packet_tracer_version="9.0.1.0858",
        policy=_QUALIFIED,
    )
    return result, physical, orientation


def test_a_pager_blocked_orientation_stops_exactly_at_serial_orientation():
    result, _physical, orientation = _run_with_blocked_orientation()

    assert result.status is EnterpriseExecutionStatus.FAILED
    assert result.stopped_at is EnterpriseExecutionStage.SERIAL_ORIENTATION
    assert orientation.calls
    assert any("pager" in item.casefold() for item in result.errors)


def test_a_pager_blocked_orientation_preserves_the_e4_identity():
    result, _physical, _orientation = _run_with_blocked_orientation()

    assert result.e4_identity_preserved is True


def test_cleanup_still_runs_after_a_pager_blocked_orientation():
    result, physical, _orientation = _run_with_blocked_orientation()

    assert result.cleanup_results
    assert result.final_inventory is not None
    assert physical.calls.count("observe_workspace") >= 2


def test_a_pager_blocked_orientation_never_removes_foreign_objects():
    result, physical, _orientation = _run_with_blocked_orientation()

    assert result.composition is not None
    planned = {item.name for item in result.composition.topology.devices}
    assert set(physical.removed) <= planned
    assert "Power Distribution Device0" not in physical.removed


class _CorruptingPagedTerminal(_PagedTerminal):
    """El terminal hace eco de un comando distinto del que se pidio."""

    def _emit_first_page(self) -> None:
        self.index = 0
        self.output += self.command[1:] + "\n" + self.pages[0] + self._tail()


def test_a_corrupted_dispatch_is_never_continued():
    """Si IOS recibio otra cosa, su pager no es el de la consulta pedida."""
    terminal = _CorruptingPagedTerminal(_dce_pages())

    result = _execute(terminal)

    assert not result.executed
    assert "COMMAND_DISPATCH_MISMATCH" in result.failure_reason
    assert not result.output_complete
    assert result.pager_continuation == PagerContinuation.NOT_QUALIFIED.value
    assert terminal.advances == 0
