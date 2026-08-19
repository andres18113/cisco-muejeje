"""Medir qué hace este backend cuando la MISMA acción E8 se aplica dos veces.

`TD-SECURITY-001` clasifica hoy a la familia ACL/NAT como
`TREAT_AS_REPLAY_UNSAFE_FOR_PRODUCT_SAFETY`. Esa clasificación es correcta como
postura de producto y **no es una medición**: la propia entrada dice que no
establece que Packet Tracer guarde ACEs duplicadas, sólo que la generación es
estructuralmente aditiva y que nadie lo comprobó. La corrección de Debt
Checkpoint 2 amplió el alcance: la reproducción tiene que cubrir los caminos
TIPADOS de seguridad y NAT, no sólo el generador suelto.

Esta pasada es esa reproducción. Aplica el MISMO lote tipado dos veces sobre un
router desechable, releyendo por consulta registrada después de cada pasada, y
devuelve las dos lecturas sin interpretarlas. Clasificar la familia es un acto
de gobernanza aparte, y se hace mirando estos números.

## Por qué dos lecturas y no una comparación interna

Una "aplicación idempotente" y "una segunda aplicación que duplicó" se
distinguen únicamente comparando el estado leído después de cada pasada. Contar
sólo al final no distingue "PT deduplica" de "el generador nunca emitió la
segunda copia", que son afirmaciones distintas sobre actores distintos.

## Lo que NO hace

* **No clasifica.** Devuelve filas observadas. Convertirlas en un veredicto de
  familia es una decisión gobernada.
* **No infiere comportamiento desde la relectura.** Que la ACE sea idéntica no
  dice que siga filtrando: eso se mide, y por eso la pasada opcionalmente
  levanta un slice de dos endpoints y lo pregunta con tráfico real.

## El slice de comportamiento, y por qué va en la MISMA pasada

El criterio pide relectura **y** verificación de comportamiento sobre la misma
reproducción. Medirlas en corridas distintas dejaría abierta la pregunta de si
el estado que se releyó es el estado que filtró. Con `endpoints=True` la pasada
construye un router con dos PCs, uno por subred, y mide en tres momentos:

```text
baseline      sin ACL          A -> B debe ALCANZAR
enforcement   tras aplicar     A -> B debe NO alcanzar; A -> gateway sí
replay        tras reaplicar   idéntico al anterior, o la reaplicación cambió algo
```

El control positivo -- A hacia su propio gateway -- es lo que separa "la ACL
denegó" de "la red se cayó". Sin él, un slice roto se leería como una ACL que
funciona.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass, field
from typing import Protocol

from ...domain.enterprise.models.physical_deployment import (
    PhysicalWorkspaceObservation,
    physical_workspace_restoration_matches,
)
from ...domain.enterprise.models.security_plan import (
    AddSecurityAclRule,
    AttachSecurityAcl,
    ConfigureSecurityNat,
    NatMode,
    SecurityAction,
    SecurityCapabilityDimension,
    SecurityDecision,
    SecurityPhase,
)
from ...domain.enterprise.models.configuration import (
    ConfigurationPhase,
    ConfigureRoutedInterface,
    SetEndpointStaticAddress,
)
from ...domain.models.plans import DevicePlan, LinkPlan
from ...infrastructure.execution.ios_terminal import (
    IosCommandResult,
    OperationalQueryId,
)
from ...infrastructure.execution.security_ios import (
    AccessListRuleRow,
    parse_show_access_lists,
)

#: Prefijo reservado, con la misma intención que `__MCP_PROBE_`,
#: `__MCP_PORTQUAL_` y `__MCP_APQUAL_`.
QUALIFICATION_PREFIX = "__MCP_SECQUAL_"

#: Cada número vive en el MISMO rango IOS que el compilador usa para su
#: familia, porque un número del rango equivocado no reproduce el camino del
#: producto: mide otra cosa. La primera versión de esta pasada puso la ACL de
#: traducción NAT en 182, y `access-list 182 permit <red> <wildcard>` es una ACE
#: estándar con un número extendido -- IOS la rechazó, la ACL nunca existió y la
#: lectura no midió replay sino un comando inválido.
#:
#: `security_compiler._extended_acl_number` asigna 100-199 a las ACL de filtrado
#: y la asignación NAT se queda en 1-99 con un comentario que dice exactamente
#: por qué. Estos controles siguen esa misma partición.
CONTROL_ACL_NUMBER = 181
CONTROL_NAT_ACL_NUMBER = 82
CONTROL_SOURCE_CIDR = "198.18.160.0/24"
CONTROL_DESTINATION_CIDR = "198.18.161.0/24"

#: El slice de comportamiento: dos subredes directamente conectadas, para que el
#: reenvío no dependa de ningún protocolo de enrutamiento y un fallo signifique
#: la ACL y no la convergencia.
_MASK = "255.255.255.0"
_INSIDE_GATEWAY = "198.18.160.1"
_INSIDE_HOST = "198.18.160.10"
_OUTSIDE_GATEWAY = "198.18.161.1"
_OUTSIDE_HOST = "198.18.161.10"


class ReplayPhysicalRuntime(Protocol):
    def observe_workspace(self) -> PhysicalWorkspaceObservation: ...
    def ensure_device(self, device: DevicePlan): ...
    def observe_device(self, device: DevicePlan): ...
    def remove_device(self, device: DevicePlan): ...


class ReplaySecurityRuntime(Protocol):
    def inventory(self) -> list: ...
    def apply_actions(self, actions) -> list: ...
    def cleanup_actions(self, actions) -> list: ...


class ReplayConfigurationRuntime(Protocol):
    def inventory(self) -> list: ...
    def apply_actions(self, actions) -> list: ...


class ReplayPingRuntime(Protocol):
    def ping(self, source_device: str, destination: str): ...


class ReplayQueryRuntime(Protocol):
    def execute(
        self, device_name: str, query_id: OperationalQueryId, *, interface: str = "",
    ) -> IosCommandResult: ...


@dataclass(frozen=True)
class FlowMeasurement:
    """Un flujo medido, con lo esperado declarado ANTES de mirarlo."""

    label: str
    source: str
    destination: str
    expected_reachable: bool
    reachable: bool = False
    fresh: bool = False
    attempts: int = 0
    statistics: str = ""

    @property
    def matched(self) -> bool:
        """Sólo una medida fresca puede coincidir con lo esperado."""
        return bool(self.fresh and self.reachable is self.expected_reachable)


@dataclass(frozen=True)
class ReplayReading:
    """Una relectura completa después de UNA pasada de aplicación."""

    pass_number: int
    applied: tuple[str, ...] = ()
    refused: tuple[str, ...] = ()
    acl_executed: bool = False
    acl_fresh: bool = False
    acl_complete: bool = False
    acl_rows: tuple[AccessListRuleRow, ...] = ()
    #: La salida CRUDA, además de las filas. `parse_show_access_lists` sólo
    #: reconoce cabeceras `Extended IP access list`, así que su silencio sobre
    #: una ACL estándar no prueba que la ACL no exista. Concluir desde las filas
    #: solas sería concluir desde el parser, no desde el backend.
    acl_output: str = ""
    nat_executed: bool = False
    nat_fresh: bool = False
    nat_output: str = ""
    #: Los flujos medidos DESPUÉS de esta pasada, si el slice existe.
    flows: tuple[FlowMeasurement, ...] = ()
    message: str = ""

    @property
    def behaviour_matched(self) -> bool | None:
        """`None` cuando no se midió comportamiento en esta pasada."""
        if not self.flows:
            return None
        return all(item.matched for item in self.flows)

    def rows_for(self, acl_name: str) -> tuple[AccessListRuleRow, ...]:
        return tuple(item for item in self.acl_rows if item.acl_name == acl_name)

    @property
    def readable(self) -> bool:
        """Si esta lectura puede sostener una comparación."""
        return bool(self.acl_executed and self.acl_fresh)


@dataclass(frozen=True)
class SecurityReplayQualificationResult:
    model: str = ""
    device_name: str = ""
    baseline_flows: tuple[FlowMeasurement, ...] = ()
    readings: tuple[ReplayReading, ...] = ()
    baseline_inventory: PhysicalWorkspaceObservation | None = None
    final_inventory: PhysicalWorkspaceObservation | None = None
    restored: bool | None = None
    removed: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()

    @property
    def comparable(self) -> bool:
        """Dos lecturas frescas es el mínimo para decir algo sobre replay."""
        return len(self.readings) == 2 and all(item.readable for item in self.readings)

    def duplication_for(self, acl_name: str) -> int | None:
        """Cuántas ACEs añadió la segunda pasada.

        `None` cuando no se puede afirmar: o las lecturas no son comparables, o
        esa ACL no se observó NUNCA. Devolver `0` para una ACL que nadie vio
        diría "no duplicó" sobre algo que ni siquiera se midió, que es la clase
        de silencio que esta deuda existe para no repetir.
        """
        if not self.comparable:
            return None
        first, second = self.readings
        if not first.rows_for(acl_name) and not second.rows_for(acl_name):
            return None
        return len(second.rows_for(acl_name)) - len(first.rows_for(acl_name))

    @property
    def behaviour_survived_the_replay(self) -> bool | None:
        """Si el comportamiento medido tras reaplicar es el mismo que antes.

        `None` cuando no hay con qué decidirlo: sin baseline alcanzable, un
        flujo bloqueado no distingue una ACL que filtra de una red que nunca
        funcionó.
        """
        if len(self.readings) != 2:
            return None
        if not all(item.matched for item in self.baseline_flows):
            return None
        verdicts = [item.behaviour_matched for item in self.readings]
        if any(item is None for item in verdicts):
            return None
        return all(verdicts)


class SecurityReplayQualifier:
    """Reproduce una aplicación repetida sobre su propio router desechable."""

    def __init__(
        self,
        physical: ReplayPhysicalRuntime,
        security: ReplaySecurityRuntime,
        query: ReplayQueryRuntime,
        *,
        configuration: ReplayConfigurationRuntime | None = None,
        ping: ReplayPingRuntime | None = None,
        name_token: str = "",
    ) -> None:
        self._physical = physical
        self._security = security
        self._query = query
        self._configuration = configuration
        self._ping = ping
        self._token = name_token or secrets.token_hex(3)

    @property
    def _can_measure_behaviour(self) -> bool:
        return self._configuration is not None and self._ping is not None

    def qualify(
        self, model: str, *, require_empty_workspace: bool = True,
    ) -> SecurityReplayQualificationResult:
        errors: list[str] = []
        try:
            baseline = self._physical.observe_workspace()
        except Exception as exc:  # noqa: BLE001 - la pasada reporta, no decide
            return SecurityReplayQualificationResult(
                model=model, errors=(f"Read-only workspace inventory failed: {exc}",),
            )
        if require_empty_workspace and baseline.semantic_devices:
            return SecurityReplayQualificationResult(
                model=model,
                baseline_inventory=baseline,
                errors=(
                    "The workspace already holds "
                    f"{len(baseline.semantic_devices)} semantic device(s); "
                    "the qualification refuses to mutate a workspace it did not "
                    "find empty.",
                ),
            )

        device = DevicePlan(
            id="secqual/00",
            name=f"{QUALIFICATION_PREFIX}{self._token}_00",
            model=model, category="", x=9400, y=9400,
        )
        created: list[DevicePlan] = []
        actions: list[SecurityAction] = []
        readings: tuple[ReplayReading, ...] = ()
        baseline_flows: tuple[FlowMeasurement, ...] = ()
        try:
            readings, baseline_flows, step_errors = self._measure(
                device, created, actions,
            )
            errors.extend(step_errors)
        except Exception as exc:  # noqa: BLE001 - la limpieza manda
            errors.append(f"qualification_raised: {type(exc).__name__}: {exc}")
        finally:
            errors.extend(self._undo(actions))
            removed, cleanup_errors, final, restored = self._cleanup(created, baseline)
            errors.extend(cleanup_errors)

        return SecurityReplayQualificationResult(
            model=model,
            device_name=device.name,
            baseline_flows=baseline_flows,
            readings=readings,
            baseline_inventory=baseline,
            final_inventory=final,
            restored=restored,
            removed=tuple(removed),
            errors=tuple(errors),
        )

    # -- la pasada -----------------------------------------------------
    def _measure(
        self, device: DevicePlan, created: list[DevicePlan], actions: list[SecurityAction],
    ):
        errors: list[str] = []
        try:
            creation = self._physical.ensure_device(device)
        except Exception as exc:  # noqa: BLE001
            created.append(device)
            return (), (), [f"device_creation_raised: {type(exc).__name__}: {exc}"]
        if not creation.applied:
            return (), (), [f"device_not_created: {creation.message}"]
        created.append(device)

        try:
            observation = self._physical.observe_device(device)
        except Exception as exc:  # noqa: BLE001
            return (), (), [f"observation_raised: {type(exc).__name__}: {exc}"]
        routed = tuple(
            item for item in observation.interfaces
            if "Ethernet" in item and not item.lower().startswith("vlan")
        )
        if len(routed) < 2:
            return (), (), [
                "Fewer than two routed Ethernet interfaces were observed; the "
                "NAT inside/outside pair cannot be established.",
            ]

        try:
            self._security.inventory()
        except Exception as exc:  # noqa: BLE001
            errors.append(f"inventory_raised: {type(exc).__name__}: {exc}")

        endpoints: tuple[str, str] | None = None
        baseline: tuple[FlowMeasurement, ...] = ()
        if self._can_measure_behaviour:
            endpoints, slice_errors = self._build_slice(device, created, routed)
            errors.extend(slice_errors)
            if endpoints is not None:
                baseline = self._flows(endpoints[0], expected_reachable=True)

        actions.extend(self._actions(device, routed[0], routed[1]))
        readings = tuple(
            self._apply_and_read(device.name, actions, number, endpoints)
            for number in (1, 2)
        )
        return readings, baseline, errors

    # -- el slice de comportamiento ------------------------------------
    def _build_slice(self, device: DevicePlan, created: list[DevicePlan], routed):
        """Dos PCs, uno por subred, por los mismos seams tipados del producto."""
        errors: list[str] = []
        pcs = tuple(
            DevicePlan(
                id=f"secqual/pc-{index}",
                name=f"{QUALIFICATION_PREFIX}{self._token}_PC{index}",
                model="PC-PT", category="", x=9400 + index * 80, y=9500,
            )
            for index in (0, 1)
        )
        for pc in pcs:
            try:
                result = self._physical.ensure_device(pc)
            except Exception as exc:  # noqa: BLE001
                created.append(pc)
                return None, [f"endpoint_creation_raised: {type(exc).__name__}: {exc}"]
            created.append(pc)
            if not result.applied:
                return None, [f"endpoint_not_created: {result.message}"]

        for index, pc in enumerate(pcs):
            link = LinkPlan(
                id=f"secqual/link-{index}",
                device_a=pc.name, port_a="FastEthernet0",
                device_b=device.name, port_b=routed[index],
                cable="straight",
            )
            try:
                result = self._physical.ensure_link(link)
            except Exception as exc:  # noqa: BLE001
                return None, [f"link_raised: {type(exc).__name__}: {exc}"]
            if not result.applied and result.disposition.value != "no_op":
                return None, [f"link_not_created: {result.message}"]

        actions = [
            ConfigureRoutedInterface(
                id="secqual/l3-inside", phase=ConfigurationPhase.L3_INTERFACES,
                device_id=device.id, device_name=device.name, site_id="secqual",
                interface=routed[0], ipv4=_INSIDE_GATEWAY, prefix=24,
                netmask=_MASK, segment_id="secqual-inside",
            ),
            ConfigureRoutedInterface(
                id="secqual/l3-outside", phase=ConfigurationPhase.L3_INTERFACES,
                device_id=device.id, device_name=device.name, site_id="secqual",
                interface=routed[1], ipv4=_OUTSIDE_GATEWAY, prefix=24,
                netmask=_MASK, segment_id="secqual-outside",
            ),
            SetEndpointStaticAddress(
                id="secqual/pc0", phase=ConfigurationPhase.ENDPOINT_ADDRESSING,
                device_id=pcs[0].id, device_name=pcs[0].name, site_id="secqual",
                interface="FastEthernet0", ipv4=_INSIDE_HOST, netmask=_MASK,
                gateway=_INSIDE_GATEWAY, segment_id="secqual-inside",
            ),
            SetEndpointStaticAddress(
                id="secqual/pc1", phase=ConfigurationPhase.ENDPOINT_ADDRESSING,
                device_id=pcs[1].id, device_name=pcs[1].name, site_id="secqual",
                interface="FastEthernet0", ipv4=_OUTSIDE_HOST, netmask=_MASK,
                gateway=_OUTSIDE_GATEWAY, segment_id="secqual-outside",
            ),
        ]
        try:
            self._configuration.inventory()
            mutations = self._configuration.apply_actions(actions)
        except Exception as exc:  # noqa: BLE001
            return None, [f"slice_configuration_raised: {type(exc).__name__}: {exc}"]
        refused = [item.action_id for item in mutations if not item.applied]
        if refused:
            return None, [f"slice_configuration_refused: {refused}"]
        return (pcs[0].name, pcs[1].name), errors

    def _flows(self, source: str, *, expected_reachable: bool):
        """Siempre los DOS flujos: el que la ACL toca y el que no.

        El control positivo hacia el propio gateway es lo que separa "la ACL
        denegó" de "el slice nunca funcionó". Se mide en los tres momentos.
        """
        return (
            self._flow("denied", source, _OUTSIDE_HOST, expected_reachable),
            self._flow("permitted", source, _INSIDE_GATEWAY, True),
        )

    def _flow(self, label: str, source: str, destination: str, expected: bool):
        try:
            result = self._ping.ping(source, destination)
        except Exception:  # noqa: BLE001 - una medida que falla no afirma nada
            return FlowMeasurement(
                label=label, source=source, destination=destination,
                expected_reachable=expected,
            )
        return FlowMeasurement(
            label=label, source=source, destination=destination,
            expected_reachable=expected,
            reachable=bool(result.reachable),
            fresh=bool(result.fresh_output_observed),
            attempts=int(getattr(result, "attempts", 0)),
            statistics=str(getattr(result, "statistics", "")),
        )

    def _actions(
        self, device: DevicePlan, inside: str, outside: str,
    ) -> list[SecurityAction]:
        common = {
            "device_id": device.id,
            "device_name": device.name,
            "model": device.model,
            "site_id": "secqual",
        }
        return [
            AddSecurityAclRule(
                id="secqual/acl-rule",
                phase=SecurityPhase.DEFINITIONS,
                required_capability=SecurityCapabilityDimension.ACL_CONFIG,
                acl_name=str(CONTROL_ACL_NUMBER),
                sequence=10,
                decision=SecurityDecision.DENY,
                protocol="ip",
                source_cidr=CONTROL_SOURCE_CIDR,
                destination_cidr=CONTROL_DESTINATION_CIDR,
                **common,
            ),
            # Sin este permit, un `deny` numerado arrastra el deny implícito y
            # tumbaría también el control positivo: el slice mediría "la red se
            # cayó" y lo leería como "la ACL filtra".
            AddSecurityAclRule(
                id="secqual/acl-permit-rest",
                phase=SecurityPhase.DEFINITIONS,
                required_capability=SecurityCapabilityDimension.ACL_CONFIG,
                acl_name=str(CONTROL_ACL_NUMBER),
                sequence=20,
                decision=SecurityDecision.ALLOW,
                protocol="ip",
                source_cidr="0.0.0.0/0",
                destination_cidr="0.0.0.0/0",
                **common,
            ),
            AttachSecurityAcl(
                id="secqual/acl-attach",
                phase=SecurityPhase.ATTACHMENTS,
                required_capability=SecurityCapabilityDimension.ACL_CONFIG,
                acl_name=str(CONTROL_ACL_NUMBER),
                interface=inside,
                direction="in",
                **common,
            ),
            ConfigureSecurityNat(
                id="secqual/nat",
                phase=SecurityPhase.ENFORCEMENT,
                required_capability=SecurityCapabilityDimension.NAT_PAT_CONFIG,
                policy_id="secqual-pat",
                mode=NatMode.PAT,
                inside_interfaces=[inside],
                outside_interface=outside,
                inside_networks=[CONTROL_SOURCE_CIDR],
                translation_acl_number=CONTROL_NAT_ACL_NUMBER,
                **common,
            ),
        ]

    def _apply_and_read(
        self,
        device_name: str,
        actions: list[SecurityAction],
        number: int,
        endpoints: tuple[str, str] | None = None,
    ) -> ReplayReading:
        applied: list[str] = []
        refused: list[str] = []
        message = ""
        try:
            for mutation in self._security.apply_actions(actions):
                (applied if mutation.applied else refused).append(mutation.action_id)
        except Exception as exc:  # noqa: BLE001
            message = f"{type(exc).__name__}: {exc}"

        acl = self._read(device_name, OperationalQueryId.SHOW_ACCESS_LISTS)
        nat = self._read(device_name, OperationalQueryId.SHOW_IP_NAT_STATISTICS)
        flows = (
            self._flows(endpoints[0], expected_reachable=False)
            if endpoints is not None else ()
        )
        return ReplayReading(
            pass_number=number,
            applied=tuple(applied),
            refused=tuple(refused),
            acl_executed=bool(acl and acl.executed),
            acl_fresh=bool(acl and acl.fresh_output_observed),
            acl_complete=bool(acl and acl.output_complete),
            acl_rows=tuple(parse_show_access_lists(acl.output)) if acl else (),
            acl_output=acl.output if acl else "",
            nat_executed=bool(nat and nat.executed),
            nat_fresh=bool(nat and nat.fresh_output_observed),
            nat_output=nat.output if nat else "",
            flows=flows,
            message=message,
        )

    def _read(self, device_name: str, query: OperationalQueryId):
        try:
            return self._query.execute(device_name, query)
        except Exception:  # noqa: BLE001 - una lectura que falla no afirma nada
            return None

    # -- limpieza ------------------------------------------------------
    def _undo(self, actions: list[SecurityAction]) -> list[str]:
        """La ruta de retirada TIPADA, que es donde vive `no access-list`."""
        if not actions:
            return []
        try:
            results = self._security.cleanup_actions(list(reversed(actions)))
        except Exception as exc:  # noqa: BLE001
            return [f"security_cleanup_raised: {type(exc).__name__}: {exc}"]
        return [
            f"Typed E8 cleanup did not apply for {item.action_id!r}: {item.message}"
            for item in results if not item.applied
        ]

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
            else:
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
            removed, errors, final,
            physical_workspace_restoration_matches(baseline, final),
        )
