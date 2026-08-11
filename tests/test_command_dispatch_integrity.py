"""Fault injection determinista sobre la frontera de despacho.

Ningun test de este archivo depende de reproducir la carrera real de Packet
Tracer: la corrupcion se inyecta, de modo que la clasificacion queda probada
aunque el backend no falle durante la corrida.
"""

import json
import re

from src.packet_tracer_mcp.infrastructure.execution.ios_terminal import (
    ControlledIosExecutor,
    OperationalQueryId,
)
from src.packet_tracer_mcp.infrastructure.execution.typed_ping import TypedPingExecutor
from src.packet_tracer_mcp.infrastructure.execution.command_dispatch import (
    DispatchClassification,
    FreshWindowStrategy,
    PromptReadiness,
    assess_prompt_readiness,
    classify_echo,
    first_echo_line,
    fresh_command_window,
    has_active_pager,
    is_command_corrupted,
    rendered_terminal_text,
    resolve_backspaces,
    terminal_is_idle,
)


# -- identidad del comando -------------------------------------------------

def test_lost_first_character_of_show_is_prefix_loss_not_a_rejection():
    """La evidencia real: se pidio `show ...` y el CLI recibio `how ...`."""
    window = "how controllers Serial0/0/1\n% Invalid input detected\nRouter#"

    classification, echoed = classify_echo("show controllers Serial0/0/1", window)

    assert classification is DispatchClassification.PREFIX_LOSS
    assert echoed == "how controllers Serial0/0/1"
    assert is_command_corrupted(classification)


def test_lost_first_character_of_ping_is_prefix_loss():
    window = "ing 150.1.1.81\n% Invalid input detected at '^' marker.\nRouter#"

    classification, echoed = classify_echo("ping 150.1.1.81", window)

    assert classification is DispatchClassification.PREFIX_LOSS
    assert echoed == "ing 150.1.1.81"


def test_exact_echo_is_the_only_thing_that_counts_as_dispatched():
    window = "show ip interface brief\nInterface IP-Address\nRouter#"

    classification, _ = classify_echo("show ip interface brief", window)

    assert classification is DispatchClassification.DISPATCHED


def test_echo_is_matched_exactly_not_by_containment():
    """Una ventana que MENCIONA el comando pedido no prueba que se despacho."""
    window = "how ip interface brief\n% Invalid input\nRouter#show ip interface brief"

    classification, echoed = classify_echo("show ip interface brief", window)

    assert classification is DispatchClassification.PREFIX_LOSS
    assert echoed == "how ip interface brief"


def test_arbitrary_corruption_is_mismatch_and_kept_apart_from_prefix_loss():
    classification, _ = classify_echo("show ip route", "sh0w ip route\nRouter#")

    assert classification is DispatchClassification.DISPATCH_MISMATCH
    assert is_command_corrupted(classification)


def test_output_without_any_echo_is_undecidable_not_corruption():
    """Un terminal que no hace eco no es un terminal que corrompio el comando."""
    window = "Interface  IP-Address  OK? Status\nGi0/0  192.0.2.1  YES up\nRouter#"

    classification, _ = classify_echo("show ip interface brief", window)

    assert classification is DispatchClassification.ECHO_UNOBSERVABLE
    assert not is_command_corrupted(classification)


def test_multiple_lost_leading_characters_are_still_corruption():
    classification, _ = classify_echo("show ip interface brief", "w ip interface brief\n% Invalid input")

    assert classification is DispatchClassification.DISPATCH_MISMATCH
    assert is_command_corrupted(classification)


def test_absent_echo_is_undecidable_and_never_a_success():
    classification, echoed = classify_echo("show ip route", "")

    assert classification is DispatchClassification.ECHO_UNOBSERVABLE
    assert echoed == ""
    assert not is_command_corrupted(classification)


def test_prompt_glued_to_the_echo_is_stripped_before_comparing():
    classification, echoed = classify_echo(
        "show ip route", "Router#show ip route\nCodes: L - local\nRouter#",
    )

    assert classification is DispatchClassification.DISPATCHED
    assert echoed == "show ip route"


# -- ventana fresca y buffer rodado ---------------------------------------

def test_appended_output_is_attributed_by_prefix_delta():
    window = fresh_command_window("Router#", "Router#show ip route\nS* 0.0.0.0\nRouter#")

    assert window.fresh and window.strategy is FreshWindowStrategy.PREFIX_DELTA
    assert window.output.startswith("show ip route")
    assert not window.rolled


def test_unchanged_buffer_yields_no_fresh_window():
    window = fresh_command_window("Router#show ip route", "Router#show ip route")

    assert not window.fresh and window.strategy is FreshWindowStrategy.NONE


def test_rolled_buffer_is_resynchronised_by_the_retained_suffix():
    """PT descarta un prefijo del transcript; lo retenido reancla la ventana."""
    before = "LINE-A\nLINE-B\nLINE-C\nRouter#"
    after = "LINE-C\nRouter#show ip route\nS* 0.0.0.0\nRouter#"

    window = fresh_command_window(before, after)

    assert window.fresh and window.rolled
    assert window.strategy is FreshWindowStrategy.ROLLED_SUFFIX_ANCHOR
    assert window.output == "show ip route\nS* 0.0.0.0\nRouter#"


def test_pager_erasing_its_own_marker_is_not_mistaken_for_a_rolled_buffer():
    """Medido en vivo: al salir del pager, IOS borra el `--More--` que imprimio.

    `after` deja de empezar con `before` sin que se haya perdido una sola linea.
    Tratarlo como buffer rodado descartaba la ventana que contenia la evidencia
    del comando corrompido.
    """
    before = "GigabitEthernet0/0 is up\n 0 packets output\n --More-- "
    after = (
        "GigabitEthernet0/0 is up\n 0 packets output\n"
        "w ip interface brief\n           ^\n"
        "% Invalid input detected at '^' marker.\nRouter>"
    )

    window = fresh_command_window(before, after)

    assert window.fresh
    assert window.strategy is FreshWindowStrategy.PAGER_TAIL_REWRITE
    assert window.output.startswith("w ip interface brief")

    classification, echoed = classify_echo("show ip interface brief", window.output)
    assert classification is DispatchClassification.DISPATCH_MISMATCH
    assert echoed == "w ip interface brief"


def test_real_output_lost_from_the_tail_is_not_excused_as_a_pager_rewrite():
    """Solo el marcador del pager cuenta como cola reescrita; salida real, no."""
    before = "Gi0/0 is up\n 0 packets output\nIMPORTANT LINE\n"
    after = "Gi0/0 is up\n 0 packets output\nsomething else\n"

    window = fresh_command_window(before, after)

    assert window.strategy is not FreshWindowStrategy.PAGER_TAIL_REWRITE


def test_buffer_rolled_past_every_anchor_is_explicitly_unattributable():
    window = fresh_command_window("AAAA\nBBBB\nRouter#", "ZZZZ\nYYYY\nRouter>")

    assert not window.fresh and window.rolled
    assert window.strategy is FreshWindowStrategy.ROLLED_UNATTRIBUTABLE
    assert window.output == ""


def test_a_repeated_command_in_a_long_session_is_not_attributed_to_the_old_run():
    """Regresion: anclarse al ULTIMO eco del comando atribuia salida vieja.

    El buffer rodo y la ejecucion nueva todavia no imprimio nada. Buscar el
    texto del comando encontraba la corrida ANTERIOR y la daba por fresca.
    """
    before = "Router#show ip route\nS* 0.0.0.0 via 10.0.0.1\nRouter#"
    after = before

    window = fresh_command_window(before, after)

    assert not window.fresh
    assert "0.0.0.0" not in window.output


# -- pager -----------------------------------------------------------------

def test_pager_marker_at_the_tail_is_detected():
    assert has_active_pager("show ip interface brief\nGi0/0 up\n--More--")


def test_pager_redrawn_with_backspaces_is_still_detected():
    """IOS borra su propio `--More--` con `\\x08 \\x08`; el texto crudo miente."""
    raw = "Gi0/0 up\n--More--" + "\b \b" * 3 + "--More--"

    assert has_active_pager(raw)


def test_backspace_erasure_does_not_eat_across_a_line_break():
    assert resolve_backspaces("abc\n\b\bxy") == "abc\nxy"


def test_rendered_text_drops_ansi_and_applies_backspaces():
    assert rendered_terminal_text("\x1b[2Jshow\b\b\b\bping 10.0.0.1\r\n") == "ping 10.0.0.1\n"


def test_a_finished_pager_is_not_reported_as_active():
    assert not has_active_pager("show ip interface brief\nGi0/0 up\nRouter#")


# -- barrera de readiness --------------------------------------------------

def _state(**overrides) -> dict:
    base = {"found": True, "terminal": True, "booting": False, "prompt": "Router#", "output": "Router#"}
    base.update(overrides)
    return base


def test_stable_exec_prompt_is_ready():
    previous = _state()

    assert assess_prompt_readiness(previous, _state()) is PromptReadiness.READY


def test_dispatch_is_refused_while_a_pager_is_pending():
    state = _state(output="Gi0/0 up\n--More--")

    assert assess_prompt_readiness(state, state) is PromptReadiness.PAGER_ACTIVE


def test_dispatch_is_refused_while_the_prompt_is_still_changing():
    """Una transicion de modo en curso es exactamente la carrera investigada."""
    previous = _state(prompt="Router>")

    assert assess_prompt_readiness(previous, _state(prompt="Router#")) is PromptReadiness.UNSTABLE


def test_dispatch_is_refused_during_boot():
    assert assess_prompt_readiness(None, _state(booting=True)) is PromptReadiness.BOOTING


def test_dispatch_is_refused_during_the_setup_dialog():
    state = _state(
        prompt="",
        output="Would you like to enter the initial configuration dialog? [yes/no]:",
    )

    assert assess_prompt_readiness(None, state) is PromptReadiness.SETUP_DIALOG


def test_dispatch_is_refused_while_awaiting_the_initial_return():
    state = _state(prompt="", output="Press RETURN to get started!")

    assert assess_prompt_readiness(None, state) is PromptReadiness.AWAITING_RETURN


def test_missing_terminal_is_unavailable():
    assert assess_prompt_readiness(None, _state(terminal=False)) is PromptReadiness.UNAVAILABLE


def test_first_echo_line_ignores_leading_blank_lines():
    assert first_echo_line("\n\n  show ip route  \nCodes:") == "show ip route"


# -- retry acotado sobre el ejecutor real ----------------------------------

class _CorruptingTerminal:
    """Termina perdiendo el primer caracter de los primeros N despachos.

    La corrupcion se inyecta, no se espera: el test no depende de que la
    carrera real de Packet Tracer se reproduzca durante la corrida.
    """

    def __init__(self, corrupt_dispatches: int, *, rejected: bool = True) -> None:
        self.output = "Router#"
        self.dispatched: list[str] = []
        self._corrupt_left = corrupt_dispatches
        self._rejected = rejected

    def __call__(self, js: str, _timeout: float) -> str:
        if "terminal_kind:'ios_command_line'" in js:
            return json.dumps({
                "found": True, "booting": False, "terminal": True,
                "prompt": "Router#", "output": self.output,
            })
        if "var before=String(t.getOutput())" in js:
            before = self.output
            command = re.search(r'enterCommand\("([^"]*)"\)', js).group(1)
            self.dispatched.append(command)
            if self._corrupt_left > 0:
                self._corrupt_left -= 1
                tail = (
                    "\n% Invalid input detected at '^' marker.\nRouter#"
                    if self._rejected else "\nRouter#"
                )
                self.output += command[1:] + tail
            else:
                self.output += command + "\nInterface  IP-Address  OK? Status\nRouter#"
            return json.dumps({"ok": True, "before": before})
        if "configuration_channel" in js:
            return json.dumps({
                "found": True, "configuration_channel": True, "output": self.output,
            })
        raise AssertionError(f"Unexpected terminal interaction: {js}")


def test_a_rejected_prefix_loss_is_retried_and_recovers():
    terminal = _CorruptingTerminal(1)

    result = ControlledIosExecutor(terminal).execute(
        "R1", OperationalQueryId.SHOW_IP_INTERFACE_BRIEF,
    )

    assert result.executed
    assert result.dispatch_attempts == 2
    assert result.dispatch_classification == DispatchClassification.DISPATCHED.value
    assert terminal.dispatched == ["show ip interface brief"] * 2


def test_retries_stop_at_the_declared_ceiling():
    terminal = _CorruptingTerminal(99)

    result = ControlledIosExecutor(terminal).execute(
        "R1", OperationalQueryId.SHOW_IP_INTERFACE_BRIEF,
    )

    assert not result.executed
    assert result.dispatch_attempts == 3
    assert len(terminal.dispatched) == 3
    assert result.dispatch_classification == DispatchClassification.PREFIX_LOSS.value


def test_corruption_is_not_reported_as_a_rejected_query():
    """`% Invalid input` sobre un comando corrompido no habla de la consulta."""
    result = ControlledIosExecutor(_CorruptingTerminal(99)).execute(
        "R1", OperationalQueryId.SHOW_IP_INTERFACE_BRIEF,
    )

    assert "COMMAND_DISPATCH_MISMATCH" in result.failure_reason
    assert result.echo_observed == "how ip interface brief"


def test_typed_ping_refuses_to_dispatch_while_a_pager_is_pending():
    """El path del `ping` no tenia ninguna guarda; es el del `ping` -> `ing`."""
    scripts: list[str] = []

    def send_and_wait(script, _timeout):
        scripts.append(script)
        if "enterCommand" in script:
            # La guarda corre dentro del mismo script: PT no llega a tipear.
            return json.dumps({"started": False, "blocked": "pager_active", "before": "Router#\n--More--"})
        return json.dumps({"found": True, "output": "Router#\n--More--"})

    result = TypedPingExecutor(send_and_wait, timeout_seconds=0).ping("R1", "10.0.0.1")

    assert not result.reachable
    assert result.failure_reason == "prompt_not_ready_pager_active"
    assert any("__pager" in script for script in scripts)


def test_typed_ping_refuses_the_first_dispatch_when_a_command_is_still_running():
    """La barrera vale para el PRIMER despacho, no solo para el reintento."""
    def send_and_wait(script, _timeout):
        if "enterCommand" in script:
            return json.dumps({"started": False, "blocked": "command_in_flight", "before": ""})
        return json.dumps({"found": True, "output": ""})

    result = TypedPingExecutor(send_and_wait, timeout_seconds=0).ping("PC0", "10.0.0.1")

    assert not result.reachable
    assert result.failure_reason == "prompt_not_ready_command_in_flight"


def test_the_idle_guard_travels_in_the_same_script_as_the_dispatch():
    scripts: list[str] = []

    def send_and_wait(script, _timeout):
        scripts.append(script)
        if "enterCommand" in script:
            return json.dumps({"started": True, "before": "C:\\>"})
        return json.dumps({"found": True, "output": "C:\\>ping 10.0.0.1\nPackets: Sent = 4, Received = 4\nC:\\>"})

    TypedPingExecutor(send_and_wait, timeout_seconds=0).ping("PC0", "10.0.0.1")

    dispatch = next(script for script in scripts if "enterCommand" in script)
    assert "__pager" in dispatch and "__idle" in dispatch


def test_typed_ping_names_a_corrupted_echo_instead_of_calling_it_absent():
    before = "Router#"
    output = before + "ing 10.0.0.1\n% Invalid input detected at '^' marker.\nRouter#"

    def send_and_wait(script, _timeout):
        if "enterCommand" in script:
            return json.dumps({"started": True, "before": before})
        return json.dumps({"found": True, "output": output})

    result = TypedPingExecutor(send_and_wait, timeout_seconds=0).ping("R1", "10.0.0.1")

    assert not result.reachable
    assert result.failure_reason.startswith("command_dispatch_mismatch:prefix_loss:")
    assert result.failure_reason.endswith("ing 10.0.0.1")


def test_a_ping_is_never_retried_while_the_previous_one_is_still_running():
    """Medido en vivo: el reintento pisaba un ping en curso.

    La ventana resultante pertenecia al comando ANTERIOR y se clasificaba como
    eco ausente, ocultando que se habia despachado sobre un terminal ocupado.
    """
    dispatches: list[str] = []
    # El terminal sigue imprimiendo: no volvio al prompt.
    busy = "C:\\>ping 10.0.0.1\n\nPinging 10.0.0.1 with 32 bytes of data:\n\n"

    def send_and_wait(script, _timeout):
        if "enterCommand" in script:
            dispatches.append(script)
            return json.dumps({"started": True, "before": "C:\\>"})
        return json.dumps({"found": True, "output": busy})

    result = TypedPingExecutor(
        send_and_wait, timeout_seconds=0, measurement_attempts=4,
        sleeper=lambda _s: None,
    ).ping("PC0", "10.0.0.1")

    assert not result.fresh_output_observed
    assert result.attempts == 1
    assert len(dispatches) == 1
    assert result.failure_reason


def test_a_terminal_back_at_its_prompt_is_idle():
    assert terminal_is_idle("C:\\>ping 10.0.0.1\nPackets: Sent = 4\n\nC:\\>")
    assert terminal_is_idle("Router#show ip route\nS* 0.0.0.0\nRouter#")


def test_a_terminal_still_printing_or_paging_is_not_idle():
    assert not terminal_is_idle("C:\\>ping 10.0.0.1\n\nPinging 10.0.0.1 with 32 bytes:\n")
    assert not terminal_is_idle("Router#show interfaces\nGi0/0 is up\n --More-- ")


def test_corruption_without_a_proven_rejection_is_never_retried():
    """Sin rechazo no hay prueba de que el comando corrompido no surtiera efecto."""
    terminal = _CorruptingTerminal(99, rejected=False)

    result = ControlledIosExecutor(terminal).execute(
        "R1", OperationalQueryId.SHOW_IP_INTERFACE_BRIEF,
    )

    assert not result.executed
    assert result.dispatch_attempts == 1
    assert len(terminal.dispatched) == 1
    assert result.dispatch_classification == DispatchClassification.PREFIX_LOSS.value
