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
