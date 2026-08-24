"""Medir el inventario de puertos REAL de un modelo, en un estado de modulo dado.

Por que existe:
`_port_evidence_errors` rechaza, antes de mutar nada, cualquier nombre de puerto
concreto que ninguna medicion autorice en este backend y esta build. Ese gate es
correcto y no se relaja. Pero hasta ahora la unica forma de producir la evidencia
que lo satisface era que una corrida del producto desplegara el modelo y lo
releyera -- lo que hizo MEG-4 run 2 para `2911`, `IE-2000` y `PC-PT`. Un modelo
que la corrida todavia no puede desplegar, porque el gate lo rechaza, no podia
adquirir su evidencia por ningun camino. Eso es lo que bloquea a MEG-5: la
referencia selecciona `1941` y `2950T-24`, y ninguno esta medido.

Esto cierra ese circulo sin tocar el gate: una pasada de cualificacion ACOTADA
que crea un dispositivo desechable por par (modelo, estado de modulo), lo relee
por el MISMO seam de produccion que usa el despliegue
(`PacketTracerPhysicalTopologyRuntime.observe_device`), y lo borra. Reutiliza las
primitivas que ya existen; no reimplementa ninguna.

## Lo que NO hace, a proposito

* **No escribe evidencia.** Devuelve observaciones tipadas. Pinchar un
  `BackendVerifiedPortInventory` en `measured_port_inventories.py` es un acto
  deliberado y versionado, porque esa evidencia tiene que sobrevivir a un
  checkout: es la diferencia entre una medicion reproducible y un estado de
  maquina. Un caso de uso que se auto-otorgara evidencia seria exactamente el
  agujero que el gate existe para cerrar.
* **No infiere.** Si la relectura no observa interfaces, la entrada sale
  `observed=False` y sin puertos. Una lista vacia no se confunde con "sin
  puertos": `interfaces_observed` es un campo aparte.
* **No reclama nada sobre modulos.** Instalar el modulo es un prerrequisito para
  que los puertos existan, no una afirmacion sobre identidad de modulo, que
  sigue bajo `TD-MODULE-SLOT-001`. Si la insercion no se aplica, la entrada se
  marca `module_applied=False` y no se emite inventario: medir un 1941 sin su
  HWIC y llamarlo "1941 con HWIC" seria fabricar evidencia.

## Limpieza

Cada dispositivo se borra en orden inverso, pase lo que pase, y el inventario
del workspace se vuelve a observar al final. `restored` compara contra la
linea base con el mismo predicado que usa el producto.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass, field

from ...domain.enterprise.models.physical_deployment import (
    PhysicalWorkspaceObservation,
    physical_workspace_restoration_matches,
)
from ...domain.enterprise.models.execution import MutationDisposition
from ...domain.enterprise.models.port_inventory import BackendVerifiedPortInventory
from ...domain.models.plans import DevicePlan, ModulePlan
from ...infrastructure.catalog.measured_port_inventories import module_state_token

#: Prefijo reservado para los dispositivos de esta pasada. Comparte intencion
#: con `__MCP_PROBE_` del descubrimiento de capacidades: hace que la limpieza
#: sea auditable y que nadie confunda un desechable con algo del operador.
QUALIFICATION_PREFIX = "__MCP_PORTQUAL_"


@dataclass(frozen=True)
class PortInventoryTarget:
    """Un par (modelo, estado de modulo) a medir. `slot` vacio = sin modulo."""

    model: str
    module: str = ""
    slot: str = ""

    @property
    def module_state(self) -> tuple[str, ...]:
        if not self.module:
            return ()
        return (module_state_token(self.module, self.slot),)

    @property
    def label(self) -> str:
        state = ", ".join(self.module_state)
        return f"{self.model}[{state}]" if state else self.model


@dataclass(frozen=True)
class PortInventoryMeasurement:
    """Lo que la relectura observo para un objetivo, y nada mas."""

    target: PortInventoryTarget
    observed: bool
    interfaces_observed: bool
    observed_model: str = ""
    ports: tuple[str, ...] = ()
    module_applied: bool | None = None
    message: str = ""

    @property
    def usable(self) -> bool:
        """Si esta medicion puede convertirse en evidencia pinchable.

        Exige las tres cosas por separado: que el device se releyera, que la
        lectura de interfaces cerrara, y -- cuando el objetivo declara modulo --
        que la insercion se haya aplicado de verdad.
        """
        if not (
            self.observed
            and self.interfaces_observed
            and self.observed_model == self.target.model
            and self.ports
        ):
            return False
        return self.module_applied is not False

    def as_evidence(self, *, backend: str, backend_version: str, source: str):
        """El inventario tipado, o None si la medicion no lo sostiene."""
        if not self.usable:
            return None
        return BackendVerifiedPortInventory(
            model=self.target.model,
            backend=backend,
            backend_version=backend_version,
            installed_modules=list(self.target.module_state),
            ports=list(self.ports),
            source=source,
        )


@dataclass(frozen=True)
class PortInventoryQualificationResult:
    measurements: tuple[PortInventoryMeasurement, ...] = ()
    baseline_inventory: PhysicalWorkspaceObservation | None = None
    final_inventory: PhysicalWorkspaceObservation | None = None
    restored: bool | None = None
    removed: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()

    @property
    def usable_measurements(self) -> tuple[PortInventoryMeasurement, ...]:
        return tuple(item for item in self.measurements if item.usable)


class PortInventoryQualifier:
    """Cualifica inventarios de puertos con dispositivos desechables propios."""

    def __init__(self, physical, *, name_token: str = "") -> None:
        self._physical = physical
        self._token = name_token or secrets.token_hex(3)

    def qualify(
        self, targets, *, require_empty_workspace: bool = True,
    ) -> PortInventoryQualificationResult:
        targets = list(targets)
        errors: list[str] = []
        measurements: list[PortInventoryMeasurement] = []
        created: list[DevicePlan] = []

        try:
            baseline = self._physical.observe_workspace()
        except Exception as exc:
            return PortInventoryQualificationResult(
                errors=(f"Read-only workspace inventory failed: {exc}",),
            )
        if require_empty_workspace and not baseline.safe_for_disposable_mutation:
            # Mismo criterio que el producto: sobre un workspace ajeno no se
            # crea nada, ni siquiera desechable.
            return PortInventoryQualificationResult(
                baseline_inventory=baseline,
                errors=(
                    "The workspace inventory is not a complete empty baseline "
                    f"(observed={baseline.observed}, "
                    f"semantic_devices={len(baseline.semantic_devices)}, "
                    f"links={len(baseline.links)}); "
                    "the qualification refuses to mutate a workspace it did not find empty.",
                ),
            )

        try:
            for index, target in enumerate(targets):
                device = self._plan(target, index)
                measurement, was_created = self._measure(target, device)
                if was_created:
                    created.append(device)
                measurements.append(measurement)
        finally:
            removed, cleanup_errors, final, restored = self._cleanup(created, baseline)
            errors.extend(cleanup_errors)

        return PortInventoryQualificationResult(
            measurements=tuple(measurements),
            baseline_inventory=baseline,
            final_inventory=final,
            restored=restored,
            removed=tuple(removed),
            errors=tuple(errors),
        )

    # -- por objetivo --------------------------------------------------
    def _plan(self, target: PortInventoryTarget, index: int) -> DevicePlan:
        return DevicePlan(
            id=f"portqual/{index:02d}",
            name=f"{QUALIFICATION_PREFIX}{self._token}_{index:02d}",
            model=target.model,
            category="",
            x=9000 + index * 60,
            y=9000,
        )

    def _measure(
        self, target: PortInventoryTarget, device: DevicePlan,
    ) -> tuple[PortInventoryMeasurement, bool]:
        try:
            creation = self._physical.ensure_device(device)
        except Exception as exc:
            return (
                PortInventoryMeasurement(
                    target=target, observed=False, interfaces_observed=False,
                    message=f"device_creation_raised: {type(exc).__name__}: {exc}",
                ),
                # La llamada pudo despacharse antes de perder su recibo. El
                # nombre es nuestro y el baseline era vacio: intentar borrarlo
                # es la unica salida que no puede filtrar un desechable.
                True,
            )
        if not creation.applied:
            return (
                PortInventoryMeasurement(
                    target=target, observed=False, interfaces_observed=False,
                    message=f"device_not_created: {creation.message}",
                ),
                creation.disposition is MutationDisposition.UNKNOWN,
            )

        module_applied: bool | None = None
        if target.module:
            module = ModulePlan(
                device=device.name, slot=target.slot, module=target.module,
            )
            try:
                insertion = self._physical.ensure_module(module)
                module_applied = bool(insertion.applied)
                module_message = insertion.message
            except Exception as exc:
                module_applied = False
                module_message = f"{type(exc).__name__}: {exc}"
            if not module_applied:
                # Sin la tarjeta, los puertos que la referencia planea no
                # existen. Medir igual y pincharlo seria evidencia falsa.
                return (
                    PortInventoryMeasurement(
                        target=target, observed=False, interfaces_observed=False,
                        module_applied=False,
                        message=f"module_not_applied: {module_message}",
                    ),
                    True,
                )

        try:
            observation = self._physical.observe_device(device)
        except Exception as exc:
            return (
                PortInventoryMeasurement(
                    target=target, observed=False, interfaces_observed=False,
                    module_applied=module_applied,
                    message=f"observation_raised: {type(exc).__name__}: {exc}",
                ),
                True,
            )
        return (
            PortInventoryMeasurement(
                target=target,
                observed=bool(observation.observed),
                interfaces_observed=bool(observation.interfaces_observed),
                observed_model=observation.model or "",
                ports=tuple(observation.interfaces),
                module_applied=module_applied,
                message=observation.message or "",
            ),
            True,
        )

    # -- limpieza ------------------------------------------------------
    def _cleanup(self, created, baseline):
        removed: list[str] = []
        errors: list[str] = []
        for device in reversed(created):
            try:
                result = self._physical.remove_device(device)
            except Exception as exc:
                errors.append(f"Cleanup failed for {device.name!r}: {exc}")
                continue
            if result.applied:
                removed.append(device.name)
            elif result.disposition is not MutationDisposition.NO_OP:
                errors.append(f"Cleanup did not apply for {device.name!r}: {result.message}")

        try:
            final = self._physical.observe_workspace()
        except Exception as exc:
            errors.append(f"Final workspace inventory failed: {exc}")
            return removed, errors, None, None

        if baseline is None:
            return removed, errors, final, None
        return (
            removed,
            errors,
            final,
            physical_workspace_restoration_matches(baseline, final),
        )
