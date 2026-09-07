"""POE-1: `show power inline` as a governed PSE-delivery observable.

Por que existe:
Hasta acá la única evidencia de entrega PoE autorizada es la observación visual
del teléfono (`manual_visible_power_state`), que necesita un humano mirando la
pantalla y no escala a un puerto más. El estado gobernado dejó anotado el único
candidato que queda del lado del switch:

    next_observable_candidate =
        SWITCH_SIDE_SHOW_POWER_INLINE_VIA_REGISTERED_IOS_QUERY_NOT_YET_EXAMINED

`show power inline` no está en el registro de consultas de producto, y no puede
entrar por adivinanza: en este build PT contesta un comando que no entiende con
texto que igual se parsea. El repo ya tiene el lugar exacto para un candidato
medido y todavía no promovido -- `IosQualificationQueryId`, que sólo
`ControlledIosExecutor.qualify()` puede ejercer -- y por ahí entra.

Este archivo NO promueve el candidato a `OperationalQueryId` ni toca
`_AUTHORIZED_OBSERVATION_METHODS`: la autoridad de reclamo sigue siendo la
visual. Sólo abre el camino gobernado para MEDIRLO en vivo.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.packet_tracer_mcp.infrastructure.execution.ios_terminal import (
    ControlledIosExecutor,
    IosQualificationQueryId,
    OperationalQueryId,
)


def test_the_poe_candidate_is_reachable_only_as_a_closed_qualification() -> None:
    """El candidato existe, y su texto IOS lo fija el repo, no el caller."""
    assert ControlledIosExecutor.qualification_command(
        IosQualificationQueryId.SHOW_POWER_INLINE,
    ) == "show power inline"


def test_the_poe_candidate_is_not_a_product_query_yet() -> None:
    """Medir no es promover: `execute` sigue rechazándolo.

    Un candidato en el registro de producto sería un read-back afirmable antes
    de tener una sola captura viva que diga qué imprime este build.
    """
    assert not any(
        item.name == "SHOW_POWER_INLINE" for item in OperationalQueryId
    )

    executor = ControlledIosExecutor(lambda _js, _timeout: None)
    with pytest.raises(TypeError, match="OperationalQueryId only"):
        executor.execute(  # type: ignore[arg-type]
            "Switch0", IosQualificationQueryId.SHOW_POWER_INLINE,
        )


def test_the_poe_candidate_never_accepts_an_interface_from_the_caller() -> None:
    """La forma global es la única medida; angostarla sería inventar sintaxis.

    `show power inline <interfaz>` no tiene soporte establecido en este build, y
    la tabla global ya trae una fila por puerto: la atribución exacta sale de la
    fila, no de un comando adivinado.
    """
    with pytest.raises(ValueError, match="does not accept an interface"):
        ControlledIosExecutor._registered_command(
            IosQualificationQueryId.SHOW_POWER_INLINE,
            interface="FastEthernet0/1",
        )


def _harness_source() -> str:
    root = Path(__file__).resolve().parents[1]
    return (
        root / "tools" / "poe_inline_calibration_live.py"
    ).read_text(encoding="utf-8")


def test_live_harness_accepts_no_ios_or_javascript_from_the_caller() -> None:
    """El arnés en vivo no tiene por dónde recibir CLI arbitraria.

    Todo lo que llega a Packet Tracer sale de un registro cerrado: los tres
    cambios de modo desde `PoEInlineMode`, y las lecturas desde los enums del
    ejecutor gobernado.
    """
    source = _harness_source()

    assert "ImportIsolationPreflight" in source
    assert "IosQualificationQueryId.SHOW_POWER_INLINE" in source
    assert "--execute" in source
    assert "--command" not in source
    assert "--ios" not in source
    assert "pt_send_raw" not in source
    assert "show running-config" not in source
    assert "show run" not in source


def test_the_live_harness_restores_and_proves_instead_of_assuming() -> None:
    """Restaurar y borrar el fixture no puede depender del camino feliz.

    Si la secuencia causal se cae a la mitad, el 3560 y el 7960 desechables
    quedarían en el lienzo y el próximo run arrancaría sobre un inventario
    sucio, que es justo lo que su propia precondición rechaza.
    """
    source = _harness_source()

    assert "finally:" in source
    assert "teardown" in source
    assert "inventory_fingerprint_before" in source
    assert "inventory_fingerprint_after" in source
    # La última mutación de la secuencia es `auto`, y su captura ES la
    # readback que prueba la restauración: no hay un "asumimos que volvió".
    assert '("auto_2", PoEInlineMode.AUTO)' in source


def test_the_live_harness_retires_what_packet_tracer_added_by_itself() -> None:
    """Borrar sólo lo creado dejaba el lienzo sucio. Medido, no supuesto.

    En `poe1-4d342a1a` el teardown borró los dos desechables y el inventario
    igual no volvió: PT había puesto un `Power Distribution Device0` al aparecer
    el 7960. La autoridad para retirarlo se acota contra los nombres de
    apertura, que se leen ANTES de crear nada.
    """
    source = _harness_source()

    assert "retire_session_residue" in source
    assert "devices_before" in source
    # El conjunto de apertura tiene que capturarse antes del fixture, o
    # "no estaba antes" incluiría al propio fixture.
    assert source.index("preexisting = calibration.device_names()") < source.index(
        'report.facts["fixture"] = calibration.build_fixture()'
    )


def test_the_live_harness_claims_no_authority_it_did_not_earn() -> None:
    """Calibrar no promueve: el artefacto lo dice explícitamente."""
    source = _harness_source()

    assert "authorized_observation_methods_unchanged" in source
    assert "poe_ports_extrapolated" in source
    assert "promotes_candidate_to_product_registry" in source
