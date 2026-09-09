"""Immutable ping evidence, independent of terminal and transport mechanics."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TypedPingResult:
    reachable: bool
    fresh_output_observed: bool
    window_strategy: str = "none"
    failure_reason: str = ""
    # Cuantas ejecuciones hicieron falta para obtener una ventana atribuible.
    attempts: int = 1
    # Linea de estadisticas tal como la imprimio el terminal, ya recortada a la
    # ventana atribuible. Existe para que un caller pueda mostrar la medida sin
    # volver a leer la consola por fuera de esta frontera.
    statistics: str = ""
    # Procedencia de la EJECUCION, no del pedido. Misma clasificacion que la
    # consulta IOS registrada: sin atribucion unica, la identidad de la fuente
    # de esta medida sigue siendo inobservable.
    # Destino que el ejecutor REALMENTE despacho y cuyo eco exacto confirmo.
    # No es el argumento pedido de vuelta: solo se rellena en los retornos que
    # ya pasaron la comprobacion de eco, asi que un despacho corrompido o una
    # ventana rancia lo dejan vacio y nadie puede certificar la direccion.
    dispatched_destination: str = ""
    observed_device_name: str = ""
    device_identity_provenance: str = "not_observed"
    device_identity_evidence: str = "none"
