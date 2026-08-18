"""Port inventories Packet Tracer actually reported, pinned to one build.

Backend knowledge, not domain knowledge, and deliberately separate from
`devices.py`. That catalogue is backend-agnostic: it states what a model is
supposed to have, and rewriting it from one live observation would silently
convert a planning declaration into a claim about a specific build. This module
is the build-specific half, in the same shape as `link_mode_capabilities.py`.

Everything below was observed during the Stage 3A4 MEG-4 bounded qualification,
run 2, on PT 9.0.1.0858, through the production read-back seam
(`PacketTracerPhysicalTopologyRuntime.observe_device`) on devices the run had
just created. Each list is the complete fresh inventory as reported, including
logical interfaces: trimming them here would turn an observation into an
interpretation.

**What is absent is unmeasured, which is not the same as wrong.** Every model
not listed resolves UNKNOWN for concrete backend binding and stays planning-only.
Notably `2960-24TT`, the model the pinned reference topology uses by hand, has
no record here — the reference has never been run through this seam, and it is
not this module's job to assume it would agree.

`IE-2000` is the reason this module exists. Its declared inventory numbers ports
`0/x`; Packet Tracer numbers them `1/x`. The declaration is not corrected —
`devices.py` still says what it always said — but a concrete binding now comes
from the measurement, and a binding with no measurement is refused.
"""

from __future__ import annotations

from ...domain.enterprise.models.port_inventory import (
    BackendVerifiedPortInventory,
    PortInventoryResolution,
    resolve_port_inventory,
)

PACKET_TRACER_BACKEND = "packet_tracer"
MEASURED_BACKEND_VERSION = "9.0.1.0858"

_MEG4_RUN_2 = "stage-3a4-meg4-run2/observe_device"

#: Un 2911 recien creado CON el HWIC-2T ya insertado en `0/0`. El estado de
#: modulo importa: sin la tarjeta, `Serial0/0/0` y `Serial0/0/1` no existen, y
#: por eso esta medicion no responde por un 2911 vacio.
_PT_2911_WITH_HWIC2T = BackendVerifiedPortInventory(
    model="2911",
    backend=PACKET_TRACER_BACKEND,
    backend_version=MEASURED_BACKEND_VERSION,
    installed_modules=["HWIC-2T@0/0"],
    ports=[
        "GigabitEthernet0/0",
        "GigabitEthernet0/1",
        "GigabitEthernet0/2",
        "Serial0/0/0",
        "Serial0/0/1",
        "Vlan1",
    ],
    source=_MEG4_RUN_2,
)

#: El hallazgo: declarado `0/x`, reportado `1/x`. Sin modulos.
_PT_IE_2000 = BackendVerifiedPortInventory(
    model="IE-2000",
    backend=PACKET_TRACER_BACKEND,
    backend_version=MEASURED_BACKEND_VERSION,
    installed_modules=[],
    ports=[
        "FastEthernet1/1",
        "FastEthernet1/2",
        "FastEthernet1/3",
        "FastEthernet1/4",
        "FastEthernet1/5",
        "FastEthernet1/6",
        "FastEthernet1/7",
        "FastEthernet1/8",
        "GigabitEthernet1/1",
        "GigabitEthernet1/2",
        "Vlan1",
    ],
    source=_MEG4_RUN_2,
)

#: `Bluetooth` viene en la lectura y se conserva. No es un puerto Ethernet, asi
#: que no llega a ser descriptor de planificacion, pero borrarlo del registro
#: seria editar la observacion.
_PT_PC = BackendVerifiedPortInventory(
    model="PC-PT",
    backend=PACKET_TRACER_BACKEND,
    backend_version=MEASURED_BACKEND_VERSION,
    installed_modules=[],
    ports=["Bluetooth", "FastEthernet0"],
    source=_MEG4_RUN_2,
)

MEASURED_PORT_INVENTORIES: tuple[BackendVerifiedPortInventory, ...] = (
    _PT_2911_WITH_HWIC2T,
    _PT_IE_2000,
    _PT_PC,
)


def backend_verified_port_inventory(
    model: str,
    *,
    backend: str = PACKET_TRACER_BACKEND,
    backend_version: str = "",
    installed_modules: list[str] | tuple[str, ...] | None = None,
) -> PortInventoryResolution:
    """Resolve one model/build/module-state query against what was measured."""

    return resolve_port_inventory(
        MEASURED_PORT_INVENTORIES,
        model,
        backend=backend,
        backend_version=backend_version,
        installed_modules=installed_modules,
    )


def module_state_token(module: str, slot: str) -> str:
    """The spelling used to record a module state, so callers cannot drift."""

    return f"{module.strip()}@{slot.strip()}"
