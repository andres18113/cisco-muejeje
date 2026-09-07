"""POE-1: la regla tipada, escrita contra los bytes que PT realmente imprimio.

Todo el texto de este archivo es la salida verbatim del run gobernado
`poe1-c4fae886` (PT 9.0.1.0858, 3560-24PS, Fa0/1 -> 7960/Switch, sin adaptador
de corriente externo). Las cuatro capturas volvieron `executed`, `fresh`,
`complete`, `confirmed_unique` y estables por repeticion.

Lo que la secuencia causal midio, y que NO coincide con lo que se esperaba:

  auto  -> la fila `Fa0/1` esta, con `Oper=on`, `Power=10.0`, `Device=IP Phone
           7960`, `Class=3`
  never -> la fila `Fa0/1` NO ESTA. PT no la imprime en `off`: la saca de la
           tabla entera
  auto  -> la fila vuelve, identica

Tres cosas medidas que un parser escrito de memoria habria roto:

1. `never` es AUSENCIA de fila, no `Oper=off`. Por eso la ausencia sólo puede
   leerse desde una captura COMPLETA: en una truncada, "no esta en la tabla" y
   "no esta en esta pagina" son el mismo texto.
2. La fila que cae en la costura del pager llega con UN espacio inicial
   (` Fa0/18`). Un ancla `^Fa0/` descarta exactamente una fila por pagina, y una
   fila descartada es indistinguible de una fila ausente -- es decir, se leeria
   como "no hay entrega" en un puerto que si la tiene.
3. La linea de resumen NO responde. `Used:10.0(w)` es identica en los cuatro
   estados, incluido `never`, donde ningun puerto entrega. El resumen no es
   autoridad de entrega; la fila si.
"""

from __future__ import annotations

from src.packet_tracer_mcp.infrastructure.execution.ios_terminal import (
    PoEInlineDelivery,
    classify_poe_inline_delivery,
    parse_show_power_inline,
)

_HEAD = (
    "show power inline\n"
    "Available:370.0(w)  Used:10.0(w)  Remaining:360.0(w)\n"
    "\n"
    "Interface Admin  Oper       Power   Device              Class Max\n"
    "                            (Watts)\n"
    "--------- ------ ---------- ------- ------------------- ----- ----\n"
)


def _off(index: int, *, seam: bool = False) -> str:
    row = f"Fa0/{index:<5} auto   off        0.0     n/a                 n/a   15.4\n"
    return (" " + row) if seam else row


_POWERED_ROW = (
    "Fa0/1     auto   on         10.0    IP Phone 7960       3     15.4\n"
)

#: La lectura cierra con DOS prompts: el que cierra la ultima pagina y el que
#: deja el terminal listo. Ninguno es una fila, y el parser no puede leerlos
#: como si lo fueran.
_TAIL = "Switch#\nSwitch#\n"

#: `power inline auto`: 24 filas, `Fa0/18` en la costura del pager.
_MEASURED_AUTO = (
    _HEAD
    + _POWERED_ROW
    + "".join(_off(i) for i in range(2, 18))
    + _off(18, seam=True)
    + "".join(_off(i) for i in range(19, 25))
    + _TAIL
)

#: `power inline never`: 23 filas y ninguna es `Fa0/1`. La costura cae en
#: `Fa0/19` porque la fila que falta corria todo hacia arriba.
_MEASURED_NEVER = (
    _HEAD
    + "".join(_off(i) for i in range(2, 19))
    + _off(19, seam=True)
    + "".join(_off(i) for i in range(20, 25))
    + _TAIL
)


def test_the_fixtures_are_the_bytes_the_governed_run_recorded() -> None:
    """El artefacto es la autoridad; este archivo no puede derivar de el.

    Si alguien ajusta una columna 'para que el parser pase', esto lo delata
    contra la evidencia persistida en vez de dejarlo pasar en silencio.
    """
    import json
    from pathlib import Path

    artifact = json.loads(
        (
            Path(__file__).resolve().parents[1]
            / "docs/reference/cp-scale/canonical-live-evidence"
            / "poe-inline-calibration-poe1-c4fae886.json"
        ).read_text(encoding="utf-8")
    )
    measured = {item["label"]: item["output"] for item in artifact["captures"]}

    assert measured["auto_1"].rstrip("\n") == _MEASURED_AUTO.rstrip("\n")
    assert measured["never"].rstrip("\n") == _MEASURED_NEVER.rstrip("\n")
    assert measured["auto_2"].rstrip("\n") == _MEASURED_AUTO.rstrip("\n")


# -- el parser --------------------------------------------------------------

def test_the_powered_row_parses_every_column_including_a_device_with_spaces():
    table = parse_show_power_inline(_MEASURED_AUTO)

    row = {item.interface: item for item in table.rows}["Fa0/1"]
    assert row.admin == "auto"
    assert row.oper == "on"
    assert row.power_watts == 10.0
    assert row.device == "IP Phone 7960"
    assert row.power_class == "3"
    assert row.max_watts == 15.4


def test_the_row_at_the_pager_seam_is_not_silently_dropped():
    """Descartarla convertiria una costura de pagina en un falso 'sin entrega'."""
    table = parse_show_power_inline(_MEASURED_AUTO)

    interfaces = [item.interface for item in table.rows]
    assert len(interfaces) == 24
    assert interfaces[17] == "Fa0/18"
    assert interfaces == [f"Fa0/{index}" for index in range(1, 25)]


def test_the_never_capture_is_short_exactly_the_calibrated_row():
    table = parse_show_power_inline(_MEASURED_NEVER)

    interfaces = [item.interface for item in table.rows]
    assert len(interfaces) == 23
    assert "Fa0/1" not in interfaces
    assert interfaces == [f"Fa0/{index}" for index in range(2, 25)]


def test_the_summary_is_recorded_but_never_becomes_authority():
    """Se mide identica en `auto` y en `never`: describir no es afirmar."""
    powered = parse_show_power_inline(_MEASURED_AUTO)
    unpowered = parse_show_power_inline(_MEASURED_NEVER)

    assert powered.summary_used_watts == 10.0
    assert unpowered.summary_used_watts == 10.0
    assert powered.summary_used_watts == unpowered.summary_used_watts


def test_text_without_the_measured_header_yields_no_rows():
    """PT contesta un comando que no entiende con texto que igual se parsea."""
    assert parse_show_power_inline("Invalid input detected at '^' marker.").rows == ()
    assert parse_show_power_inline("").rows == ()


# -- la regla tipada --------------------------------------------------------

def test_a_complete_capture_with_the_powered_row_means_delivering():
    assert classify_poe_inline_delivery(
        _MEASURED_AUTO, "Fa0/1", capture_complete=True,
    ) is PoEInlineDelivery.DELIVERING


def test_a_complete_capture_missing_the_row_means_not_delivering():
    assert classify_poe_inline_delivery(
        _MEASURED_NEVER, "Fa0/1", capture_complete=True,
    ) is PoEInlineDelivery.NOT_DELIVERING


def test_a_present_row_that_is_off_means_not_delivering():
    assert classify_poe_inline_delivery(
        _MEASURED_AUTO, "Fa0/7", capture_complete=True,
    ) is PoEInlineDelivery.NOT_DELIVERING


def test_an_incomplete_capture_can_never_report_absence_as_a_negative():
    """El techo fail-closed que hizo falta cualificar el pager para empezar.

    En una captura truncada la ausencia de fila no prueba nada, asi que no puede
    salir NOT_DELIVERING: eso afirmaria que el puerto no entrega cuando lo unico
    observado es que la pagina se corto antes.
    """
    assert classify_poe_inline_delivery(
        _MEASURED_NEVER, "Fa0/1", capture_complete=False,
    ) is PoEInlineDelivery.UNOBSERVABLE


def test_an_incomplete_capture_that_shows_the_powered_row_still_delivers():
    """Ver la fila encendida es positivo aunque falte el resto de la tabla.

    La completitud hace falta para sostener una AUSENCIA, no para creerle a una
    fila que esta ahi, fresca y atribuida.
    """
    assert classify_poe_inline_delivery(
        _MEASURED_AUTO, "Fa0/1", capture_complete=False,
    ) is PoEInlineDelivery.DELIVERING


def test_an_unparsable_capture_is_unobservable_rather_than_negative():
    assert classify_poe_inline_delivery(
        "Invalid input detected at '^' marker.", "Fa0/1", capture_complete=True,
    ) is PoEInlineDelivery.UNOBSERVABLE
