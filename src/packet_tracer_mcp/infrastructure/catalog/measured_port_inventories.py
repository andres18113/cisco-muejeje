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

The canonical CP-SCALE qualification later measured the exact models required
by the documented physical design: bare and `NM-4A/S@1` states of `2811`,
`2960-24TT`, `3650-24PS`, and `Laptop-PT`. The same qualifier and production
read-back seam were used, and all five disposable devices were removed before
the empty baseline was accepted as restored.

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
_CP_SCALE_CANONICAL_PORT_QUALIFICATION = (
    "cp-scale-canonical-port-qualification/observe_device"
)
_CP_SCALE_819_ALIAS_QUALIFICATION = (
    "cp-scale-stage-a-link-alias-qualification/exact-link-readback"
)

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
    port_aliases={"Ethernet1": "FastEthernet0"},
    source=(
        _CP_SCALE_STAGE_A_QUALIFICATION
        + ";"
        + _CP_SCALE_819_ALIAS_QUALIFICATION
    ),
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

_PT_2811 = BackendVerifiedPortInventory(
    model="2811",
    backend=PACKET_TRACER_BACKEND,
    backend_version=MEASURED_BACKEND_VERSION,
    installed_modules=[],
    ports=["FastEthernet0/0", "FastEthernet0/1", "Vlan1"],
    source=_CP_SCALE_CANONICAL_PORT_QUALIFICATION,
)

_PT_2811_WITH_NM_4A_S = BackendVerifiedPortInventory(
    model="2811",
    backend=PACKET_TRACER_BACKEND,
    backend_version=MEASURED_BACKEND_VERSION,
    installed_modules=["NM-4A/S@1"],
    ports=[
        "FastEthernet0/0",
        "FastEthernet0/1",
        "Serial1/0",
        "Serial1/1",
        "Serial1/2",
        "Serial1/3",
        "Vlan1",
    ],
    source=_CP_SCALE_CANONICAL_PORT_QUALIFICATION,
)

_PT_2960_24TT = BackendVerifiedPortInventory(
    model="2960-24TT",
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
    source=_CP_SCALE_CANONICAL_PORT_QUALIFICATION,
)

_PT_3650_24PS = BackendVerifiedPortInventory(
    model="3650-24PS",
    backend=PACKET_TRACER_BACKEND,
    backend_version=MEASURED_BACKEND_VERSION,
    installed_modules=[],
    ports=[
        "GigabitEthernet1/0/1",
        "GigabitEthernet1/0/10",
        "GigabitEthernet1/0/11",
        "GigabitEthernet1/0/12",
        "GigabitEthernet1/0/13",
        "GigabitEthernet1/0/14",
        "GigabitEthernet1/0/15",
        "GigabitEthernet1/0/16",
        "GigabitEthernet1/0/17",
        "GigabitEthernet1/0/18",
        "GigabitEthernet1/0/19",
        "GigabitEthernet1/0/2",
        "GigabitEthernet1/0/20",
        "GigabitEthernet1/0/21",
        "GigabitEthernet1/0/22",
        "GigabitEthernet1/0/23",
        "GigabitEthernet1/0/24",
        "GigabitEthernet1/0/3",
        "GigabitEthernet1/0/4",
        "GigabitEthernet1/0/5",
        "GigabitEthernet1/0/6",
        "GigabitEthernet1/0/7",
        "GigabitEthernet1/0/8",
        "GigabitEthernet1/0/9",
        "GigabitEthernet1/1/1",
        "GigabitEthernet1/1/2",
        "GigabitEthernet1/1/3",
        "GigabitEthernet1/1/4",
        "Vlan1",
    ],
    source=_CP_SCALE_CANONICAL_PORT_QUALIFICATION,
)

_PT_LAPTOP = BackendVerifiedPortInventory(
    model="Laptop-PT",
    backend=PACKET_TRACER_BACKEND,
    backend_version=MEASURED_BACKEND_VERSION,
    installed_modules=[],
    ports=["Bluetooth", "FastEthernet0"],
    source=_CP_SCALE_CANONICAL_PORT_QUALIFICATION,
)

MEASURED_PORT_INVENTORIES: tuple[BackendVerifiedPortInventory, ...] = (
    _PT_2811,
    _PT_2811_WITH_NM_4A_S,
    _PT_2960_24TT,
    _PT_3560_24PS,
    _PT_3650_24PS,
    _PT_819HG_4G_IOX,
    _PT_1941,
    _PT_1941_WITH_HWIC2T,
    _PT_2911_WITH_HWIC2T,
    _PT_2950T_24,
    _PT_ACCESS_POINT,
    _PT_IE_2000,
    _PT_IP_PHONE_7960,
    _PT_LAPTOP,
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
