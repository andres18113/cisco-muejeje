"""Cualificar la lectura de un puerto de acceso contra el backend, no contra una idea.

`TD-ACCESSPORT-READBACK-001` lleva abierta porque nadie capturó nunca la salida
de un puerto de acceso en este backend, y su criterio de cierre lo dice con
todas las letras: la lectura tiene que quedar cualificada contra **salida real
capturada** de una sesión controlada sobre un switch desechable. Escribir el
parser primero sería inventar la evidencia.

Esta pasada produce esa captura y nada más. Es hermana de
`qualify_port_inventories`: mismo contrato de aislamiento, mismo prefijo
reservado, misma limpieza en orden inverso, y la misma abstención deliberada --
**no escribe evidencia ni decide nada**. Devuelve lo observado; convertirlo en
un parser pinchado es un acto aparte y versionado.

## Los tres controles, en la misma pasada

Un puerto se configura como acceso en una VLAN conocida, otro como troncal, y
un tercero se deja exactamente como vino. Los tres hacen falta y ninguno sobra:

* sin el **puerto por defecto**, una lectura que devolviera "vlan 1" para todo
  pasaría por correcta sobre el configurado;
* sin el **troncal**, el criterio "un puerto en modo troncal NO es un puerto de
  acceso verificado aunque su VLAN coincida" no tendría con qué medirse, y el
  refuse quedaría escrito contra una idea del modo en vez de contra el valor
  que este backend devuelve.

## Lo que NO hace

* **No afirma capacidad.** Que un getter exista no dice que su valor signifique
  lo que su nombre sugiere. Por eso el descubrimiento viaja junto al estado
  configurado: el lector compara, no confía.
* **No promueve nada.** `DHCP_POOL` comparte hoy la rama `_unobservable` y
  sigue exactamente donde estaba.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from typing import Protocol

from ...domain.enterprise.models.configuration import (
    ConfigurationPhase,
    ConfigureAccessPort,
    ConfigureTrunk,
    CreateVlan,
    VerificationExpectation,
    VerificationKind,
)
from ...domain.enterprise.models.configuration_runtime import RuntimeVerification
from ...domain.enterprise.models.execution import MutationDisposition
from ...domain.enterprise.models.physical_deployment import (
    PhysicalWorkspaceObservation,
    physical_workspace_restoration_matches,
)
from ...domain.models.plans import DevicePlan
from ...infrastructure.execution.access_port_probe import PortObserverDiscovery
from ...infrastructure.execution.ios_terminal import (
    IosCommandResult,
    OperationalQueryId,
)

#: Prefijo reservado para esta pasada, con la misma intención que
#: `__MCP_PROBE_` y `__MCP_PORTQUAL_`: que la limpieza sea auditable y que nadie
#: confunda un desechable con algo del operador.
QUALIFICATION_PREFIX = "__MCP_APQUAL_"

#: VLAN del control positivo. Fuera del rango reservado por PT y distinta de la
#: VLAN por defecto, para que "coincidió" y "se leyó" no puedan confundirse.
CONTROL_VLAN_ID = 742


class QualificationPhysicalRuntime(Protocol):
    def observe_workspace(self) -> PhysicalWorkspaceObservation: ...
    def ensure_device(self, device: DevicePlan): ...
    def observe_device(self, device: DevicePlan): ...
    def remove_device(self, device: DevicePlan): ...


class QualificationConfigurationRuntime(Protocol):
    def inventory(self) -> list: ...
    def apply_actions(self, actions) -> list: ...
    def verify(self, expectations) -> list: ...


class QualificationQueryRuntime(Protocol):
    def execute(
        self, device_name: str, query_id: OperationalQueryId, *, interface: str = "",
    ) -> IosCommandResult: ...


class QualificationObserverProbe(Protocol):
    def discover_port_observers(
        self, device_name: str, interface: str,
    ) -> PortObserverDiscovery: ...


@dataclass(frozen=True)
class AccessPortCapture:
    """Lo observado sobre UN puerto, con cada dimensión separada."""

    interface: str
    #: `None` marca el control negativo: el puerto no se configuró.
    expected_vlan: int | None
    configured: bool = False
    configuration_message: str = ""
    executed: bool = False
    fresh: bool = False
    complete: bool = False
    truncated: bool = False
    output: str = ""
    failure_reason: str = ""
    pages_captured: int = 0
    pagination: str = ""
    observed_device_name: str = ""
    device_identity_provenance: str = ""
    discovery: PortObserverDiscovery | None = None
    #: Lo que devuelve la lectura de produccion sobre ESTE puerto, pidiendole
    #: la VLAN del control positivo. En el puerto configurado tiene que
    #: verificar; en los otros dos tiene que negarse. Un lector que no se niega
    #: sobre un troncal no esta observando: esta coincidiendo.
    readback: RuntimeVerification | None = None

    @property
    def usable(self) -> bool:
        """Si esta captura puede sostener un parser pinchado."""
        return bool(self.executed and self.fresh and self.complete and self.output)


@dataclass(frozen=True)
class AccessPortReadbackQualificationResult:
    model: str = ""
    device_name: str = ""
    physical_ports: tuple[str, ...] = ()
    captures: tuple[AccessPortCapture, ...] = ()
    baseline_inventory: PhysicalWorkspaceObservation | None = None
    final_inventory: PhysicalWorkspaceObservation | None = None
    restored: bool | None = None
    removed: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()

    @property
    def usable_captures(self) -> tuple[AccessPortCapture, ...]:
        return tuple(item for item in self.captures if item.usable)


class AccessPortReadbackQualifier:
    """Cualifica la lectura de puerto de acceso con su propio switch desechable."""

    def __init__(
        self,
        physical: QualificationPhysicalRuntime,
        configuration: QualificationConfigurationRuntime,
        query: QualificationQueryRuntime,
        probe: QualificationObserverProbe | None = None,
        *,
        name_token: str = "",
    ) -> None:
        self._physical = physical
        self._configuration = configuration
        self._query = query
        self._probe = probe
        self._token = name_token or secrets.token_hex(3)

    def qualify(
        self, model: str, *, require_empty_workspace: bool = True,
    ) -> AccessPortReadbackQualificationResult:
        errors: list[str] = []
        try:
            baseline = self._physical.observe_workspace()
        except Exception as exc:  # noqa: BLE001 - la pasada reporta, no decide
            return AccessPortReadbackQualificationResult(
                model=model,
                errors=(f"Read-only workspace inventory failed: {exc}",),
            )
        if require_empty_workspace and not baseline.safe_for_disposable_mutation:
            return AccessPortReadbackQualificationResult(
                model=model,
                baseline_inventory=baseline,
                errors=(
                    "The workspace inventory is not a complete empty baseline "
                    f"(observed={baseline.observed}, "
                    f"semantic_devices={len(baseline.semantic_devices)}, "
                    f"links={len(baseline.links)}); "
                    "the qualification refuses to mutate a workspace it did not "
                    "find empty.",
                ),
            )

        device = DevicePlan(
            id="apqual/00",
            name=f"{QUALIFICATION_PREFIX}{self._token}_00",
            model=model,
            category="",
            x=9200,
            y=9200,
        )
        # La lista se pasa por referencia y el caso de uso la llena EN CUANTO
        # el dispositivo existe. Devolver "se creó" junto al resto del
        # resultado dejaba la limpieza ciega ante cualquier excepción posterior
        # a la creación, que es exactamente cómo se fuga un desechable.
        created: list[DevicePlan] = []
        ports: tuple[str, ...] = ()
        captures: tuple[AccessPortCapture, ...] = ()
        try:
            ports, captures, step_errors = self._measure(device, created)
            errors.extend(step_errors)
        except Exception as exc:  # noqa: BLE001 - la limpieza manda
            errors.append(f"qualification_raised: {type(exc).__name__}: {exc}")
        finally:
            removed, cleanup_errors, final, restored = self._cleanup(created, baseline)
            errors.extend(cleanup_errors)

        return AccessPortReadbackQualificationResult(
            model=model,
            device_name=device.name,
            physical_ports=ports,
            captures=captures,
            baseline_inventory=baseline,
            final_inventory=final,
            restored=restored,
            removed=tuple(removed),
            errors=tuple(errors),
        )

    # -- la pasada -----------------------------------------------------
    def _measure(self, device: DevicePlan, created: list[DevicePlan]):
        errors: list[str] = []
        try:
            creation = self._physical.ensure_device(device)
        except Exception as exc:  # noqa: BLE001
            # Una excepción no prueba que el device NO exista, así que se
            # registra para limpieza igual: borrar lo que no está es barato,
            # dejar puesto lo que sí está no lo es.
            created.append(device)
            return (), (), [f"device_creation_raised: {type(exc).__name__}: {exc}"]
        if not creation.applied:
            if creation.disposition is MutationDisposition.UNKNOWN:
                # Recibo ambiguo: la llamada puede haberse aplicado. El nombre
                # reservado y el baseline vacio permiten una limpieza exacta.
                created.append(device)
            return (), (), [f"device_not_created: {creation.message}"]
        created.append(device)

        try:
            observation = self._physical.observe_device(device)
        except Exception as exc:  # noqa: BLE001
            return (), (), [f"observation_raised: {type(exc).__name__}: {exc}"]
        ports = tuple(
            item for item in observation.interfaces
            if "Ethernet" in item and not item.lower().startswith("vlan")
        )


        if len(ports) < 3:
            return ports, (), [
                "Fewer than three Ethernet ports were observed; the trunk "
                "control cannot be established.",
            ]
        configured_port, trunk_port, control_port = ports[0], ports[1], ports[2]
        try:
            self._configuration.inventory()
        except Exception as exc:  # noqa: BLE001
            errors.append(f"inventory_raised: {type(exc).__name__}: {exc}")

        # El mismo par de acciones tipadas que compila el producto: la VLAN
        # existe antes de que un puerto la referencie. Aplicarlas por separado
        # sería inventar un orden que el compilador no emite.
        actions = [
            CreateVlan(
                id="apqual/create-vlan",
                phase=ConfigurationPhase.L2_DEFINITIONS,
                device_id=device.id,
                device_name=device.name,
                site_id="apqual",
                vlan_id=CONTROL_VLAN_ID,
                name="APQUAL",
            ),
            ConfigureAccessPort(
                id="apqual/access-port",
                phase=ConfigurationPhase.L2_INTERFACES,
                device_id=device.id,
                device_name=device.name,
                site_id="apqual",
                interface=configured_port,
                data_vlan_id=CONTROL_VLAN_ID,
            ),
            ConfigureTrunk(
                id="apqual/trunk-port",
                phase=ConfigurationPhase.L2_INTERFACES,
                device_id=device.id,
                device_name=device.name,
                site_id="apqual",
                interface=trunk_port,
                allowed_vlans=[CONTROL_VLAN_ID],
            ),
        ]
        applied = False
        message = ""
        try:
            mutations = self._configuration.apply_actions(actions)
            by_id = {item.action_id: item for item in mutations}
            port_mutation = by_id.get("apqual/access-port")
            applied = bool(port_mutation and port_mutation.applied)
            message = "; ".join(
                f"{key}: applied={bool(item and item.applied)}"
                for key, item in (
                    ("vlan", by_id.get("apqual/create-vlan")),
                    ("access", port_mutation),
                    ("trunk", by_id.get("apqual/trunk-port")),
                )
            )
            trunk_applied = bool(
                (trunk := by_id.get("apqual/trunk-port")) and trunk.applied
            )
            trunk_message = message
        except Exception as exc:  # noqa: BLE001
            message = f"{type(exc).__name__}: {exc}"
            trunk_applied = False
            trunk_message = message

        captures = (
            self._capture(device.name, configured_port, CONTROL_VLAN_ID, applied, message),
            self._capture(device.name, trunk_port, None, trunk_applied, "trunk control: " + trunk_message),
            self._capture(device.name, control_port, None, False, "default control: untouched"),
        )
        return ports, captures, errors

    def _capture(
        self,
        device_name: str,
        interface: str,
        expected_vlan: int | None,
        configured: bool,
        configuration_message: str,
    ) -> AccessPortCapture:
        discovery = None
        if self._probe is not None:
            try:
                discovery = self._probe.discover_port_observers(device_name, interface)
            except Exception as exc:  # noqa: BLE001
                discovery = PortObserverDiscovery(
                    interface=interface, error=f"{type(exc).__name__}: {exc}",
                )
        try:
            show = self._query.execute(
                device_name,
                OperationalQueryId.SHOW_INTERFACES_SWITCHPORT,
                interface=interface,
            )
        except Exception as exc:  # noqa: BLE001
            return AccessPortCapture(
                interface=interface,
                expected_vlan=expected_vlan,
                configured=configured,
                configuration_message=configuration_message,
                failure_reason=f"{type(exc).__name__}: {exc}",
                discovery=discovery,
                readback=self._readback(device_name, interface),
            )
        return AccessPortCapture(
            interface=interface,
            expected_vlan=expected_vlan,
            configured=configured,
            configuration_message=configuration_message,
            readback=self._readback(device_name, interface),
            executed=bool(show.executed),
            fresh=bool(show.fresh_output_observed),
            complete=bool(show.output_complete),
            truncated=bool(show.truncated_by_pager),
            output=show.output or "",
            failure_reason=show.failure_reason or "",
            pages_captured=int(show.pager_pages_captured),
            pagination=str(show.pager_continuation),
            observed_device_name=str(show.observed_device_name or ""),
            device_identity_provenance=str(show.device_identity_provenance or ""),
            discovery=discovery,
        )

    def _readback(self, device_name: str, interface: str) -> RuntimeVerification | None:
        """Corre la lectura de PRODUCCION sobre este puerto, sin adaptarla."""
        expectation = VerificationExpectation(
            id=f"apqual/verify/{interface}",
            action_id="apqual/access-port",
            kind=VerificationKind.ACCESS_PORT,
            device_id="apqual/00",
            device_name=device_name,
            expected={"interface": interface, "vlan_id": CONTROL_VLAN_ID},
        )
        try:
            results = self._configuration.verify([expectation])
        except Exception:  # noqa: BLE001 - la cualificacion reporta, no decide
            return None
        return results[0] if results else None

    # -- limpieza ------------------------------------------------------
    def _cleanup(self, created: list[DevicePlan], baseline):
        removed: list[str] = []
        errors: list[str] = []
        for device in reversed(created):
            try:
                result = self._physical.remove_device(device)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"Cleanup failed for {device.name!r}: {exc}")
                continue
            if result.applied:
                removed.append(device.name)
            elif result.disposition is not MutationDisposition.NO_OP:
                errors.append(
                    f"Cleanup did not apply for {device.name!r}: {result.message}"
                )

        try:
            final = self._physical.observe_workspace()
        except Exception as exc:  # noqa: BLE001
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
