"""Calibrar `child.vlanId` contra un puerto cuya VLAN se leyó, no se supuso.

Dos LIVE gobernados leyeron `vlanId = 20` en los dos lados del enlace DHCP de
PHONE-02 y ninguno pudo decir qué SIGNIFICA ese 20: en ninguna de las dos
ventanas entró un frame por un puerto cuya VLAN fuera conocida de forma
independiente, así que el campo quedó
`DIRECT_PROPERTY_ONLY_NOT_GLOBALLY_QUALIFIED`.

Esta pasada es lo más chico que puede cerrar eso, y es hermana de
`qualify_access_port_readback`: mismo contrato de aislamiento, mismo prefijo
reservado, misma limpieza en orden inverso.

## Por qué el lado importa

Un control califica `vlanId` sólo cuando el puerto de VLAN conocida es el de
ENTRADA del frame. La VLAN esperada sale del puerto por el que el frame entró y
el valor observado se lee en el hijo de ESE mismo lado, así que no hace falta
ninguna suposición sobre lo que el switch hace entre una boca y la otra.

Emparejar la VLAN de un puerto de SALIDA con el tag del lado de entrada sería la
tentación obvia -- la copia con tag está justo ahí --, pero asumiría que el
switch preserva la VLAN a través del reenvío: comportamiento L2 corriente que
este repositorio no ha medido. Una calibración apoyada en una suposición no
medida no califica nada.

## APLICADO no es VERIFICADO

La VLAN esperada NO puede salir del plan tipado. Para cada puerto de control
hace falta que la lectura DIRECTA del backend -- `getAccessVlan()`, por la vía
de verificación que este repositorio ya usa -- haya coincidido con la VLAN
pedida. Un puerto aplicado y no leído no prueba ninguna VLAN, y un puerto que
además reclama VLAN de voz no puede calibrar nada: con datos Y voz, cualquiera
de los dos valores parecería correcto.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from typing import Protocol

from ...domain.enterprise.models.configuration import (
    ConfigurationPhase,
    ConfigureAccessPort,
    CreateVlan,
    VerificationExpectation,
    VerificationKind,
)
from ...domain.enterprise.models.execution import MutationDisposition
from ...domain.enterprise.models.physical_deployment import (
    PhysicalWorkspaceObservation,
    physical_workspace_restoration_matches,
)
from ...domain.models.plans import DevicePlan, LinkPlan

#: Prefijo reservado, con la misma intención que `__MCP_APQUAL_`: que la
#: limpieza sea auditable y que nadie confunda un desechable con algo del
#: operador.
CALIBRATION_PREFIX = "__MCP_VLANCAL_"

#: Las DOS VLAN de control. Distintas entre sí para que dos coincidencias sean
#: dos calibraciones y no una observada dos veces; fuera del rango reservado por
#: PT y distintas de la VLAN por defecto, para que "coincidió" nunca pueda
#: confundirse con un valor que el backend puso solo.
CONTROL_VLAN_IDS = (742, 743)


def _finite_vlan(value: object) -> int | float | None:
    """Un número finito, o nada. `True` no es 1 y `"742"` no es 742."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value if value == value and value not in (float("inf"), float("-inf")) else None


@dataclass(frozen=True)
class VlanCalibrationControl:
    """UN puerto de control, y qué se pudo probar sobre él.

    Cada dimensión se decide por separado: que el puerto se haya configurado no
    dice que se haya leído, que se haya leído no dice que el frame sea el que
    entró por ahí, y que el frame sea el correcto no dice que su hijo trajera un
    número.
    """

    vlan_id: int
    switch_interface: str = ""
    endpoint_name: str = ""
    #: La lectura DIRECTA del backend coincidió con `vlan_id`. Sin esto la VLAN
    #: esperada sería la intención del plan, que no prueba nada.
    access_vlan_verified: bool = False
    #: Un puerto de datos Y voz no puede calibrar: cualquiera de los dos valores
    #: parecería correcto.
    voice_vlan_claimed: bool = False
    frame_index: int | None = None
    frame_observed_in_port: str = ""
    frame_previous_device: str = ""
    identity_reconfirmed: bool = False
    child_returned: bool = False
    observed_vlan: object = None
    failure_reason: str = ""

    @property
    def expected_vlan_qualified(self) -> bool:
        """Si este puerto puede sostener una VLAN esperada."""
        return self.access_vlan_verified and not self.voice_vlan_claimed

    @property
    def match(self) -> str:
        """YES, NO o UNOBSERVABLE, decidido sólo con lo observado."""
        if not self.expected_vlan_qualified or not self.identity_reconfirmed:
            return "UNOBSERVABLE"
        observed = _finite_vlan(self.observed_vlan)
        if observed is None:
            return "UNOBSERVABLE"
        return "YES" if observed == self.vlan_id else "NO"


@dataclass(frozen=True)
class FrameVlanCalibrationResult:
    """Lo observado por la pasada entera. No decide nada fuera de sí misma."""

    model: str = ""
    switch_name: str = ""
    controls: tuple[VlanCalibrationControl, ...] = ()
    baseline_inventory: PhysicalWorkspaceObservation | None = None
    final_inventory: PhysicalWorkspaceObservation | None = None
    restored: bool | None = None
    realtime_restored: bool | None = None
    removed: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()

    @property
    def semantics(self) -> str:
        """Hasta dónde queda calificado `vlanId`, y nunca más allá."""
        judged = [item for item in self.controls if item.match != "UNOBSERVABLE"]
        if any(item.match == "NO" for item in judged):
            # Una contradicción medida decide sola y no se promedia contra las
            # que sí coincidieron.
            return "CONTRADICTED_BY_CONTROL"
        matched = [item for item in judged if item.match == "YES"]
        if len(matched) >= 2 and len({item.vlan_id for item in matched}) >= 2:
            return "STRONGLY_SUPPORTED_BY_MULTIVLAN_CONTROL"
        if matched:
            return "SUPPORTED_BY_CONTROL"
        return "DIRECT_PROPERTY_ONLY_NOT_GLOBALLY_QUALIFIED"


class CalibrationPhysicalRuntime(Protocol):
    def observe_workspace(self) -> PhysicalWorkspaceObservation: ...
    def ensure_device(self, device: DevicePlan): ...
    def observe_device(self, device: DevicePlan): ...
    def remove_device(self, device: DevicePlan): ...
    def ensure_link(self, link: LinkPlan): ...


class CalibrationConfigurationRuntime(Protocol):
    def inventory(self) -> list: ...
    def apply_actions(self, actions) -> list: ...
    def verify(self, expectations) -> list: ...


class CalibrationEndpointRuntime(Protocol):
    def configure_endpoint_dhcp(
        self, device: str, interface: str = "FastEthernet0",
    ) -> bool: ...


class CalibrationSimulationRuntime(Protocol):
    def read_simulation_state(self): ...
    def set_simulation_mode(self, on: bool): ...
    def step(self, action: str = "forward", times: int = 1): ...
    def read_trace(self, limit: int = 200, device: str = ""): ...


class CalibrationFrameProbe(Protocol):
    def discover_frame_observers(self, indices, *, timeout: float = 10.0): ...


#: Cuántos frames del switch se piden como máximo, y cuántos índices se
#: enumeran. Un control por VLAN basta: enumerar de más convertiría una
#: calibración acotada en un barrido.
TRACE_LIMIT = 200
MAX_ENUMERATED = 2


class FrameVlanCalibrationQualifier:
    """Califica `vlanId` con su propio switch desechable y su propio endpoint.

    Sólo el lado de ENTRADA califica, así que el endpoint cuelga del puerto de
    acceso y el frame que se mide es el que ENTRÓ por ese puerto. Nada aquí lee
    el lado de salida ni deriva una VLAN de un reenvío.
    """

    def __init__(
        self,
        physical: CalibrationPhysicalRuntime,
        configuration: CalibrationConfigurationRuntime,
        endpoints: CalibrationEndpointRuntime,
        simulation: CalibrationSimulationRuntime,
        probe: CalibrationFrameProbe,
        *,
        name_token: str = "",
        step_batches: int = 6,
        step_batch_size: int = 40,
    ) -> None:
        self._physical = physical
        self._configuration = configuration
        self._endpoints = endpoints
        self._simulation = simulation
        self._probe = probe
        self._token = name_token or secrets.token_hex(3)
        self._step_batches = step_batches
        self._step_batch_size = step_batch_size

    # -- nombres reservados --------------------------------------------
    def _switch_name(self) -> str:
        return f"{CALIBRATION_PREFIX}{self._token}_SW"

    def _endpoint_name(self, position: int) -> str:
        return f"{CALIBRATION_PREFIX}{self._token}_PC{position}"

    def qualify(
        self,
        switch_model: str,
        endpoint_model: str,
        *,
        require_empty_workspace: bool = True,
    ) -> FrameVlanCalibrationResult:
        errors: list[str] = []
        try:
            baseline = self._physical.observe_workspace()
        except Exception as exc:  # noqa: BLE001 - la pasada reporta, no decide
            return FrameVlanCalibrationResult(
                model=switch_model,
                errors=(f"Read-only workspace inventory failed: {exc}",),
            )
        if require_empty_workspace and not baseline.safe_for_disposable_mutation:
            return FrameVlanCalibrationResult(
                model=switch_model,
                baseline_inventory=baseline,
                errors=(
                    "The workspace inventory is not a complete empty baseline "
                    f"(observed={baseline.observed}, "
                    f"semantic_devices={len(baseline.semantic_devices)}, "
                    f"links={len(baseline.links)}); the calibration refuses to "
                    "mutate a workspace it did not find empty.",
                ),
            )

        created: list[DevicePlan] = []
        controls: tuple[VlanCalibrationControl, ...] = ()
        original_simulation: bool | None = None
        realtime_restored: bool | None = None
        try:
            original_simulation, controls, step_errors = self._measure(
                switch_model, endpoint_model, created,
            )
            errors.extend(step_errors)
        except Exception as exc:  # noqa: BLE001 - la limpieza manda
            errors.append(f"calibration_raised: {type(exc).__name__}: {exc}")
        finally:
            realtime_restored, restore_errors = self._restore_mode(original_simulation)
            errors.extend(restore_errors)
            removed, cleanup_errors, final, restored = self._cleanup(created, baseline)
            errors.extend(cleanup_errors)

        return FrameVlanCalibrationResult(
            model=switch_model,
            switch_name=self._switch_name(),
            controls=controls,
            baseline_inventory=baseline,
            final_inventory=final,
            restored=restored,
            realtime_restored=realtime_restored,
            removed=tuple(removed),
            errors=tuple(errors),
        )

    # -- la pasada -----------------------------------------------------
    def _measure(self, switch_model: str, endpoint_model: str, created):
        errors: list[str] = []
        switch = DevicePlan(
            id="vlancal/sw", name=self._switch_name(), model=switch_model,
            category="", x=9400, y=9400,
        )
        if not self._create(switch, created, errors):
            return None, (), errors

        try:
            observation = self._physical.observe_device(switch)
        except Exception as exc:  # noqa: BLE001
            return None, (), [*errors, f"switch_observation_raised: {exc}"]
        ports = tuple(
            str(getattr(item, "name", item))
            for item in getattr(observation, "interfaces", ()) or ()
        )
        access_ports = tuple(
            item for item in ports if item.casefold().startswith("fastethernet")
        )
        if len(access_ports) < len(CONTROL_VLAN_IDS):
            return None, (), [
                *errors,
                "The disposable switch exposed "
                f"{len(access_ports)} FastEthernet port(s); "
                f"{len(CONTROL_VLAN_IDS)} are required, one per control VLAN.",
            ]

        endpoints: list[tuple[str, str, int]] = []
        for position, vlan_id in enumerate(CONTROL_VLAN_IDS):
            endpoint = DevicePlan(
                id=f"vlancal/pc{position}", name=self._endpoint_name(position),
                model=endpoint_model, category="",
                x=9400 + 220 * (position + 1), y=9600,
            )
            if not self._create(endpoint, created, errors):
                return None, (), errors
            interface = access_ports[position]
            try:
                link = self._physical.ensure_link(LinkPlan(
                    id=f"vlancal/link{position}",
                    device_a=endpoint.name, port_a="FastEthernet0",
                    device_b=switch.name, port_b=interface,
                    cable="straight",
                ))
            except Exception as exc:  # noqa: BLE001
                return None, (), [*errors, f"link_raised: {exc}"]
            if not getattr(link, "applied", False):
                return None, (), [
                    *errors,
                    f"link_not_created for {interface!r}: "
                    f"{getattr(link, 'message', '')}",
                ]
            endpoints.append((endpoint.name, interface, vlan_id))

        verified = self._configure_and_read_back(switch.name, endpoints, errors)
        armed = self._arm_endpoints(endpoints, errors)
        original, frames, sim_errors = self._observe_ingress(switch.name, endpoints)
        errors.extend(sim_errors)

        controls = tuple(
            self._control(name, interface, vlan_id, verified, armed, frames)
            for name, interface, vlan_id in endpoints
        )
        return original, controls, errors

    def _create(self, device: DevicePlan, created, errors) -> bool:
        try:
            creation = self._physical.ensure_device(device)
        except Exception as exc:  # noqa: BLE001
            # Una excepción no prueba que el device NO exista: se registra para
            # limpieza igual, porque borrar lo que no está es barato y dejar
            # puesto lo que sí está no lo es.
            created.append(device)
            errors.append(f"device_creation_raised: {type(exc).__name__}: {exc}")
            return False
        if not creation.applied:
            if creation.disposition is MutationDisposition.UNKNOWN:
                created.append(device)
            errors.append(f"device_not_created: {creation.message}")
            return False
        created.append(device)
        return True

    def _configure_and_read_back(self, switch_name, endpoints, errors) -> dict:
        """Aplica y luego LEE. Aplicado no es verificado y no se confunden.

        La VLAN esperada de un control sale de esta lectura directa, nunca de la
        acción tipada: una acción dice lo que se pidió, no lo que el backend
        tiene.
        """
        actions: list = []
        expectations: list = []
        for position, (_name, interface, vlan_id) in enumerate(endpoints):
            actions.append(CreateVlan(
                id=f"vlancal/vlan/{vlan_id}",
                phase=ConfigurationPhase.L2_DEFINITIONS,
                device_id="vlancal/sw", device_name=switch_name,
                site_id="vlancal", vlan_id=vlan_id, name=f"VLANCAL{vlan_id}",
            ))
            action_id = f"vlancal/access/{position}"
            actions.append(ConfigureAccessPort(
                id=action_id,
                phase=ConfigurationPhase.L2_INTERFACES,
                device_id="vlancal/sw", device_name=switch_name,
                site_id="vlancal", interface=interface, data_vlan_id=vlan_id,
                # Sin VLAN de voz: un puerto de datos Y voz no puede calibrar
                # nada, porque cualquiera de los dos valores parecería correcto.
                voice_vlan_id=None,
            ))
            expectations.append(VerificationExpectation(
                id=f"vlancal/verify/{position}", action_id=action_id,
                kind=VerificationKind.ACCESS_PORT, device_id="vlancal/sw",
                device_name=switch_name,
                expected={"interface": interface, "vlan_id": vlan_id},
            ))
        try:
            self._configuration.apply_actions(actions)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"configuration_raised: {type(exc).__name__}: {exc}")
            return {}
        try:
            results = self._configuration.verify(expectations)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"verification_raised: {type(exc).__name__}: {exc}")
            return {}

        by_expectation = {
            f"vlancal/verify/{position}": interface
            for position, (_n, interface, _v) in enumerate(endpoints)
        }
        verified: dict[str, bool] = {}
        for item in results or ():
            interface = by_expectation.get(getattr(item, "expectation_id", ""))
            if interface is None:
                continue
            fields = getattr(item, "fields", {}) or {}
            status = fields.get("vlan_id")
            # El campo se decide solo: una verificación global "verified" no
            # sustituye a la lectura de ESTE campo, y una lectura que no es
            # fresca no prueba el estado de ahora.
            verified[interface] = bool(
                getattr(item, "fresh_evidence", False)
                and str(getattr(status, "value", status)).casefold() == "verified"
            )
        return verified

    def _arm_endpoints(self, endpoints, errors) -> dict:
        """Arma el cliente DHCP en Realtime; nadie tipea en una terminal.

        El disparador es el que este repositorio YA midió: un endpoint con
        cliente DHCP y sin servidor que le responda reintenta, y esos reintentos
        entran al switch por su puerto de acceso y aparecen en el event list de
        Simulación. Un ping tipado NO sirve acá: su ejecutor espera una ventana
        fresca de terminal que en Simulación no puede llegar sin avanzar el
        reloj, y esa composición no está medida.
        """
        armed: dict[str, bool] = {}
        for name, interface, _vlan_id in endpoints:
            try:
                armed[interface] = bool(
                    self._endpoints.configure_endpoint_dhcp(name)
                )
            except Exception as exc:  # noqa: BLE001
                armed[interface] = False
                errors.append(f"endpoint_arming_raised for {name!r}: {exc}")
        return armed

    def _observe_ingress(self, switch_name, endpoints):
        """Entra a Simulación, avanza acotado y enumera SOLO lo que entró."""
        errors: list[str] = []
        try:
            state = self._simulation.read_simulation_state()
        except Exception as exc:  # noqa: BLE001
            return None, {}, [f"simulation_state_raised: {exc}"]
        original = bool(getattr(state, "simulation_mode", False))
        if not original:
            try:
                self._simulation.set_simulation_mode(True)
            except Exception as exc:  # noqa: BLE001
                return original, {}, [f"simulation_mode_raised: {exc}"]
        try:
            self._simulation.step("reset")
            for _batch in range(self._step_batches):
                self._simulation.step("forward", self._step_batch_size)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"simulation_step_raised: {exc}")
        try:
            trace = self._simulation.read_trace(
                limit=TRACE_LIMIT, device=switch_name,
            )
        except Exception as exc:  # noqa: BLE001
            return original, {}, [*errors, f"trace_raised: {exc}"]

        wanted = {interface: name for name, interface, _v in endpoints}
        targets: dict[str, dict] = {}
        for hop in getattr(trace, "hops", ()) or ():
            interface = str(getattr(hop, "in_port", "") or "")
            expected_name = wanted.get(interface)
            # Sólo ENTRADA, y sólo desde el endpoint que cuelga de ESE puerto.
            if expected_name is None or interface in targets:
                continue
            if str(getattr(hop, "previous_device", "") or "") != expected_name:
                continue
            index = getattr(hop, "index", None)
            if not isinstance(index, int):
                continue
            targets[interface] = {
                "index": index,
                "previous_device": expected_name,
                "in_port": interface,
                "sim_time": getattr(hop, "sim_time", None),
                "traffic_type_raw": getattr(hop, "traffic_type_raw", None),
            }
        if not targets:
            errors.append(
                "No frame ENTERED a calibration access port in this bounded "
                "window; absence here is a property of the window, not proof "
                "that the endpoints sent nothing."
            )
            return original, {}, errors

        indices = [row["index"] for row in list(targets.values())[:MAX_ENUMERATED]]
        try:
            discovery = self._probe.discover_frame_observers(indices)
        except Exception as exc:  # noqa: BLE001
            return original, {}, [*errors, f"frame_probe_raised: {exc}"]
        by_index = {item.index: item for item in getattr(discovery, "frames", ())}
        for row in targets.values():
            frame = by_index.get(row["index"])
            row["frame"] = frame
            row["identity_reconfirmed"] = bool(
                frame is not None
                and frame.matches(
                    device=switch_name,
                    sim_time=row.get("sim_time"),
                    traffic_type=row.get("traffic_type_raw"),
                    in_port=row["in_port"],
                )
            )
        return original, targets, errors

    def _control(self, name, interface, vlan_id, verified, armed, frames):
        row = frames.get(interface) or {}
        frame = row.get("frame")
        observed = None
        child_returned = False
        reason = ""
        if frame is not None and row.get("identity_reconfirmed"):
            child = next(
                (
                    item for item in getattr(frame, "children", ())
                    if item.getter == "getInFrame"
                ),
                None,
            )
            if child is None or child.returned_null:
                reason = "getInFrame returned no object, so there is no tag."
            else:
                child_returned = True
                field = child.tag_by_name.get("vlanId")
                if field is None or not field.observed:
                    reason = "The ingress child exposed no readable vlanId."
                else:
                    observed = field.numeric_value
        elif not row:
            reason = (
                f"No frame entered {interface!r} from {name!r} in this window."
            )
        else:
            reason = (
                "The enumerated frame could not be re-attributed to this "
                "ingress port."
            )
        if not verified.get(interface, False):
            reason = reason or (
                "The access VLAN was applied but never read back, so no "
                "expected VLAN is established for this port."
            )
        if not armed.get(interface, False):
            reason = reason or "The endpoint DHCP client could not be armed."
        return VlanCalibrationControl(
            vlan_id=vlan_id,
            switch_interface=interface,
            endpoint_name=name,
            access_vlan_verified=bool(verified.get(interface, False)),
            voice_vlan_claimed=False,
            frame_index=row.get("index"),
            frame_observed_in_port=str(row.get("in_port") or ""),
            frame_previous_device=str(row.get("previous_device") or ""),
            identity_reconfirmed=bool(row.get("identity_reconfirmed")),
            child_returned=child_returned,
            observed_vlan=observed,
            failure_reason=reason,
        )

    # -- devolver la aplicación como estaba ----------------------------
    def _restore_mode(self, original: bool | None):
        """El modo se devuelve y se VERIFICA con otra lectura pura."""
        if original is None:
            return None, []
        errors: list[str] = []
        try:
            self._simulation.set_simulation_mode(original)
            state = self._simulation.read_simulation_state()
        except Exception as exc:  # noqa: BLE001
            return False, [f"mode_restoration_raised: {exc}"]
        restored = bool(
            getattr(state, "observed", False)
            and bool(getattr(state, "simulation_mode", False)) == original
        )
        if not restored:
            errors.append(
                "The original Simulation/Realtime mode could not be verified "
                "after restoration."
            )
        return restored, errors

    def _cleanup(self, created: list[DevicePlan], baseline):
        removed: list[str] = []
        errors: list[str] = []
        # Orden inverso, y SÓLO lo que esta pasada creó. Un objeto que se
        # parece a un desechable no es un desechable de esta pasada.
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
