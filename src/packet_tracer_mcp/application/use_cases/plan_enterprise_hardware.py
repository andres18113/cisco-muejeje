"""Consumidor productivo de evidencia de capacidad para la seleccion de hardware.

TD-HARDWARE-001, en una frase: la evidencia de capacidad existia, la raiz de
composicion por version exacta existia, y `HardwarePlanner` existia -- pero nada
en `src/` conectaba los tres. Medido con Graphify antes de escribir esto: las 47
aristas entrantes de `HardwarePlanner` venian todas de tests o de su propio
modulo, y `packet_tracer_enterprise_capability_adapter` no tenia ni un llamador
productivo.

Este caso de uso es ese llamador y nada mas. No planifica: delega en
`HardwarePlanner`, que queda intacto. No decide capacidades: las lee de los
providers por version exacta. Su unica responsabilidad es componer.

La version es opcional a proposito, y las dos ramas dicen cosas distintas:

- con version exacta -> raiz de composicion productiva, evidencia elegible;
- sin version        -> adapter desnudo, todo UNKNOWN.

UNKNOWN no es permiso. Un candidato sin evidencia no queda habilitado por
omision: `DeviceSelector` lo marca como que necesita verificacion, y esa
distincion es justamente lo que la deuda pide conservar.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ...domain.enterprise.models.enterprise_plan import EnterprisePlan
from ...domain.enterprise.models.hardware import HardwareCandidate, HardwarePlan
from ...domain.enterprise.services.hardware_planner import (
    HardwarePlanner,
    HardwarePlanningPolicy,
)
from ...infrastructure.catalog.enterprise_capabilities import (
    EnterpriseCapabilityAdapter,
    packet_tracer_enterprise_capability_adapter,
)
from ...infrastructure.persistence.capability_snapshot_store import (
    CapabilitySnapshotStore,
)


@dataclass(frozen=True)
class EnterpriseHardwareComposition:
    """El plan y la evidencia con la que se decidio, juntos.

    Los candidatos viajan con el resultado porque el criterio de cierre de
    TD-HARDWARE-001 habla de la evidencia *usada por* el resolver. Devolver solo
    el plan haria que esa evidencia fuera irrecuperable justo cuando hay que
    registrarla.
    """

    plan: HardwarePlan
    switch_candidates: list[HardwareCandidate] = field(default_factory=list)
    router_candidates: list[HardwareCandidate] = field(default_factory=list)
    packet_tracer_version: str | None = None


def capability_catalog_for(
    packet_tracer_version: str | None = None,
    *,
    capability_store: CapabilitySnapshotStore | None = None,
) -> EnterpriseCapabilityAdapter:
    """Raiz de composicion por version exacta, o adapter desnudo sin version."""
    if packet_tracer_version is None:
        return EnterpriseCapabilityAdapter()
    return packet_tracer_enterprise_capability_adapter(
        packet_tracer_version, store=capability_store,
    )


def plan_enterprise_hardware(
    enterprise_plan: EnterprisePlan,
    *,
    packet_tracer_version: str | None = None,
    policy: HardwarePlanningPolicy | None = None,
    capability_store: CapabilitySnapshotStore | None = None,
    capability_catalog: EnterpriseCapabilityAdapter | None = None,
) -> EnterpriseHardwareComposition:
    """Compone evidencia de capacidad y planificacion fisica en un HardwarePlan."""
    catalog = capability_catalog or capability_catalog_for(
        packet_tracer_version, capability_store=capability_store,
    )
    switch_candidates = catalog.hardware_candidates("switch", packet_tracer_version)
    router_candidates = catalog.hardware_candidates("router", packet_tracer_version)
    plan = HardwarePlanner().plan(
        enterprise_plan,
        switch_candidates,
        router_candidates,
        policy or HardwarePlanningPolicy(),
    )
    return EnterpriseHardwareComposition(
        plan=plan,
        switch_candidates=switch_candidates,
        router_candidates=router_candidates,
        packet_tracer_version=packet_tracer_version,
    )
