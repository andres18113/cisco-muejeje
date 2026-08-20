"""Repetir `create cnf-files` bajo control, y mirar TODO lo que este backend expone.

`TD-VOICE-001` pide una sonda controlada y desechable que determine si la
ejecución repetida es replay-safe, produce efectos adicionales, o **permanece
inobservable**. Las tres son respuestas admisibles; lo que no lo es, es no haber
mirado.

Esta pasada mira por los tres caminos que este repositorio tiene, y por eso una
respuesta "inobservable" que salga de acá significa algo:

```text
consulta registrada   `show telephony-service`
consulta registrada   `show ephone`
camino de objeto      miembros del dispositivo y procesos que responden por nombre
```

Y compara las dos pasadas entre sí. Que ambas salgan idénticas establece que
nada cambió **en lo que se puede ver**; no establece que nada cambiara. Esa
distinción es el resultado, no una advertencia sobre el resultado.

## Lo que NO hace

* **No clasifica.** Mover la política de replay es un acto gobernado y vive en
  `domain/enterprise/mutation_replay.py`.
* **No convierte silencio en seguridad.** Dos lecturas vacías idénticas no son
  evidencia de idempotencia; son evidencia de que no hay observador.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from typing import Protocol

from ...domain.enterprise.models.configuration import (
    ConfigurationPhase,
    ConfigureRoutedInterface,
)
from ...domain.enterprise.models.physical_deployment import (
    PhysicalWorkspaceObservation,
    physical_workspace_restoration_matches,
)
from ...domain.enterprise.models.voice_plan import (
    ConfigureCallControlSource,
    CreateExtension,
    EnableCallControl,
    GeneratePhoneConfigurationFiles,
    VoiceAction,
    VoiceCapabilityDimension,
    VoicePhase,
)
from ...domain.models.plans import DevicePlan
from ...infrastructure.execution.access_port_probe import DeviceObserverDiscovery
from ...infrastructure.execution.ios_terminal import (
    IosCommandResult,
    OperationalQueryId,
)

#: Prefijo reservado, con la misma intención que los demás desechables.
QUALIFICATION_PREFIX = "__MCP_VOICEQUAL_"

CONTROL_SOURCE_ADDRESS = "198.18.170.1"
CONTROL_SIGNALING_PORT = 2000
CONTROL_EXTENSION = "1001"
_MASK = "255.255.255.0"

#: Las consultas registradas que podrían decir algo del bootstrap TFTP. Las dos
#: se ejecutan en cada pasada: una que responde "comando inválido" y otra que
#: responde vacío son evidencias distintas y no se colapsan.
_OBSERVATION_QUERIES = (
    OperationalQueryId.SHOW_TELEPHONY_SERVICE,
    OperationalQueryId.SHOW_EPHONE,
)


class VoicePhysicalRuntime(Protocol):
    def observe_workspace(self) -> PhysicalWorkspaceObservation: ...
    def ensure_device(self, device: DevicePlan): ...
    def observe_device(self, device: DevicePlan): ...
    def remove_device(self, device: DevicePlan): ...


class VoiceConfigurationRuntime(Protocol):
    def inventory(self) -> list: ...
    def apply_actions(self, actions) -> list: ...


class VoiceApplicationRuntime(Protocol):
    def inventory(self) -> list: ...
    def apply_actions(self, actions) -> list: ...


class VoiceQueryRuntime(Protocol):
    def execute(
        self, device_name: str, query_id: OperationalQueryId, *, interface: str = "",
    ) -> IosCommandResult: ...


class VoiceObserverProbe(Protocol):
    def __call__(self, device_name: str) -> DeviceObserverDiscovery: ...


@dataclass(frozen=True)
class QueryObservation:
    """Una consulta registrada y lo que respondió, sin interpretarla."""

    query: str
    executed: bool = False
    fresh: bool = False
    complete: bool = False
    output: str = ""
    failure_reason: str = ""

    @property
    def rejected_by_ios(self) -> bool:
        """IOS dijo que el comando no existe. No es lo mismo que responder vacío."""
        return "invalid input" in self.output.casefold()

    @property
    def answered_empty(self) -> bool:
        body = [
            line for line in self.output.splitlines()[1:]
            if line.strip() and not line.strip().endswith("#")
        ]
        return self.executed and not body and not self.rejected_by_ios


@dataclass(frozen=True)
class VoiceReplayPass:
    """Una ejecución de `create cnf-files` y todo lo observado después."""

    pass_number: int
    applied: bool = False
    message: str = ""
    queries: tuple[QueryObservation, ...] = ()
    discovery: DeviceObserverDiscovery | None = None

    @property
    def observable_state(self) -> tuple:
        """La huella de TODO lo observable, para comparar pasadas."""
        return (
            tuple((item.query, item.output) for item in self.queries),
            () if self.discovery is None else (
                self.discovery.device_class_name,
                self.discovery.enumerated_members,
                self.discovery.processes_present,
            ),
        )

    @property
    def any_observer_answered(self) -> bool:
        """Si algo, lo que sea, dijo algo sobre el estado de telefonía."""
        if any(
            item.executed and not item.rejected_by_ios and not item.answered_empty
            for item in self.queries
        ):
            return True
        return bool(self.discovery and self.discovery.processes_present and any(
            name.casefold() != "vlanmanager"
            for name in self.discovery.processes_present
        ))


@dataclass(frozen=True)
class VoiceReplayQualificationResult:
    model: str = ""
    device_name: str = ""
    setup_applied: bool = False
    passes: tuple[VoiceReplayPass, ...] = ()
    baseline_inventory: PhysicalWorkspaceObservation | None = None
    final_inventory: PhysicalWorkspaceObservation | None = None
    restored: bool | None = None
    removed: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()

    @property
    def dispatched_twice(self) -> bool:
        return len(self.passes) == 2 and all(item.applied for item in self.passes)

    @property
    def any_observer_answered(self) -> bool:
        return any(item.any_observer_answered for item in self.passes)

    @property
    def repeat_effect(self) -> str:
        """La clasificación que la evidencia sostiene, y ninguna más fuerte.

        `unobservable` no es un fallo de la pasada: es uno de los tres
        desenlaces que el criterio de `TD-VOICE-001` admite, y sólo puede
        afirmarse habiendo mirado por todos los caminos disponibles.
        """
        if not self.dispatched_twice:
            return "not_reproduced"
        if not self.any_observer_answered:
            return "unobservable"
        first, second = (item.observable_state for item in self.passes)
        return "no_observable_difference" if first == second else "observable_difference"


class VoiceReplayQualifier:
    """Reproduce `create cnf-files` repetido sobre su propio router desechable."""

    def __init__(
        self,
        physical: VoicePhysicalRuntime,
        configuration: VoiceConfigurationRuntime,
        voice: VoiceApplicationRuntime,
        query: VoiceQueryRuntime,
        probe: VoiceObserverProbe | None = None,
        *,
        name_token: str = "",
    ) -> None:
        self._physical = physical
        self._configuration = configuration
        self._voice = voice
        self._query = query
        self._probe = probe
        self._token = name_token or secrets.token_hex(3)

    def qualify(
        self, model: str, *, require_empty_workspace: bool = True,
    ) -> VoiceReplayQualificationResult:
        errors: list[str] = []
        try:
            baseline = self._physical.observe_workspace()
        except Exception as exc:  # noqa: BLE001 - la pasada reporta, no decide
            return VoiceReplayQualificationResult(
                model=model, errors=(f"Read-only workspace inventory failed: {exc}",),
            )
        if require_empty_workspace and baseline.semantic_devices:
            return VoiceReplayQualificationResult(
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
            id="voicequal/00",
            name=f"{QUALIFICATION_PREFIX}{self._token}_00",
            model=model, category="", x=9600, y=9600,
        )
        created: list[DevicePlan] = []
        passes: tuple[VoiceReplayPass, ...] = ()
        setup_applied = False
        try:
            setup_applied, passes, step_errors = self._measure(device, created)
            errors.extend(step_errors)
        except Exception as exc:  # noqa: BLE001 - la limpieza manda
            errors.append(f"qualification_raised: {type(exc).__name__}: {exc}")
        finally:
            removed, cleanup_errors, final, restored = self._cleanup(created, baseline)
            errors.extend(cleanup_errors)

        return VoiceReplayQualificationResult(
            model=model,
            device_name=device.name,
            setup_applied=setup_applied,
            passes=passes,
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
            created.append(device)
            return False, (), [f"device_creation_raised: {type(exc).__name__}: {exc}"]
        if not creation.applied:
            return False, (), [f"device_not_created: {creation.message}"]
        created.append(device)

        try:
            observation = self._physical.observe_device(device)
        except Exception as exc:  # noqa: BLE001
            return False, (), [f"observation_raised: {type(exc).__name__}: {exc}"]
        routed = [
            item for item in observation.interfaces
            if "Ethernet" in item and not item.lower().startswith("vlan")
        ]
        if not routed:
            return False, (), [
                "No routed Ethernet interface was observed; call control has no "
                "source address to bind.",
            ]

        try:
            self._configuration.inventory()
            address = self._configuration.apply_actions([ConfigureRoutedInterface(
                id="voicequal/l3", phase=ConfigurationPhase.L3_INTERFACES,
                device_id=device.id, device_name=device.name, site_id="voicequal",
                interface=routed[0], ipv4=CONTROL_SOURCE_ADDRESS, prefix=24,
                netmask=_MASK, segment_id="voicequal-voice",
            )])
        except Exception as exc:  # noqa: BLE001
            return False, (), [f"addressing_raised: {type(exc).__name__}: {exc}"]
        if not all(item.applied for item in address):
            return False, (), ["call_control_source_address_not_applied"]

        try:
            self._voice.inventory()
            setup = self._voice.apply_actions(self._setup_actions(device))
        except Exception as exc:  # noqa: BLE001
            return False, (), [f"voice_setup_raised: {type(exc).__name__}: {exc}"]
        setup_applied = all(item.applied for item in setup)
        if not setup_applied:
            errors.append(
                "voice_setup_incomplete: "
                + ", ".join(item.action_id for item in setup if not item.applied)
            )

        cnf = GeneratePhoneConfigurationFiles(
            id="voicequal/cnf", phase=VoicePhase.PHONE_BOOTSTRAP,
            call_control_id="voicequal-cc", host_device_id=device.id,
            host_device_name=device.name, host_model=device.model,
            site_id="voicequal",
            required_capability=VoiceCapabilityDimension.TFTP_PHONE_BOOTSTRAP,
        )
        passes = tuple(
            self._dispatch_and_observe(device.name, cnf, number) for number in (1, 2)
        )
        return setup_applied, passes, errors

    def _setup_actions(self, device: DevicePlan) -> list[VoiceAction]:
        common = dict(
            call_control_id="voicequal-cc", host_device_id=device.id,
            host_device_name=device.name, host_model=device.model,
            site_id="voicequal",
        )
        return [
            EnableCallControl(
                id="voicequal/cc", phase=VoicePhase.CALL_CONTROL,
                required_capability=VoiceCapabilityDimension.CALL_CONTROL_CONFIG,
                max_phones=4, max_extensions=4, **common,
            ),
            ConfigureCallControlSource(
                id="voicequal/src", phase=VoicePhase.CALL_CONTROL,
                required_capability=VoiceCapabilityDimension.CALL_CONTROL_CONFIG,
                source_address=CONTROL_SOURCE_ADDRESS,
                signaling_port=CONTROL_SIGNALING_PORT,
                source_configuration_action_id="voicequal/l3", **common,
            ),
            CreateExtension(
                id="voicequal/dn", phase=VoicePhase.EXTENSIONS,
                required_capability=VoiceCapabilityDimension.PHONE_EXTENSION_CONFIG,
                extension=CONTROL_EXTENSION, directory_index=1, **common,
            ),
        ]

    def _dispatch_and_observe(
        self, device_name: str, action: GeneratePhoneConfigurationFiles, number: int,
    ) -> VoiceReplayPass:
        applied = False
        message = ""
        try:
            mutations = self._voice.apply_actions([action])
            first = mutations[0] if mutations else None
            applied = bool(first and first.applied)
            message = (first.message if first else "no mutation returned") or ""
        except Exception as exc:  # noqa: BLE001
            message = f"{type(exc).__name__}: {exc}"

        discovery = None
        if self._probe is not None:
            try:
                discovery = self._probe(device_name)
            except Exception as exc:  # noqa: BLE001
                discovery = DeviceObserverDiscovery(
                    error=f"{type(exc).__name__}: {exc}",
                )
        return VoiceReplayPass(
            pass_number=number,
            applied=applied,
            message=message,
            queries=tuple(
                self._observe(device_name, query) for query in _OBSERVATION_QUERIES
            ),
            discovery=discovery,
        )

    def _observe(self, device_name: str, query: OperationalQueryId) -> QueryObservation:
        try:
            show = self._query.execute(device_name, query)
        except Exception as exc:  # noqa: BLE001
            return QueryObservation(
                query=query.value, failure_reason=f"{type(exc).__name__}: {exc}",
            )
        return QueryObservation(
            query=query.value,
            executed=bool(show.executed),
            fresh=bool(show.fresh_output_observed),
            complete=bool(show.output_complete),
            output=show.output or "",
            failure_reason=show.failure_reason or "",
        )

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
