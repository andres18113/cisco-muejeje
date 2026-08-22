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
`2960-24TT`, the model the *hand-pinned* reference topology uses, still has no
record here and stays UNKNOWN: capability-driven selection picks `2950T-24` for
the same role, so nothing this repository executes needs it, and it is not this
module's job to assume the two would agree.

The `1941` and `2950T-24` records came later, from the Stage 3A4 **MEG-5**
port-inventory qualification: the 41-device reference selects them and the port
evidence gate refused it until they were measured. That pass creates one
disposable `__MCP_PORTQUAL_*` device per (model, module state) through
`PortInventoryQualifier`, reads it back through this same production seam, and
removes it — the measurement path is identical to run 2's, only the occasion
differs.

The `AccessPoint-PT`, `7960`, `Printer-PT`, `819HG-4G-IOX`, and `3560-24PS`
records came from the same bounded qualifier when CP-SCALE Stage A reached the
physical port-evidence gate. They were measured together on an empty semantic
workspace and each observed model identity matched its requested model before
the evidence was admitted.

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
_MEG5_QUALIFICATION = "stage-3a4-meg5-port-qualification/observe_device"
_CP_SCALE_STAGE_A_QUALIFICATION = "cp-scale-stage-a-port-qualification/observe_device"

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


#: El `1941` vacio, medido en la cualificacion MEG-5. Sirve para el binding de
#: sus puertos Gigabit; NO responde por los Serial, que no existen sin tarjeta.
_PT_1941 = BackendVerifiedPortInventory(
    model="1941",
    backend=PACKET_TRACER_BACKEND,
    backend_version=MEASURED_BACKEND_VERSION,
    installed_modules=[],
    ports=[
        "GigabitEthernet0/0",
        "GigabitEthernet0/1",
        "Vlan1",
    ],
    source=_MEG5_QUALIFICATION,
)

#: El mismo `1941` CON el HWIC-2T en `0/0`. Es el estado en el que la referencia
#: lo despliega, y el unico que autoriza `Serial0/0/x`. Dos slots HWIC, no
#: cuatro: el bare de arriba y este se midieron en la misma pasada, uno detras
#: del otro, y la diferencia entre ambos es exactamente lo que la tarjeta anade.
_PT_1941_WITH_HWIC2T = BackendVerifiedPortInventory(
    model="1941",
    backend=PACKET_TRACER_BACKEND,
    backend_version=MEASURED_BACKEND_VERSION,
    installed_modules=["HWIC-2T@0/0"],
    ports=[
        "GigabitEthernet0/0",
        "GigabitEthernet0/1",
        "Serial0/0/0",
        "Serial0/0/1",
        "Vlan1",
    ],
    source=_MEG5_QUALIFICATION,
)

#: `2950T-24`, el switch de acceso que la seleccion por capacidades elige para
#: la referencia. Numera `0/x`, al reves que el `IE-2000`; por eso ninguno de
#: los dos puede responder por el otro.
_PT_2950T_24 = BackendVerifiedPortInventory(
    model="2950T-24",
    backend=PACKET_TRACER_BACKEND,
    backend_version=MEASURED_BACKEND_VERSION,
    installed_modules=[],
    ports=[
        "FastEthernet0/1",
        "FastEthernet0/10",
        "FastEthernet0/11",
        "FastEthernet0/12",
        "FastEthernet0/13",
        "FastEthernet0/14",
        "FastEthernet0/15",
        "FastEthernet0/16",
        "FastEthernet0/17",
        "FastEthernet0/18",
        "FastEthernet0/19",
        "FastEthernet0/2",
        "FastEthernet0/20",
        "FastEthernet0/21",
        "FastEthernet0/22",
        "FastEthernet0/23",
        "FastEthernet0/24",
        "FastEthernet0/3",
        "FastEthernet0/4",
        "FastEthernet0/5",
        "FastEthernet0/6",
        "FastEthernet0/7",
        "FastEthernet0/8",
        "FastEthernet0/9",
        "GigabitEthernet0/1",
        "GigabitEthernet0/2",
        "Vlan1",
    ],
    source=_MEG5_QUALIFICATION,
)

_PT_ACCESS_POINT = BackendVerifiedPortInventory(
    model="AccessPoint-PT",
    backend=PACKET_TRACER_BACKEND,
    backend_version=MEASURED_BACKEND_VERSION,
    installed_modules=[],
    ports=["Port 0", "Port 1"],
    source=_CP_SCALE_STAGE_A_QUALIFICATION,
)

_PT_IP_PHONE_7960 = BackendVerifiedPortInventory(
    model="7960",
    backend=PACKET_TRACER_BACKEND,
    backend_version=MEASURED_BACKEND_VERSION,
    installed_modules=[],
    ports=["PC", "Switch", "Vlan1"],
    source=_CP_SCALE_STAGE_A_QUALIFICATION,
)

_PT_PRINTER = BackendVerifiedPortInventory(
    model="Printer-PT",
    backend=PACKET_TRACER_BACKEND,
    backend_version=MEASURED_BACKEND_VERSION,
    installed_modules=[],
    ports=["FastEthernet0"],
    source=_CP_SCALE_STAGE_A_QUALIFICATION,
)

_PT_819HG_4G_IOX = BackendVerifiedPortInventory(
    model="819HG-4G-IOX",
    backend=PACKET_TRACER_BACKEND,
    backend_version=MEASURED_BACKEND_VERSION,
    installed_modules=[],
    ports=[
        "Cellular0",
        "Ethernet1",
        "FastEthernet0",
        "FastEthernet1",
        "FastEthernet2",
        "FastEthernet3",
        "GigabitEthernet0",
        "Serial0",
        "VirtualPortGroup0",
        "Vlan1",
    ],
    source=_CP_SCALE_STAGE_A_QUALIFICATION,
)

_PT_3560_24PS = BackendVerifiedPortInventory(
    model="3560-24PS",
    backend=PACKET_TRACER_BACKEND,
    backend_version=MEASURED_BACKEND_VERSION,
    installed_modules=[],
    ports=[
        "FastEthernet0/1",
        "FastEthernet0/10",
        "FastEthernet0/11",
        "FastEthernet0/12",
        "FastEthernet0/13",
        "FastEthernet0/14",
        "FastEthernet0/15",
        "FastEthernet0/16",
        "FastEthernet0/17",
        "FastEthernet0/18",
        "FastEthernet0/19",
        "FastEthernet0/2",
        "FastEthernet0/20",
        "FastEthernet0/21",
        "FastEthernet0/22",
        "FastEthernet0/23",
        "FastEthernet0/24",
        "FastEthernet0/3",
        "FastEthernet0/4",
        "FastEthernet0/5",
        "FastEthernet0/6",
        "FastEthernet0/7",
        "FastEthernet0/8",
        "FastEthernet0/9",
        "GigabitEthernet0/1",
        "GigabitEthernet0/2",
        "Vlan1",
    ],
    source=_CP_SCALE_STAGE_A_QUALIFICATION,
)

MEASURED_PORT_INVENTORIES: tuple[BackendVerifiedPortInventory, ...] = (
    _PT_3560_24PS,
    _PT_819HG_4G_IOX,
    _PT_1941,
    _PT_1941_WITH_HWIC2T,
    _PT_2911_WITH_HWIC2T,
    _PT_2950T_24,
    _PT_ACCESS_POINT,
    _PT_IE_2000,
    _PT_IP_PHONE_7960,
    _PT_PC,
    _PT_PRINTER,
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
