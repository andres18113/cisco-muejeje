"""POE-1: `show power inline` no cabe en una pagina, y la primera no alcanza.

Medido en vivo en PT 9.0.1.0858 (run `poe1-4d342a1a`, 3560-24PS): las cuatro
capturas de la secuencia causal volvieron `executed=True`, `fresh=True`,
`confirmed_unique` -- y `output_complete=False`, `truncated_by_pager=True`,
`pager_continuation=not_qualified`. El pager fue el unico bloqueante.

Por que la primera pagina NO alcanza para esta calibracion:
Las dos capturas midieron 1390 bytes EXACTOS, asi que el corte de pagina de este
build es por tamano, no por cantidad de filas. En `auto` la pagina llega hasta
`Fa0/17` porque la fila de `Fa0/1` ocupa lugar; en `never` la fila de `Fa0/1` no
esta y entra una fila mas, hasta `Fa0/18`. Esa ausencia es justamente la mitad
negativa de la firma causal que el ticket pide, y una primera pagina no puede
sostenerla: "Fa0/1 no aparece en esta pagina" no es "Fa0/1 no esta en la tabla".
Es el mismo argumento que ya hizo cualificar a `SHOW_IP_DHCP_BINDING`, donde el
hecho diagnostico tambien era una ausencia.

La consulta tampoco se puede angostar: `show power inline <interfaz>` no tiene
soporte establecido en este build y adivinarlo seria inventar la forma del
comando para esquivar el pager, y PT 9.0.1 rechaza `terminal length 0`.

Alcance de lo que se afirma aca: la PRIMERA pagina es texto medido, verbatim.
La continuacion sirve para ejercitar la mecanica del recorrido -- que la lectura
cierre en un prompt y deje de estar truncada -- y sus filas no se afirman como
las que imprime PT. Eso sale de la corrida en vivo, no de este archivo.
"""

from __future__ import annotations

from src.packet_tracer_mcp.infrastructure.execution.ios_terminal import (
    ControlledIosExecutor,
    IosQualificationQueryId,
    PagerContinuation,
)
from tests.test_e95_serial_orientation_pager_capture import (
    _FakeClock,
    _PagedTerminal,
)

_COMMAND = "show power inline"
_PROMPT = "Switch#"

#: Primera pagina medida en vivo, verbatim, menos el marcador que el falso
#: TerminalLine agrega por su cuenta. 1390 bytes con el marcador.
_MEASURED_FIRST_PAGE = (
    "Available:370.0(w)  Used:10.0(w)  Remaining:360.0(w)\n"
    "\n"
    "Interface Admin  Oper       Power   Device              Class Max\n"
    "                            (Watts)\n"
    "--------- ------ ---------- ------- ------------------- ----- ----\n"
    "Fa0/1     auto   on         10.0    IP Phone 7960       3     15.4\n"
    "Fa0/2     auto   off        0.0     n/a                 n/a   15.4\n"
    "Fa0/3     auto   off        0.0     n/a                 n/a   15.4\n"
    "Fa0/4     auto   off        0.0     n/a                 n/a   15.4\n"
    "Fa0/5     auto   off        0.0     n/a                 n/a   15.4\n"
    "Fa0/6     auto   off        0.0     n/a                 n/a   15.4\n"
    "Fa0/7     auto   off        0.0     n/a                 n/a   15.4\n"
    "Fa0/8     auto   off        0.0     n/a                 n/a   15.4\n"
    "Fa0/9     auto   off        0.0     n/a                 n/a   15.4\n"
    "Fa0/10    auto   off        0.0     n/a                 n/a   15.4\n"
    "Fa0/11    auto   off        0.0     n/a                 n/a   15.4\n"
    "Fa0/12    auto   off        0.0     n/a                 n/a   15.4\n"
    "Fa0/13    auto   off        0.0     n/a                 n/a   15.4\n"
    "Fa0/14    auto   off        0.0     n/a                 n/a   15.4\n"
    "Fa0/15    auto   off        0.0     n/a                 n/a   15.4\n"
    "Fa0/16    auto   off        0.0     n/a                 n/a   15.4\n"
    "Fa0/17    auto   off        0.0     n/a                 n/a   15.4\n"
)

#: Continuacion con la MISMA forma de fila, para ejercitar el recorrido. No se
#: afirma que estas sean las filas que PT imprime en su segunda pagina.
_CONTINUATION_SHAPE = "".join(
    f"Fa0/{index:<5} auto   off        0.0     n/a                 n/a   15.4\n"
    for index in range(18, 25)
)


def _executor(terminal: _PagedTerminal) -> ControlledIosExecutor:
    clock = _FakeClock()
    return ControlledIosExecutor(terminal, clock=clock, sleeper=lambda _s: None)


def _paged_terminal() -> _PagedTerminal:
    return _PagedTerminal(
        [_MEASURED_FIRST_PAGE, _CONTINUATION_SHAPE],
        prompt=_PROMPT,
        command=_COMMAND,
    )


def test_the_candidate_walks_its_pager_instead_of_stopping_at_page_one() -> None:
    """Sin recorrer el pager, la mitad negativa de la firma es inobservable."""
    terminal = _paged_terminal()

    result = _executor(terminal).qualify(
        "Switch0", IosQualificationQueryId.SHOW_POWER_INLINE,
    )

    assert result.executed
    assert result.output_complete, (
        "La lectura sigue cerrando truncada: una ausencia de fila no se puede "
        "distinguir de un corte de pagina."
    )
    assert not result.truncated_by_pager
    assert result.pager_continuation == PagerContinuation.COMPLETED.value
    assert terminal.advances >= 1


def test_the_complete_capture_carries_both_ends_of_the_table() -> None:
    """La fila calibrada y la ultima de la tabla en UNA sola lectura logica."""
    result = _executor(_paged_terminal()).qualify(
        "Switch0", IosQualificationQueryId.SHOW_POWER_INLINE,
    )

    assert "Fa0/1     auto   on         10.0    IP Phone 7960" in result.output
    assert "Fa0/24" in result.output
    assert "--More--" not in result.output


def test_a_capture_that_cannot_finish_stays_truncated_rather_than_guessing()  -> None:
    """Si la continuacion no cierra en prompt, no se inventa completitud.

    El techo fail-closed es el mismo que ya tiene toda consulta cualificada: una
    captura incompleta se reporta incompleta, nunca como ausencia observada.
    """
    terminal = _PagedTerminal(
        [_MEASURED_FIRST_PAGE, _CONTINUATION_SHAPE],
        prompt=_PROMPT,
        command=_COMMAND,
        final_tail="--More--",
    )

    result = _executor(terminal).qualify(
        "Switch0", IosQualificationQueryId.SHOW_POWER_INLINE,
    )

    assert not result.output_complete
    assert result.truncated_by_pager


def test_capture_retains_the_prompt_at_dispatch_not_after_user_mode_restore():
    import json
    from src.packet_tracer_mcp.infrastructure.execution.ios_terminal import IosSessionState

    class ReturningToUserMode(_PagedTerminal):
        def __call__(self, js, timeout):
            if 'var before=String(t.getOutput())' in js:
                reply = json.loads(super().__call__(js, timeout))
                if 'expected_prompt:expectedPrompt' in js:
                    reply['expected_prompt'] = self.prompt
                return json.dumps(reply)
            return super().__call__(js, timeout)

    terminal = ReturningToUserMode([_MEASURED_FIRST_PAGE, _CONTINUATION_SHAPE],
                                   prompt='Switch#', command=_COMMAND)
    executor = _executor(terminal)
    executor._prepare_session = lambda name: IosSessionState.EXEC_PROMPT_READY
    original = executor._terminal_state
    first = True
    def state(name):
        nonlocal first
        if first:
            first = False
            return {'prompt': 'Switch>'}
        return original(name)
    executor._terminal_state = state
    executor._wait_for = lambda *args: True
    def enter(name, command):
        terminal.prompt = 'Switch>' if command == 'disable' else 'Switch#'
        return True
    executor._enter = enter
    result = executor.qualify('Switch0', IosQualificationQueryId.SHOW_POWER_INLINE)
    assert terminal.prompt == 'Switch>'
    assert result.expected_prompt == 'Switch#'
    assert result.output.rstrip().endswith('Switch#')
