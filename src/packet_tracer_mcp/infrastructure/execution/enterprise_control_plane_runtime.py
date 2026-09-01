"""Adapter Packet Tracer para mutaciones y evidencia cerradas de E9."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from ipaddress import IPv4Network
from time import monotonic, sleep
from typing import Protocol

from ...domain.enterprise.models.configuration_runtime import (
    ActionExecutionStatus,
    ConfigurationFailureCode,
    ConvergenceReport,
    FieldVerificationStatus,
    RuntimeActionMutation,
    RuntimeConfigurationTarget,
)
from ...domain.enterprise.models.control_plane import (
    ConfigureEigrpIpv4,
    ConfigureEtherChannel,
    ConfigureHsrp,
    ConfigureOspfv2,
    ConfigureRipv2,
    ConfigureSpanningTree,
    ControlPlaneAction,
    ControlPlaneVerificationExpectation,
    ControlPlaneVerificationKind,
    DynamicRoutingProtocol,
    EtherChannelProtocol,
    LinkFailureScenario,
    StpMode,
)
from ...domain.enterprise.models.control_plane_runtime import (
    ControlPlaneExecutionStage,
    FailureScenarioTransition,
    FailureTransitionPhase,
    RuntimeControlPlaneVerification,
    RuntimeFailureScenarioResult,
)
from ..generator.control_plane_renderer import (
    PacketTracerControlPlaneFaultRenderer,
    PacketTracerControlPlaneRenderer,
)
from .configuration_runtime import PacketTracerConfigurationRuntime
from .ios_terminal import (
    ControlledIosExecutor,
    DeviceIdentityProvenance,
    EigrpQueryClassification,
    IosCommandResult,
    OperationalQueryId,
    classify_show_ip_eigrp_neighbors,
    classify_show_ip_route_eigrp,
    parse_show_etherchannel_summary,
    parse_show_ip_ospf_neighbor,
    parse_show_ip_eigrp_neighbors,
    parse_show_ip_interface,
    parse_show_ip_protocols_rip,
    parse_show_ip_protocols_eigrp,
    parse_show_ip_route_eigrp,
    parse_show_ip_route_rip,
    parse_show_ip_route_ospf,
    parse_show_spanning_tree,
    qualified_pager_retry_eligible,
)
from .runtime_inventory import normalize_runtime_inventory
from .stable_convergence import StableConvergenceWaiter
from .typed_ping import SAFE_PING_TIMEOUT_S, TypedPingExecutor, TypedPingResult


class _PingExecutor(Protocol):
    def ping(self, source_device: str, destination: str) -> TypedPingResult: ...


class _IosExecutor(Protocol):
    def execute(
        self,
        device_name: str,
        query_id: OperationalQueryId,
        *,
        interface: str = "",
    ) -> IosCommandResult: ...


class FailureScenarioExecutor:
    """Ejecuta fault/restore tipados y exige evidencia ICMP estable."""

    def __init__(
        self,
        configuration: PacketTracerConfigurationRuntime,
        ping_executor: _PingExecutor,
        ios_executor: _IosExecutor | None = None,
        *,
        renderer: PacketTracerControlPlaneFaultRenderer | None = None,
        stable_samples: int = 2,
        max_probe_attempts: int = 6,
        timeout_seconds: float = 12.0,
        interval_seconds: float = 0.25,
        clock: Callable[[], float] = monotonic,
        sleeper: Callable[[float], None] = sleep,
    ) -> None:
        if (
            isinstance(stable_samples, bool)
            or not isinstance(stable_samples, int)
            or stable_samples < 2
        ):
            raise ValueError("stable_samples must be at least 2.")
        if (
            isinstance(max_probe_attempts, bool)
            or not isinstance(max_probe_attempts, int)
        ):
            raise ValueError("max_probe_attempts must be an integer.")
        if max_probe_attempts < stable_samples:
            raise ValueError("max_probe_attempts cannot be smaller than stable_samples.")
        if timeout_seconds < 0:
            raise ValueError("timeout_seconds must be non-negative.")
        if interval_seconds < 0:
            raise ValueError("interval_seconds must be non-negative.")
        self._configuration = configuration
        self._ping = ping_executor
        self._ios = ios_executor
        self._renderer = renderer or PacketTracerControlPlaneFaultRenderer()
        self._stable_samples = stable_samples
        self._max_attempts = max_probe_attempts
        self._timeout = timeout_seconds
        self._interval = interval_seconds
        self._clock = clock
        self._sleep = sleeper

    def execute(
        self,
        scenario: LinkFailureScenario,
        failure_expectation: ControlPlaneVerificationExpectation,
        recovery_expectation: ControlPlaneVerificationExpectation,
    ) -> RuntimeFailureScenarioResult:
        if failure_expectation.kind is not ControlPlaneVerificationKind.LINK_FAILURE_CONVERGENCE:
            raise ValueError("A failure scenario requires a link-failure expectation.")
        if recovery_expectation.kind is not ControlPlaneVerificationKind.RESTORE_RECOVERY:
            raise ValueError("A failure scenario requires a restore expectation.")
        expected_ids = set(scenario.verification_expectation_ids)
        if not {failure_expectation.id, recovery_expectation.id}.issubset(expected_ids):
            raise ValueError("Failure expectations are not bound to the typed scenario.")
        failure_reachable = self._expected_reachable(failure_expectation)
        recovery_reachable = self._expected_reachable(recovery_expectation)
        started = self._clock()
        transitions: list[FailureScenarioTransition] = []

        def transition(
            phase: FailureTransitionPhase,
            status: ActionExecutionStatus,
            *,
            evidence_method: str = "",
            message: str = "",
        ) -> None:
            elapsed_ms = max(0, int((self._clock() - started) * 1000))
            if transitions:
                elapsed_ms = max(elapsed_ms, transitions[-1].elapsed_ms)
            transitions.append(FailureScenarioTransition(
                sequence=len(transitions),
                phase=phase,
                elapsed_ms=elapsed_ms,
                status=status,
                evidence_method=evidence_method,
                message=message,
            ))

        try:
            rendered = self._renderer.render_scenario(scenario)
        except (TypeError, ValueError) as exc:
            return RuntimeFailureScenarioResult(
                scenario_id=scenario.id,
                injection=self._failed_mutation(
                    f"{scenario.id}:shutdown", str(exc),
                ),
                message=f"Typed fault rendering failed: {exc}",
            )

        before = self._stable_probe(
            scenario,
            expectation_id=failure_expectation.id,
            stage=ControlPlaneExecutionStage.BEHAVIOR,
            expected_reachable=True,
        )
        transition(
            FailureTransitionPhase.BASELINE_OBSERVED,
            before.status,
            evidence_method=before.evidence_method,
            message=before.message,
        )
        if before.status is not ActionExecutionStatus.VERIFIED:
            return RuntimeFailureScenarioResult(
                scenario_id=scenario.id,
                before=before,
                transitions=transitions,
                message="Stable reachable baseline was not established; fault not injected.",
            )

        injection: RuntimeActionMutation | None = None
        during: RuntimeControlPlaneVerification | None = None
        restore: RuntimeActionMutation | None = None
        after: RuntimeControlPlaneVerification | None = None
        restore_attempted = False
        try:
            # The cleanup payload already exists before the first shutdown can be sent.
            injection = self._configure(
                f"{scenario.id}:shutdown",
                rendered.device_name,
                rendered.ios_payload,
                "Typed link shutdown accepted by Packet Tracer.",
            )
            if injection.applied:
                fault_effect = self._interface_effect(
                    scenario,
                    expectation_id=failure_expectation.id,
                    stage=ControlPlaneExecutionStage.FAILOVER,
                    expected_down=True,
                )
                transition(
                    FailureTransitionPhase.FAULT_INJECTED,
                    fault_effect.status,
                    evidence_method=fault_effect.evidence_method,
                    message=fault_effect.message,
                )
                if fault_effect.status is ActionExecutionStatus.VERIFIED:
                    reachability = self._stable_probe(
                        scenario,
                        expectation_id=failure_expectation.id,
                        stage=ControlPlaneExecutionStage.FAILOVER,
                        expected_reachable=failure_reachable,
                    )
                    during = self._compose_failure_observation(
                        scenario, failure_expectation, fault_effect, reachability,
                    )
                else:
                    during = self._blocked_by_effect(
                        failure_expectation,
                        fault_effect,
                        field="link_down",
                    )
            else:
                transition(
                    FailureTransitionPhase.FAULT_INJECTED,
                    ActionExecutionStatus.FAILED,
                    evidence_method="typed_interface_shutdown_dispatch",
                    message=injection.message,
                )
                during = self._unobservable(
                    failure_expectation.id,
                    ControlPlaneExecutionStage.FAILOVER,
                    "Fault dispatch was not confirmed, so failover was not measured.",
                )
            transition(
                FailureTransitionPhase.FAILOVER_OBSERVED,
                during.status,
                evidence_method=during.evidence_method,
                message=during.message,
            )
        finally:
            restore_attempted = True
            restore = self._configure(
                f"{scenario.id}:restore",
                rendered.device_name,
                rendered.cleanup_payload,
                "Typed link restoration accepted by Packet Tracer.",
            )
            transition(
                FailureTransitionPhase.RESTORE_DISPATCHED,
                (
                    ActionExecutionStatus.APPLIED
                    if restore.applied else ActionExecutionStatus.FAILED
                ),
                evidence_method="typed_interface_restore_dispatch",
                message=restore.message,
            )
            if restore.applied:
                restore_effect = self._interface_effect(
                    scenario,
                    expectation_id=recovery_expectation.id,
                    stage=ControlPlaneExecutionStage.RESTORE,
                    expected_down=False,
                )
                if restore_effect.status is ActionExecutionStatus.VERIFIED:
                    reachability = self._stable_probe(
                        scenario,
                        expectation_id=recovery_expectation.id,
                        stage=ControlPlaneExecutionStage.RESTORE,
                        expected_reachable=recovery_reachable,
                    )
                    after = self._compose_recovery_observation(
                        recovery_expectation, restore_effect, reachability,
                    )
                else:
                    after = self._blocked_by_effect(
                        recovery_expectation,
                        restore_effect,
                        field="link_restored",
                    )
                transition(
                    FailureTransitionPhase.RECOVERY_OBSERVED,
                    after.status,
                    evidence_method=after.evidence_method,
                    message=after.message,
                )

        messages = [
            item for item in (
                injection.message if injection and not injection.applied else "",
                during.message if during and during.status is not ActionExecutionStatus.VERIFIED else "",
                restore.message if restore and not restore.applied else "",
                after.message if after and after.status is not ActionExecutionStatus.VERIFIED else "",
            ) if item
        ]
        return RuntimeFailureScenarioResult(
            scenario_id=scenario.id,
            before=before,
            injection=injection,
            during=during,
            restore_attempted=restore_attempted,
            restore=restore,
            after=after,
            transitions=transitions,
            message="; ".join(messages),
        )

    def _interface_effect(
        self,
        scenario: LinkFailureScenario,
        *,
        expectation_id: str,
        stage: ControlPlaneExecutionStage,
        expected_down: bool,
    ) -> RuntimeControlPlaneVerification:
        field = "link_down" if expected_down else "link_restored"
        if self._ios is None:
            return RuntimeControlPlaneVerification(
                expectation_id=expectation_id,
                stage=stage,
                status=ActionExecutionStatus.UNOBSERVABLE,
                evidence_method="interface_effect_observer_unavailable",
                fields={field: FieldVerificationStatus.UNOBSERVABLE},
                message=(
                    "No registered IOS observer was available to establish the "
                    "interface mutation effect."
                ),
            )
        try:
            show = self._ios.execute(
                scenario.target_device_name,
                OperationalQueryId.SHOW_IP_INTERFACE,
                interface=scenario.target_interface,
            )
        except Exception as exc:
            return RuntimeControlPlaneVerification(
                expectation_id=expectation_id,
                stage=stage,
                status=ActionExecutionStatus.UNOBSERVABLE,
                evidence_method="interface_effect_query_failed",
                fields={field: FieldVerificationStatus.UNOBSERVABLE},
                message=(
                    "Registered interface-effect query raised "
                    f"{type(exc).__name__}: {exc}"
                ),
            )
        if (
            not show.executed
            or not show.fresh_output_observed
            or show.truncated_by_pager
        ):
            return RuntimeControlPlaneVerification(
                expectation_id=expectation_id,
                stage=stage,
                status=ActionExecutionStatus.UNOBSERVABLE,
                evidence_method="interface_effect_readback_unobservable",
                fresh_evidence=show.fresh_output_observed,
                fields={field: FieldVerificationStatus.UNOBSERVABLE},
                message=(
                    show.failure_reason
                    or "Interface-effect read-back was absent, stale, or truncated."
                ),
            )
        observed = parse_show_ip_interface(show.output)
        if observed is None or self._interface_key(observed.interface) != self._interface_key(
            scenario.target_interface
        ):
            return RuntimeControlPlaneVerification(
                expectation_id=expectation_id,
                stage=stage,
                status=ActionExecutionStatus.UNOBSERVABLE,
                evidence_method="interface_effect_parse_unobservable",
                fresh_evidence=True,
                fields={field: FieldVerificationStatus.UNOBSERVABLE},
                message="Fresh interface output did not identify the exact target.",
            )
        administratively_down = "administratively down" in observed.status.casefold()
        matched = administratively_down is expected_down
        return RuntimeControlPlaneVerification(
            expectation_id=expectation_id,
            stage=stage,
            status=(
                ActionExecutionStatus.VERIFIED
                if matched else ActionExecutionStatus.FAILED
            ),
            evidence_method="fresh_show_ip_interface_admin_state",
            fresh_evidence=True,
            fields={
                field: (
                    FieldVerificationStatus.VERIFIED
                    if matched else FieldVerificationStatus.FAILED
                )
            },
            message=(
                f"Fresh exact-interface read-back matched {field}=true."
                if matched else
                f"Fresh exact-interface read-back contradicted {field}=true."
            ),
        )

    @staticmethod
    def _interface_key(value: str) -> str:
        normalized = value.casefold().replace("-", "")
        for prefix, canonical in (
            ("fastethernet", "fa"),
            ("gigabitethernet", "gi"),
            ("serial", "se"),
            ("fa", "fa"),
            ("gi", "gi"),
            ("se", "se"),
        ):
            if normalized.startswith(prefix):
                return canonical + normalized[len(prefix):]
        return normalized

    @staticmethod
    def _blocked_by_effect(expectation, effect, *, field):
        fields = {
            key: FieldVerificationStatus.UNOBSERVABLE
            for key in expectation.expected
        }
        fields[field] = effect.fields[field]
        return effect.model_copy(update={"fields": fields})

    @staticmethod
    def _composed_status(fields):
        statuses = set(fields.values())
        if FieldVerificationStatus.FAILED in statuses:
            return ActionExecutionStatus.FAILED
        if statuses == {FieldVerificationStatus.VERIFIED}:
            return ActionExecutionStatus.VERIFIED
        return ActionExecutionStatus.UNOBSERVABLE

    def _compose_failure_observation(
        self, scenario, expectation, effect, reachability,
    ):
        fields = {
            key: FieldVerificationStatus.UNOBSERVABLE
            for key in expectation.expected
        }
        fields.update(effect.fields)
        fields.update(reachability.fields)
        domain = scenario.failure_domain_result
        if domain is not None:
            expected_status = expectation.expected.get("failure_domain_status")
            if isinstance(expected_status, str):
                fields["failure_domain_status"] = (
                    FieldVerificationStatus.VERIFIED
                    if domain.status.value == expected_status
                    else FieldVerificationStatus.FAILED
                )
        # A successful ping does not identify which alternate link carried it.
        # Keep path attribution explicitly unobservable until a registered
        # route/interface observer can establish the declared survivor set.
        return RuntimeControlPlaneVerification(
            expectation_id=expectation.id,
            stage=ControlPlaneExecutionStage.FAILOVER,
            status=self._composed_status(fields),
            evidence_method="interface_effect_and_typed_ping",
            fresh_evidence=effect.fresh_evidence and reachability.fresh_evidence,
            fields=fields,
            message=(
                reachability.message
                + " Surviving-path attribution was not inferred from reachability."
            ),
            convergence=reachability.convergence,
        )

    def _compose_recovery_observation(self, expectation, effect, reachability):
        fields = {
            key: FieldVerificationStatus.UNOBSERVABLE
            for key in expectation.expected
        }
        fields.update(effect.fields)
        fields.update(reachability.fields)
        return RuntimeControlPlaneVerification(
            expectation_id=expectation.id,
            stage=ControlPlaneExecutionStage.RESTORE,
            status=self._composed_status(fields),
            evidence_method="interface_restore_effect_and_typed_ping",
            fresh_evidence=effect.fresh_evidence and reachability.fresh_evidence,
            fields=fields,
            message=reachability.message,
            convergence=reachability.convergence,
        )

    def _stable_probe(
        self,
        scenario: LinkFailureScenario,
        *,
        expectation_id: str,
        stage: ControlPlaneExecutionStage,
        expected_reachable: bool,
    ) -> RuntimeControlPlaneVerification:
        fresh_seen = False
        last_reason = ""

        def inspect() -> TypedPingResult:
            nonlocal fresh_seen, last_reason
            observed = self._ping.ping(
                scenario.probe_source_device_name,
                scenario.probe_destination_ipv4,
            )
            last_reason = observed.failure_reason
            fresh_seen = fresh_seen or observed.fresh_output_observed
            return observed

        convergence = StableConvergenceWaiter(
            inspect,
            lambda observed: bool(
                observed.fresh_output_observed
                and observed.reachable is expected_reachable
            ),
            lambda observed: (observed.reachable, observed.fresh_output_observed),
            timeout_seconds=self._timeout,
            interval_seconds=self._interval,
            stable_samples=self._stable_samples,
            max_attempts=self._max_attempts,
            clock=self._clock,
            sleeper=self._sleep,
        ).wait()
        if convergence.converged:
            return RuntimeControlPlaneVerification(
                expectation_id=expectation_id,
                stage=stage,
                status=ActionExecutionStatus.VERIFIED,
                evidence_method="typed_ping_stable_samples",
                fresh_evidence=True,
                fields={"reachable": FieldVerificationStatus.VERIFIED},
                message=(
                    f"Observed {self._stable_samples} consecutive fresh "
                    f"samples with reachable={expected_reachable}."
                ),
                convergence=ConvergenceReport(
                    attempts=convergence.attempts,
                    elapsed_ms=convergence.elapsed_ms,
                    final_status=ActionExecutionStatus.VERIFIED,
                    last_observable_state=f"reachable={expected_reachable}",
                ),
            )

        status = (
            ActionExecutionStatus.FAILED
            if fresh_seen else ActionExecutionStatus.UNOBSERVABLE
        )
        field_status = (
            FieldVerificationStatus.FAILED
            if fresh_seen else FieldVerificationStatus.UNOBSERVABLE
        )
        last_reason = last_reason or convergence.last_error or "state_mismatch"
        return RuntimeControlPlaneVerification(
            expectation_id=expectation_id,
            stage=stage,
            status=status,
            evidence_method="typed_ping_stable_samples",
            fresh_evidence=fresh_seen,
            fields={"reachable": field_status},
            message=(
                "Stable typed-ping evidence did not converge within the bounded "
                f"sample window ({last_reason})."
            ),
            convergence=ConvergenceReport(
                attempts=convergence.attempts,
                elapsed_ms=convergence.elapsed_ms,
                final_status=status,
                last_observable_state=last_reason,
            ),
        )

    def _configure(
        self,
        action_id: str,
        device_name: str,
        payload: str,
        success_message: str,
    ) -> RuntimeActionMutation:
        try:
            accepted = self._configuration.configure_ios(device_name, payload)
        except Exception as exc:
            return self._failed_mutation(
                action_id, f"Packet Tracer mutation raised {type(exc).__name__}: {exc}",
            )
        return RuntimeActionMutation(
            action_id=action_id,
            applied=accepted,
            failure_code=(
                ConfigurationFailureCode.NONE
                if accepted else ConfigurationFailureCode.APPLICATION_FAILED
            ),
            message=(
                success_message
                if accepted else "Packet Tracer rejected the typed link mutation."
            ),
            batch_id=f"{device_name}:failure-scenario",
        )

    @staticmethod
    def _expected_reachable(
        expectation: ControlPlaneVerificationExpectation,
    ) -> bool:
        value = expectation.expected.get("reachable")
        if not isinstance(value, bool):
            raise ValueError(
                f"Expectation {expectation.id!r} requires a typed reachable boolean."
            )
        return value

    @staticmethod
    def _failed_mutation(action_id: str, message: str) -> RuntimeActionMutation:
        return RuntimeActionMutation(
            action_id=action_id,
            applied=False,
            failure_code=ConfigurationFailureCode.APPLICATION_FAILED,
            message=message,
        )

    @staticmethod
    def _unobservable(
        expectation_id: str,
        stage: ControlPlaneExecutionStage,
        message: str,
    ) -> RuntimeControlPlaneVerification:
        return RuntimeControlPlaneVerification(
            expectation_id=expectation_id,
            stage=stage,
            status=ActionExecutionStatus.UNOBSERVABLE,
            evidence_method="typed_fault_dispatch_unconfirmed",
            fresh_evidence=False,
            fields={"reachable": FieldVerificationStatus.UNOBSERVABLE},
            message=message,
        )


class PacketTracerEnterpriseControlPlaneRuntime:
    """Aplica acciones E9 y verifica sólo comportamiento ICMP observable."""

    def __init__(
        self,
        query_inventory: Callable[[], list[dict] | dict],
        send: Callable[[str], bool],
        send_and_wait: Callable[[str, float], str | None],
        *,
        renderer: PacketTracerControlPlaneRenderer | None = None,
        fault_renderer: PacketTracerControlPlaneFaultRenderer | None = None,
        ping_executor: _PingExecutor | None = None,
        ios_executor: ControlledIosExecutor | None = None,
        # Medido: un ping totalmente perdido tarda 25.0 s desde un PC. Con
        # 12 s, un destino que de verdad es inalcanzable no llegaba a
        # clasificarse como tal y quedaba sin evidencia atribuible.
        behavior_timeout_seconds: float = SAFE_PING_TIMEOUT_S,
        endpoint_measurement_attempts: int = 3,
        convergence_interval_seconds: float = 0.25,
        stable_samples: int = 2,
        max_probe_attempts: int = 6,
        stp_convergence_timeout_seconds: float = 12.0,
        stp_convergence_interval_seconds: float = 2.0,
        stp_convergence_attempts: int = 7,
        # RIP anuncia cada 30 s. Medido en R2-B fase 4: tras esperar 35 s las
        # rutas ya estaban, con edades 00:00:26 y 00:00:00. El presupuesto
        # cubre un ciclo completo de actualizacion con margen, y se agota
        # releyendo, nunca reaplicando.
        route_convergence_timeout_seconds: float = 45.0,
        route_convergence_interval_seconds: float = 5.0,
        route_convergence_attempts: int = 10,
        # Medido en MEG-4 run 11 con el trace de simulacion de Packet Tracer:
        # la primera medida de reenvio salio `0/5` mientras el camino ya estaba
        # bien cableado y bien configurado, y ~30 s despues el MISMO ping
        # recibio Echo Reply. Entre medio no cambio ninguna configuracion: lo
        # que faltaba era convergencia -- ARP sobre la LAN de destino y un
        # switch de acceso recien creado cuyos puertos todavia no reenviaban.
        # Toda otra observacion de este runtime que depende de un plano que
        # converge ya tiene su ventana acotada de RELECTURA; esta, que depende
        # de la mas larga de todas, se media una sola vez.
        reachability_convergence_timeout_seconds: float = 90.0,
        reachability_convergence_interval_seconds: float = 5.0,
        reachability_convergence_attempts: int = 6,
        clock: Callable[[], float] = monotonic,
        sleeper: Callable[[float], None] = sleep,
    ) -> None:
        if stp_convergence_timeout_seconds < 0:
            raise ValueError("stp_convergence_timeout_seconds must be non-negative.")
        if stp_convergence_interval_seconds < 0:
            raise ValueError("stp_convergence_interval_seconds must be non-negative.")
        if (
            isinstance(stp_convergence_attempts, bool)
            or not isinstance(stp_convergence_attempts, int)
            or stp_convergence_attempts < 1
        ):
            raise ValueError("stp_convergence_attempts must be a positive integer.")
        if route_convergence_timeout_seconds < 0:
            raise ValueError("route_convergence_timeout_seconds must be non-negative.")
        if route_convergence_interval_seconds < 0:
            raise ValueError("route_convergence_interval_seconds must be non-negative.")
        if (
            isinstance(route_convergence_attempts, bool)
            or not isinstance(route_convergence_attempts, int)
            or route_convergence_attempts < 1
        ):
            raise ValueError("route_convergence_attempts must be a positive integer.")
        if reachability_convergence_timeout_seconds < 0:
            raise ValueError(
                "reachability_convergence_timeout_seconds must be non-negative.",
            )
        if reachability_convergence_interval_seconds < 0:
            raise ValueError(
                "reachability_convergence_interval_seconds must be non-negative.",
            )
        if (
            isinstance(reachability_convergence_attempts, bool)
            or not isinstance(reachability_convergence_attempts, int)
            or reachability_convergence_attempts < 1
        ):
            raise ValueError(
                "reachability_convergence_attempts must be a positive integer.",
            )
        self._query_inventory = query_inventory
        self._configuration = PacketTracerConfigurationRuntime(send)
        self._renderer = renderer or PacketTracerControlPlaneRenderer()
        self._ios = ios_executor or ControlledIosExecutor(send_and_wait)
        self._ping = ping_executor or TypedPingExecutor(
            send_and_wait,
            # La terminal de un endpoint PC no atribuye sus primeras
            # ejecuciones; sin presupuesto, una ruta que funciona se
            # pierde como UNOBSERVABLE en lugar de medirse.
            measurement_attempts=endpoint_measurement_attempts,
            timeout_seconds=behavior_timeout_seconds,
            interval_seconds=convergence_interval_seconds,
            clock=clock,
            sleeper=sleeper,
        )
        self._failure = FailureScenarioExecutor(
            self._configuration,
            self._ping,
            self._ios,
            renderer=fault_renderer,
            stable_samples=stable_samples,
            max_probe_attempts=max_probe_attempts,
            timeout_seconds=behavior_timeout_seconds,
            interval_seconds=convergence_interval_seconds,
            clock=clock,
            sleeper=sleeper,
        )
        self._route_timeout = route_convergence_timeout_seconds
        self._route_interval = route_convergence_interval_seconds
        self._route_attempts = route_convergence_attempts
        self._reach_timeout = reachability_convergence_timeout_seconds
        self._reach_interval = reachability_convergence_interval_seconds
        self._reach_attempts = reachability_convergence_attempts
        self._stp_timeout = stp_convergence_timeout_seconds
        self._stp_interval = stp_convergence_interval_seconds
        self._stp_attempts = stp_convergence_attempts
        self._clock = clock
        self._sleep = sleeper
        self._device_names_by_id: dict[str, str] = {}
        self._applied_actions: dict[str, ControlPlaneAction] = {}

    def inventory(self) -> list[RuntimeConfigurationTarget]:
        raw = self._query_inventory()
        items = raw.get("devices", []) if isinstance(raw, dict) else raw
        for item in items:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or item.get("device_name") or "")
            device_id = str(item.get("id") or item.get("device_id") or "")
            if device_id and name:
                self._device_names_by_id[device_id] = name
        return normalize_runtime_inventory(raw)

    def apply_actions(
        self, actions: Sequence[ControlPlaneAction],
    ) -> list[RuntimeActionMutation]:
        results: list[RuntimeActionMutation] = []
        for action in actions:
            try:
                rendered = self._renderer.render_action(action)
                accepted = self._configuration.configure_ios(
                    rendered.device_name, rendered.ios_payload,
                )
            except (TypeError, ValueError) as exc:
                accepted = False
                message = f"Typed E9 rendering failed: {exc}"
            except Exception as exc:
                accepted = False
                message = f"Packet Tracer mutation raised {type(exc).__name__}: {exc}"
            else:
                message = (
                    "Trusted typed control-plane mutation accepted by Packet Tracer."
                    if accepted else
                    "Packet Tracer rejected the typed control-plane mutation."
                )
            if accepted:
                self._applied_actions[action.id] = action
            results.append(RuntimeActionMutation(
                action_id=action.id,
                applied=accepted,
                failure_code=(
                    ConfigurationFailureCode.NONE
                    if accepted else ConfigurationFailureCode.APPLICATION_FAILED
                ),
                message=message,
                batch_id=f"{action.device_name}:{int(action.phase)}",
            ))
        return results

    def verify(
        self, expectations: Sequence[ControlPlaneVerificationExpectation],
    ) -> list[RuntimeControlPlaneVerification]:
        query_cache: dict[
            tuple[str, OperationalQueryId], IosCommandResult
        ] = {}
        return [self._verify_one(item, query_cache) for item in expectations]

    def execute_failure_scenario(
        self,
        scenario: LinkFailureScenario,
        failure_expectation: ControlPlaneVerificationExpectation,
        recovery_expectation: ControlPlaneVerificationExpectation,
    ) -> RuntimeFailureScenarioResult:
        return self._failure.execute(
            scenario, failure_expectation, recovery_expectation,
        )

    def _verify_one(
        self,
        expectation: ControlPlaneVerificationExpectation,
        query_cache: dict[tuple[str, OperationalQueryId], IosCommandResult],
    ) -> RuntimeControlPlaneVerification:
        action = self._applied_actions.get(expectation.action_id)
        if action is None:
            return self._unobservable(
                expectation,
                (
                    ControlPlaneExecutionStage.BEHAVIOR
                    if expectation.kind
                    is ControlPlaneVerificationKind.END_TO_END_REACHABILITY
                    else ControlPlaneExecutionStage.OBSERVED
                ),
                "The expectation is not bound to an applied typed action.",
            )
        direct = {
            ControlPlaneVerificationKind.STP_STATE: self._observe_stp,
            ControlPlaneVerificationKind.ETHERCHANNEL_STATE:
                self._observe_etherchannel,
            ControlPlaneVerificationKind.ROUTING_PROCESS:
                self._observe_routing_process,
            ControlPlaneVerificationKind.ROUTING_NEIGHBOR:
                self._observe_routing_neighbor,
            ControlPlaneVerificationKind.ROUTE_PRESENT:
                self._observe_route,
            ControlPlaneVerificationKind.HSRP_STATE:
                self._observe_hsrp_role,
        }.get(expectation.kind)
        if direct is not None:
            return direct(expectation, action, query_cache)
        if (
            expectation.kind
            is ControlPlaneVerificationKind.END_TO_END_REACHABILITY
            and isinstance(action, ConfigureSpanningTree)
            and {"loop_free", "forwarding_converged"}
            & set(expectation.expected)
        ):
            return self._observe_stp_behavior(expectation, action, query_cache)
        if expectation.kind is not ControlPlaneVerificationKind.END_TO_END_REACHABILITY:
            return self._unobservable(
                expectation,
                ControlPlaneExecutionStage.OBSERVED,
                "No live-fixture-backed registered query observes this state.",
            )
        destination = str(expectation.expected.get("destination_ipv4") or "")
        source = str(expectation.expected.get("source_device_name") or "")
        if not source:
            source = self._device_names_by_id.get(expectation.device_id, "")
        if not source and action.device_id == expectation.device_id:
            source = action.device_name
        if not source or not destination:
            return self._unobservable(
                expectation,
                ControlPlaneExecutionStage.BEHAVIOR,
                "Typed source device and destination IPv4 are not both available.",
            )
        expected_value = expectation.expected.get("reachable")
        if not isinstance(expected_value, bool):
            return self._unobservable(
                expectation,
                ControlPlaneExecutionStage.BEHAVIOR,
                "The reachability expectation is not a typed boolean.",
            )
        # Ventana de convergencia ACOTADA, la misma forma que `_observe_rip_route`
        # y por la misma razon: una sola medida confunde "todavia no converge"
        # con "no va a converger". Lo unico que se repite es la MEDIDA -- aqui
        # no se reaplica ni se redispacha ninguna configuracion.
        #
        # No es un reintento en busca de un resultado favorable. Corta en cuanto
        # la medida coincide con lo esperado, exactamente como el bucle de rutas
        # corta en cuanto la ruta aparece; si lo esperado fuera `reachable=False`
        # cortaria en el primer False y seguiria midiendo mientras diera True.
        # Y una ventana no fresca aborta de inmediato: esperar no la vuelve
        # atribuible, y agotar el presupuesto la disfrazaria de fallo.
        expected = expected_value
        deadline = self._clock() + self._reach_timeout
        attempts = 0
        while True:
            attempts += 1
            try:
                observed = self._ping.ping(source, destination)
            except Exception as exc:
                return self._unobservable(
                    expectation,
                    ControlPlaneExecutionStage.BEHAVIOR,
                    f"Typed ping raised {type(exc).__name__}: {exc}",
                )
            if not observed.fresh_output_observed:
                return self._unobservable(
                    expectation,
                    ControlPlaneExecutionStage.BEHAVIOR,
                    observed.failure_reason
                    or "No fresh typed-ping result was observed.",
                )
            matched = observed.reachable is expected
            if matched or attempts >= self._reach_attempts:
                break
            if self._clock() + self._reach_interval >= deadline:
                break
            self._sleep(self._reach_interval)
        # Contabilidad normal de campos, igual que toda otra observacion. Antes
        # este era el unico observador que construia `fields` a mano, y por eso
        # un `source_device_name` reclamado desaparecia del resultado en vez de
        # reportarse: una afirmacion se estrechaba sin que su techo de evidencia
        # se moviera, que es exactamente lo que `_unobservable_fields` existe
        # para impedir.
        fields = self._unobservable_fields(expectation)
        fields["reachable"] = self._field(matched)
        # Falla cerrado: sin atribucion unica de la sesion que midio, la
        # identidad de la fuente sigue inobservable, y con ella el agregado.
        self._certify_source_device(fields, expectation, observed)
        # La direccion la reporta el EJECUTOR, no el llamador: solo la rellena
        # en los retornos que ya confirmaron el eco exacto de `ping <ip>`, asi
        # que compararla contra lo reclamado ata la medida a esta direccion. Un
        # despacho corrompido la deja vacia y el campo se queda inobservable.
        if "destination_ipv4" in fields:
            dispatched = str(getattr(observed, "dispatched_destination", "") or "")
            if dispatched:
                fields["destination_ipv4"] = self._field(dispatched == destination)
        # El protocolo se ata a la ACCION APLICADA cuyo comportamiento se mide,
        # no al valor reclamado. `action` sale de `_applied_actions`, es decir
        # de lo que este producto aplico de verdad en esta corrida; una
        # expectativa que reclamase otro protocolo del que se aplico FALLA.
        if "protocol" in fields:
            applied_protocol = self._applied_protocol(action)
            if applied_protocol:
                fields["protocol"] = self._field(
                    applied_protocol == expectation.expected.get("protocol")
                )
        # El flujo del intent NO aparece aca, y no porque se oculte: viaja en
        # `expectation.source_traffic_flow_id`, que es procedencia igual que
        # `action_id`. Un campo de `expected` es una propiedad del device que
        # alguna consulta registrada podria leer; una etiqueta del compilador
        # nunca lo fue. Cualquier OTRO campo reclamado que no se pueda observar
        # sigue rindiendo UNOBSERVABLE via `_unobservable_fields`.
        status = self._aggregate_status(fields)
        return RuntimeControlPlaneVerification(
            expectation_id=expectation.id,
            stage=ControlPlaneExecutionStage.BEHAVIOR,
            status=status,
            evidence_method="typed_ping_current_command_window",
            fresh_evidence=True,
            fields=fields,
            message=(
                f"Fresh typed ping matched reachable={expected} after "
                f"{attempts} bounded measurement(s)."
                if matched else
                f"Fresh typed ping differed from reachable={expected} across "
                f"{attempts} bounded measurement(s); nothing was redispatched."
            ),
            convergence=ConvergenceReport(
                attempts=attempts,
                final_status=status,
                last_observable_state=f"reachable={observed.reachable}",
            ),
        )

    def _observe_stp(self, expectation, action, query_cache):
        if not isinstance(action, ConfigureSpanningTree):
            return self._unobservable(
                expectation, ControlPlaneExecutionStage.OBSERVED,
                "The STP expectation is not bound to a typed STP action.",
            )
        if action.mode is StpMode.MST:
            return self._unobservable(
                expectation,
                ControlPlaneExecutionStage.OBSERVED,
                "MST has no PT 9.0.1.0858 fresh-output fixture and typed parser.",
                evidence_method="mst_readback_unavailable",
            )
        deadline = self._clock() + self._stp_timeout
        key = (action.device_name, OperationalQueryId.SHOW_SPANNING_TREE)
        attempts = 0
        while True:
            attempts += 1
            show = self._fresh_show(
                action.device_name,
                OperationalQueryId.SHOW_SPANNING_TREE,
                expectation,
                query_cache,
            )
            if isinstance(show, RuntimeControlPlaneVerification):
                return show.model_copy(update={
                    "convergence": ConvergenceReport(
                        attempts=attempts,
                        final_status=show.status,
                        last_observable_state="unobservable",
                    ),
                })
            instances = parse_show_spanning_tree(show.output)
            if not instances:
                result = self._unobservable(
                    expectation, ControlPlaneExecutionStage.OBSERVED,
                    "Fresh spanning-tree output had no parser-backed instance.",
                )
                retryable = True
                state = "no_parser_backed_instance"
            else:
                fields = self._unobservable_fields(expectation)
                self._certify_source_device(fields, expectation, show)
                vlan_ids = self._typed_int_list(
                    expectation.expected.get("vlan_ids")
                )
                root_vlans = self._typed_int_list(
                    expectation.expected.get("root_primary_vlans")
                )
                secondary_vlans = self._typed_int_list(
                    expectation.expected.get("root_secondary_vlans")
                )
                priorities = self._typed_int_mapping(
                    expectation.expected.get("priorities")
                )
                by_vlan = {item.vlan_id: item for item in instances}
                selected = [
                    by_vlan[item] for item in vlan_ids or [] if item in by_vlan
                ]
                all_vlans_present = (
                    vlan_ids is not None and len(selected) == len(vlan_ids)
                )
                if vlan_ids is not None:
                    fields["vlan_ids"] = self._field(all_vlans_present)
                mode = expectation.expected.get("mode")
                expected_protocol = {
                    StpMode.PVST.value: "ieee",
                    StpMode.RAPID_PVST.value: "rstp",
                }.get(mode)
                if expected_protocol is not None and all_vlans_present:
                    fields["mode"] = self._field(
                        bool(selected)
                        and all(
                            item.protocol.casefold() == expected_protocol
                            for item in selected
                        )
                    )
                if root_vlans is not None:
                    fields["root_primary_vlans"] = self._field(all(
                        vlan in by_vlan and by_vlan[vlan].root_is_local
                        for vlan in root_vlans
                    ))
                if secondary_vlans is not None and all(
                    vlan in by_vlan
                    and by_vlan[vlan].bridge_base_priority is not None
                    for vlan in secondary_vlans
                ):
                    fields["root_secondary_vlans"] = self._field(all(
                        by_vlan[vlan].bridge_base_priority == 28672
                        for vlan in secondary_vlans
                    ))
                if priorities is not None and all(
                    vlan in by_vlan
                    and by_vlan[vlan].bridge_base_priority is not None
                    for vlan in priorities
                ):
                    fields["priorities"] = self._field(all(
                        by_vlan[vlan].bridge_base_priority == priority
                        for vlan, priority in priorities.items()
                    ))
                result = self._direct_observation(
                    expectation, fields, "fresh_show_spanning_tree",
                    "Fresh parser-backed STP instances were compared by VLAN.",
                )
                retryable = bool(
                    not all_vlans_present
                    or any(
                        port.state.casefold() in {"lis", "lrn"}
                        for item in selected
                        for port in item.interfaces
                    )
                )
                state = "parser_backed_instances"
            if (
                result.status is ActionExecutionStatus.VERIFIED
                or not retryable
                or attempts >= self._stp_attempts
                or self._clock() + self._stp_interval >= deadline
            ):
                return result.model_copy(update={
                    "convergence": ConvergenceReport(
                        attempts=attempts,
                        final_status=result.status,
                        last_observable_state=state,
                    ),
                })
            self._sleep(self._stp_interval)
            # Re-observe only; never re-render or redispatch the typed action.
            query_cache.pop(key, None)

    def _observe_stp_behavior(self, expectation, action, query_cache):
        if action.mode is StpMode.MST:
            return self._unobservable(
                expectation,
                ControlPlaneExecutionStage.BEHAVIOR,
                "MST behavior has no PT 9.0.1.0858 parser-backed qualification.",
                evidence_method="mst_behavior_readback_unavailable",
            )
        deadline = self._clock() + self._stp_timeout
        key = (action.device_name, OperationalQueryId.SHOW_SPANNING_TREE)
        attempts = 0
        while True:
            attempts += 1
            show = self._fresh_show(
                action.device_name,
                OperationalQueryId.SHOW_SPANNING_TREE,
                expectation,
                query_cache,
            )
            if isinstance(show, RuntimeControlPlaneVerification):
                return show.model_copy(update={
                    "convergence": ConvergenceReport(
                        attempts=attempts,
                        final_status=show.status,
                        last_observable_state="unobservable",
                    ),
                })
            instances = parse_show_spanning_tree(show.output)
            if not instances:
                result = self._unobservable(
                    expectation,
                    ControlPlaneExecutionStage.BEHAVIOR,
                    "Fresh spanning-tree output had no parser-backed instance.",
                    evidence_method="stp_readback_no_parser_backed_instance",
                )
                transitional = True
                stable = False
                state = "no_parser_backed_instance"
            else:
                by_vlan = {item.vlan_id: item for item in instances}
                selected = [
                    by_vlan[vlan]
                    for vlan in action.vlan_ids
                    if vlan in by_vlan
                ]
                all_vlans_present = len(selected) == len(action.vlan_ids)
                ports = [port for item in selected for port in item.interfaces]
                stable = bool(selected) and bool(ports) and all(
                    port.state.casefold() in {"fwd", "blk"}
                    for port in ports
                )
                role_state_consistent = stable and all(
                    (
                        port.role.casefold() in {"root", "desg"}
                        and port.state.casefold() == "fwd"
                    )
                    or (
                        port.role.casefold() in {"altn", "back"}
                        and port.state.casefold() == "blk"
                    )
                    for port in ports
                )
                fields = self._unobservable_fields(expectation)
                self._certify_source_device(fields, expectation, show)
                loop_free = expectation.expected.get("loop_free")
                if isinstance(loop_free, bool):
                    fields["loop_free"] = self._field(
                        all_vlans_present and role_state_consistent is loop_free
                    )
                forwarding = expectation.expected.get("forwarding_converged")
                if isinstance(forwarding, bool):
                    fields["forwarding_converged"] = self._field(
                        all_vlans_present and stable is forwarding
                    )
                result = self._direct_observation(
                    expectation,
                    fields,
                    "fresh_show_spanning_tree_stable_roles",
                    (
                        "Fresh parser-backed STP roles and states were checked "
                        "for stable forwarding/blocking consistency."
                    ),
                    stage=ControlPlaneExecutionStage.BEHAVIOR,
                )
                transitional = bool(
                    not all_vlans_present
                    or any(
                        port.state.casefold() in {"lis", "lrn"}
                        for port in ports
                    )
                )
                state = (
                    "stable_roles"
                    if stable else "transitional_or_absent_roles"
                )
            if (
                result.status is ActionExecutionStatus.VERIFIED
                or not transitional
                or attempts >= self._stp_attempts
                or self._clock() + self._stp_interval >= deadline
            ):
                return result.model_copy(update={
                    "convergence": ConvergenceReport(
                        attempts=attempts,
                        final_status=result.status,
                        last_observable_state=state,
                    ),
                })
            self._sleep(self._stp_interval)
            query_cache.pop(key, None)

    def _observe_etherchannel(self, expectation, action, query_cache):
        if not isinstance(action, ConfigureEtherChannel):
            return self._unobservable(
                expectation, ControlPlaneExecutionStage.OBSERVED,
                "The EtherChannel expectation is not bound to a typed channel action.",
            )
        if action.protocol is not EtherChannelProtocol.LACP:
            return self._unobservable(
                expectation,
                ControlPlaneExecutionStage.OBSERVED,
                f"{action.protocol.value} bundle read-back has no PT 9.0.1.0858 "
                "fixture-backed parser.",
                evidence_method="etherchannel_protocol_readback_unavailable",
            )
        show = self._fresh_show(
            action.device_name, OperationalQueryId.SHOW_ETHERCHANNEL_SUMMARY,
            expectation, query_cache,
        )
        if isinstance(show, RuntimeControlPlaneVerification):
            return show
        groups = parse_show_etherchannel_summary(show.output)
        if not groups:
            return self._unobservable(
                expectation, ControlPlaneExecutionStage.OBSERVED,
                "Fresh EtherChannel output had no parser-backed group row.",
            )
        fields = self._unobservable_fields(expectation)
        self._certify_source_device(fields, expectation, show)
        expected_port = expectation.expected.get("port_channel_interface")
        expected_port_key = (
            self._interface_key(expected_port)
            if isinstance(expected_port, str) else ""
        )
        group = next(
            (item for item in groups
             if self._interface_key(item.port_channel) == expected_port_key),
            None,
        )
        if group is None:
            if expected_port_key:
                fields["port_channel_interface"] = FieldVerificationStatus.FAILED
            return self._direct_observation(
                expectation, fields, "fresh_show_etherchannel_summary",
                "No parser-backed EtherChannel row matched the expected group.",
            )
        fields["port_channel_interface"] = self._field(
            "S" in group.port_channel_flags.upper()
            and "U" in group.port_channel_flags.upper()
        )
        protocol = expectation.expected.get("protocol")
        if isinstance(protocol, str):
            fields["protocol"] = self._field(
                group.protocol.casefold() == protocol.casefold()
            )
        members = expectation.expected.get("member_interfaces")
        if (
            isinstance(members, list)
            and all(isinstance(item, str) and item for item in members)
        ):
            expected_members = {self._interface_key(item) for item in members}
            observed_members = {
                self._interface_key(item.interface) for item in group.members
            }
            fields["member_interfaces"] = self._field(
                observed_members == expected_members
                and all(item.flag.upper() == "P" for item in group.members)
            )
        return self._direct_observation(
            expectation, fields, "fresh_show_etherchannel_summary",
            "Fresh parser-backed EtherChannel group was compared exactly.",
        )

    def _observe_routing_process(self, expectation, action, query_cache):
        if isinstance(action, ConfigureRipv2):
            return self._observe_rip_process(expectation, action, query_cache)
        if isinstance(action, ConfigureEigrpIpv4):
            return self._observe_eigrp_process(expectation, action, query_cache)
        return self._observe_ospf_process(expectation, action, query_cache)

    def _observe_routing_neighbor(self, expectation, action, query_cache):
        if isinstance(action, ConfigureRipv2):
            return self._unobservable(
                expectation,
                ControlPlaneExecutionStage.OBSERVED,
                "RIP adjacency is behaviour, not configuration read-back.",
                evidence_method="rip_neighbor_readback_unavailable",
            )
        if isinstance(action, ConfigureEigrpIpv4):
            return self._observe_eigrp_neighbor(expectation, action, query_cache)
        return self._observe_ospf_neighbor(expectation, action, query_cache)

    def _observe_route(self, expectation, action, query_cache):
        if isinstance(action, ConfigureRipv2):
            return self._observe_rip_route(expectation, action, query_cache)
        if isinstance(action, ConfigureEigrpIpv4):
            return self._observe_eigrp_route(expectation, action, query_cache)
        return self._observe_ospf_route(expectation, action, query_cache)

    def _observe_eigrp_process(self, expectation, action, query_cache):
        if not self._is_eigrp_expectation(expectation, action):
            return self._unobservable(
                expectation, ControlPlaneExecutionStage.OBSERVED,
                "No registered live-fixture-backed query observes this EIGRP process.",
            )
        show = self._fresh_show(
            action.device_name, OperationalQueryId.SHOW_IP_PROTOCOLS,
            expectation, query_cache, permit_truncated=True,
        )
        if isinstance(show, RuntimeControlPlaneVerification):
            return show
        process = parse_show_ip_protocols_eigrp(show.output)
        if process is None:
            return self._unobservable(
                expectation, ControlPlaneExecutionStage.OBSERVED,
                "Fresh SHOW output had no parser-backed EIGRP process block.",
                evidence_method="fresh_show_ip_protocols_eigrp",
            )
        fields = self._unobservable_fields(expectation)
        self._certify_source_device(fields, expectation, show)
        fields["protocol"] = self._field(process.as_number == action.as_number)
        router_id = expectation.expected.get("router_id")
        if isinstance(router_id, str):
            fields["router_id"] = self._field(process.router_id == router_id)
        return self._direct_observation(
            expectation, fields, "fresh_show_ip_protocols_eigrp",
            "Fresh EIGRP process AS and local router ID were compared exactly.",
        )

    def _observe_eigrp_neighbor(self, expectation, action, query_cache):
        if not self._is_eigrp_expectation(expectation, action):
            return self._unobservable(
                expectation, ControlPlaneExecutionStage.OBSERVED,
                "No registered live-fixture-backed query observes this EIGRP neighbor.",
            )
        show = self._fresh_show(
            action.device_name, OperationalQueryId.SHOW_IP_EIGRP_NEIGHBORS,
            expectation, query_cache,
        )
        if isinstance(show, RuntimeControlPlaneVerification):
            return show
        if not show.output_complete:
            return self._unobservable(
                expectation, ControlPlaneExecutionStage.OBSERVED,
                "The fresh EIGRP neighbor read-back did not close on a prompt.",
                evidence_method="eigrp_neighbor_readback_incomplete",
            )
        classification = classify_show_ip_eigrp_neighbors(
            show.output, expected_as_number=action.as_number,
        )
        if classification not in {
            EigrpQueryClassification.SUPPORTED_WITH_ROWS,
            EigrpQueryClassification.SUPPORTED_EMPTY,
        }:
            return self._unobservable(
                expectation, ControlPlaneExecutionStage.OBSERVED,
                f"Fresh EIGRP neighbor output classified as {classification.value}.",
                evidence_method="fresh_show_ip_eigrp_neighbors",
            )
        rows = parse_show_ip_eigrp_neighbors(show.output)
        peer_ip = expectation.expected.get("peer_ipv4")
        peer_row = next(
            (
                item for item in rows
                if isinstance(peer_ip, str) and item.address == peer_ip
            ),
            None,
        )
        fields = self._unobservable_fields(expectation)
        self._certify_source_device(fields, expectation, show)
        fields["protocol"] = FieldVerificationStatus.VERIFIED
        if isinstance(peer_ip, str):
            fields["peer_ipv4"] = self._field(peer_row is not None)
        adjacent = expectation.expected.get("adjacent")
        if isinstance(adjacent, bool):
            fields["adjacent"] = self._field((peer_row is not None) is adjacent)

        peer_router_id = expectation.expected.get("peer_router_id")
        peer_action = self._applied_eigrp_action_for_device(
            expectation.peer_device_id,
        )
        if isinstance(peer_router_id, str) and peer_action is not None:
            peer_show = self._fresh_show(
                peer_action.device_name, OperationalQueryId.SHOW_IP_PROTOCOLS,
                expectation, query_cache, permit_truncated=True,
            )
            if not isinstance(peer_show, RuntimeControlPlaneVerification):
                peer_process = parse_show_ip_protocols_eigrp(peer_show.output)
                if peer_process is not None:
                    fields["peer_router_id"] = self._field(
                        peer_process.as_number == action.as_number
                        and peer_process.router_id == peer_router_id
                    )
        return self._direct_observation(
            expectation, fields, "fresh_show_ip_eigrp_neighbors",
            "Fresh EIGRP neighbor rows were matched by process AS and peer IPv4; "
            "the peer router ID was independently read from the applied peer.",
            allow_partial=True,
        )

    def _observe_eigrp_route(self, expectation, action, query_cache):
        if not self._is_eigrp_expectation(expectation, action):
            return self._unobservable(
                expectation, ControlPlaneExecutionStage.OBSERVED,
                "No registered live-fixture-backed query observes this EIGRP route.",
            )
        network = expectation.expected.get("network")
        prefix_length = expectation.expected.get("prefix_length")
        if not isinstance(network, str) or type(prefix_length) is not int:
            return self._unobservable(
                expectation, ControlPlaneExecutionStage.OBSERVED,
                "The EIGRP route expectation lacks a typed prefix and length.",
                evidence_method="eigrp_route_expectation_untyped",
            )
        key = (action.device_name, OperationalQueryId.SHOW_IP_ROUTE_EIGRP)
        deadline = self._clock() + self._route_timeout
        attempts = 0
        route = None
        while True:
            attempts += 1
            show = self._fresh_show(
                action.device_name, OperationalQueryId.SHOW_IP_ROUTE_EIGRP,
                expectation, query_cache,
            )
            if isinstance(show, RuntimeControlPlaneVerification):
                return show
            if not show.output_complete:
                return self._unobservable(
                    expectation, ControlPlaneExecutionStage.OBSERVED,
                    "The fresh EIGRP route read-back did not close on a prompt.",
                    evidence_method="eigrp_route_readback_incomplete",
                )
            classification = classify_show_ip_route_eigrp(show.output)
            if classification not in {
                EigrpQueryClassification.SUPPORTED_WITH_ROWS,
                EigrpQueryClassification.SUPPORTED_EMPTY,
            }:
                return self._unobservable(
                    expectation, ControlPlaneExecutionStage.OBSERVED,
                    f"Fresh EIGRP route output classified as {classification.value}.",
                    evidence_method="fresh_show_ip_route_eigrp",
                )
            route = next(
                (
                    item for item in parse_show_ip_route_eigrp(show.output)
                    if item.prefix == network
                    and item.prefix_length == prefix_length
                ),
                None,
            )
            if route is not None or attempts >= self._route_attempts:
                break
            if self._clock() + self._route_interval >= deadline:
                break
            self._sleep(self._route_interval)
            query_cache.pop(key, None)

        fields = self._unobservable_fields(expectation)
        self._certify_source_device(fields, expectation, show)
        for field in ("protocol", "network", "prefix_length"):
            fields[field] = self._field(route is not None)
        wildcard = expectation.expected.get("wildcard")
        if isinstance(wildcard, str) and route is not None:
            observed_wildcard = str(
                IPv4Network(f"0.0.0.0/{route.prefix_length}").hostmask
            )
            fields["wildcard"] = self._field(observed_wildcard == wildcard)
        observation = self._direct_observation(
            expectation, fields, "fresh_show_ip_route_eigrp",
            f"Fresh EIGRP route rows matched the exact learned prefix after "
            f"{attempts} read(s)."
            if route is not None else
            f"The expected EIGRP route did not appear within {attempts} bounded "
            f"read(s); no configuration was redispatched.",
            allow_partial=True,
        )
        return observation.model_copy(update={
            "convergence": ConvergenceReport(
                attempts=attempts,
                final_status=observation.status,
                last_observable_state=(
                    f"{network}/{prefix_length}" if route is not None
                    else "route_absent"
                ),
            ),
        })

    def _observe_rip_route(self, expectation, action, query_cache):
        """Ruta APRENDIDA por RIP, distinta de la configuración leída.

        Compara sólo prefijo, longitud y que la fuente sea RIP. Ni siguiente
        salto ni interfaz entran: la evidencia viva llegó por una serial, y
        exigir ese nombre ataría la aceptación a una topología concreta.
        """
        if expectation.expected.get("protocol") != "ripv2":
            return self._unobservable(
                expectation, ControlPlaneExecutionStage.OBSERVED,
                "No registered live-fixture-backed query observes this route protocol.",
            )
        network = expectation.expected.get("network")
        prefix_length = expectation.expected.get("prefix_length")
        if not isinstance(network, str) or type(prefix_length) is not int:
            # Sin prefijo y máscara tipados no hay nada que comparar. Antes se
            # caía a emparejar sólo por dirección de red, y entonces una /27
            # satisfacía una expectativa de /24.
            return self._unobservable(
                expectation, ControlPlaneExecutionStage.OBSERVED,
                "The route expectation does not carry a typed prefix and length.",
                evidence_method="rip_route_expectation_untyped",
            )
        # Ventana de convergencia ACOTADA. RIP anuncia cada 30 s, asi que una
        # sola lectura confunde "todavia no llego" con "no va a llegar". Lo
        # unico que se reintenta es la LECTURA: aqui no se reaplica nada.
        key = (action.device_name, OperationalQueryId.SHOW_IP_ROUTE_RIP)
        deadline = self._clock() + self._route_timeout
        attempts = 0
        while True:
            attempts += 1
            show = self._fresh_show(
                action.device_name, OperationalQueryId.SHOW_IP_ROUTE_RIP,
                expectation, query_cache, permit_truncated=True,
            )
            if isinstance(show, RuntimeControlPlaneVerification):
                # Evidencia rancia o consulta no ejecutada: esperar no lo
                # arregla y agotar el presupuesto lo disfrazaria de fallo.
                return show
            if show.truncated_by_pager:
                # Una tabla cortada puede esconder justo la ruta buscada: leerla
                # como ausencia seria un FAILED falso.
                return self._unobservable(
                    expectation, ControlPlaneExecutionStage.OBSERVED,
                    "The RIP route read-back was truncated by the IOS pager.",
                    evidence_method="rip_route_readback_truncated",
                )
            match = next(
                (
                    item for item in parse_show_ip_route_rip(show.output)
                    if item.prefix == network
                    and item.prefix_length == prefix_length
                ),
                None,
            )
            if match is not None or attempts >= self._route_attempts:
                break
            if self._clock() + self._route_interval >= deadline:
                break
            self._sleep(self._route_interval)
            # La cache existe para no repetir la consulta entre expectativas
            # del mismo device; para converger hace falta una lectura nueva.
            query_cache.pop(key, None)

        fields = self._unobservable_fields(expectation)
        self._certify_source_device(fields, expectation, show)
        for field in ("protocol", "network", "prefix_length"):
            fields[field] = self._field(match is not None)
        observation = self._direct_observation(
            expectation, fields, "fresh_show_ip_route_rip",
            f"Fresh RIP route rows matched the expected prefix after "
            f"{attempts} read(s)."
            if match is not None else
            f"The expected RIP route did not appear within {attempts} bounded "
            f"read(s); no configuration was redispatched.",
        )
        return observation.model_copy(update={
            "convergence": ConvergenceReport(
                attempts=attempts,
                final_status=observation.status,
                last_observable_state=(
                    f"{network}/{prefix_length}"
                    if match is not None else "route_absent"
                ),
            ),
        })

    def _observe_rip_process(self, expectation, action, query_cache):
        if expectation.expected.get("protocol") != "ripv2":
            return self._unobservable(
                expectation, ControlPlaneExecutionStage.OBSERVED,
                "No registered live-fixture-backed query observes this routing process.",
            )
        query_key = (
            action.device_name,
            OperationalQueryId.SHOW_IP_PROTOCOLS,
        )
        show = self._fresh_show(
            action.device_name, OperationalQueryId.SHOW_IP_PROTOCOLS,
            expectation, query_cache, permit_truncated=True,
        )
        if isinstance(show, RuntimeControlPlaneVerification):
            return show
        first_show = show
        attempts = 1
        if qualified_pager_retry_eligible(
            show,
            expected_device_name=action.device_name,
        ):
            query_cache.pop(query_key, None)
            show = self._fresh_show(
                action.device_name,
                OperationalQueryId.SHOW_IP_PROTOCOLS,
                expectation,
                query_cache,
                permit_truncated=True,
            )
            attempts = 2

        def retain_pager_retry(
            result: RuntimeControlPlaneVerification,
            last_observable_state: str,
        ) -> RuntimeControlPlaneVerification:
            if attempts == 1:
                return result
            cached_final = query_cache.get(query_key)
            final_show = (
                show
                if isinstance(show, IosCommandResult)
                else cached_final
                if isinstance(cached_final, IosCommandResult)
                else None
            )
            return result.model_copy(update={
                "convergence": ConvergenceReport(
                    attempts=attempts,
                    final_status=result.status,
                    last_observable_state=last_observable_state,
                    details={
                        "first_output_complete": first_show.output_complete,
                        "first_truncated_by_pager": (
                            first_show.truncated_by_pager
                        ),
                        "first_pager_continuation": (
                            first_show.pager_continuation
                        ),
                        "first_pager_pages_captured": (
                            first_show.pager_pages_captured
                        ),
                        "first_device_identity_provenance": (
                            first_show.device_identity_provenance
                        ),
                        "final_output_complete": (
                            final_show.output_complete
                            if final_show is not None else None
                        ),
                        "final_truncated_by_pager": (
                            final_show.truncated_by_pager
                            if final_show is not None else None
                        ),
                        "final_pager_continuation": (
                            final_show.pager_continuation
                            if final_show is not None else None
                        ),
                    },
                ),
            })

        if isinstance(show, RuntimeControlPlaneVerification):
            return retain_pager_retry(show, "retry_unobservable")
        if show.truncated_by_pager:
            # Un `show ip protocols` cortado por el pager puede esconder
            # sentencias de red o interfaces pasivas: leerlo como ausencia
            # produciria un FAILED falso.
            return retain_pager_retry(self._unobservable(
                expectation, ControlPlaneExecutionStage.OBSERVED,
                "The RIP read-back was truncated by the IOS pager.",
                evidence_method="rip_readback_truncated",
            ), "pager_continuation_failed")
        observed = parse_show_ip_protocols_rip(show.output)
        fields = self._unobservable_fields(expectation)
        self._certify_source_device(fields, expectation, show)
        if observed is None:
            # La procedencia sobrevive: que el device no corra RIP no borra la
            # evidencia de QUE device contesto.
            return retain_pager_retry(self._direct_observation(
                expectation,
                {
                    field: (
                        status if field == "source_device_name"
                        else FieldVerificationStatus.FAILED
                    )
                    for field, status in fields.items()
                },
                "fresh_show_ip_protocols",
                "Fresh output reports no RIP routing process on the device.",
            ), "rip_process_absent")
        fields["protocol"] = FieldVerificationStatus.VERIFIED
        for field, value in (
            ("version_send", observed.version_send),
            ("version_recv", observed.version_recv),
        ):
            expected = expectation.expected.get(field)
            if type(expected) is int:
                fields[field] = self._field(value == expected)
        auto_summary = expectation.expected.get("auto_summary")
        if isinstance(auto_summary, bool) and observed.auto_summary is not None:
            fields["auto_summary"] = self._field(
                observed.auto_summary is auto_summary
            )
        networks = expectation.expected.get("networks")
        if self._typed_str_list(networks) is not None:
            fields["networks"] = self._field(
                set(observed.networks) == set(networks)
            )
        passive = expectation.expected.get("passive_interfaces")
        if self._typed_str_list(passive) is not None:
            fields["passive_interfaces"] = self._field(
                {self._interface_key(item) for item in observed.passive_interfaces}
                == {self._interface_key(item) for item in passive}
            )
        return retain_pager_retry(self._direct_observation(
            expectation, fields, "fresh_show_ip_protocols",
            "Fresh RIP state was compared semantically against the typed intent.",
        ), "rip_process_observed")

    def _observe_hsrp_role(self, expectation, action, query_cache):
        del query_cache
        if not isinstance(action, ConfigureHsrp):
            return self._unobservable(
                expectation,
                ControlPlaneExecutionStage.OBSERVED,
                "The HSRP expectation is not bound to a typed HSRP action.",
            )
        return self._unobservable(
            expectation,
            ControlPlaneExecutionStage.OBSERVED,
            "Packet Tracer exposes no fixture-backed stationary HSRP role read-back.",
            evidence_method="hsrp_role_readback_unavailable",
        )

    def _observe_ospf_process(self, expectation, action, query_cache):
        if not self._is_ospf_expectation(expectation, action):
            return self._unobservable(
                expectation, ControlPlaneExecutionStage.OBSERVED,
                "No registered live-fixture-backed query observes this routing process.",
            )
        show = self._fresh_show(
            action.device_name, OperationalQueryId.SHOW_IP_OSPF_NEIGHBOR,
            expectation, query_cache,
        )
        if isinstance(show, RuntimeControlPlaneVerification):
            return show
        rows = parse_show_ip_ospf_neighbor(show.output)
        if not rows:
            return self._unobservable(
                expectation, ControlPlaneExecutionStage.OBSERVED,
                "Fresh OSPF output had no parser-backed neighbor row.",
            )
        fields = self._unobservable_fields(expectation)
        self._certify_source_device(fields, expectation, show)
        fields["protocol"] = FieldVerificationStatus.VERIFIED
        return self._direct_observation(
            expectation, fields, "fresh_show_ip_ospf_neighbor",
            "OSPF operation was observed; the local router ID is absent from this SHOW.",
        )

    def _observe_ospf_neighbor(self, expectation, action, query_cache):
        if not self._is_ospf_expectation(expectation, action):
            return self._unobservable(
                expectation, ControlPlaneExecutionStage.OBSERVED,
                "No registered live-fixture-backed query observes this neighbor protocol.",
            )
        show = self._fresh_show(
            action.device_name, OperationalQueryId.SHOW_IP_OSPF_NEIGHBOR,
            expectation, query_cache,
        )
        if isinstance(show, RuntimeControlPlaneVerification):
            return show
        rows = parse_show_ip_ospf_neighbor(show.output)
        if not rows:
            return self._unobservable(
                expectation, ControlPlaneExecutionStage.OBSERVED,
                "Fresh OSPF output had no parser-backed neighbor row.",
            )
        peer_id = expectation.expected.get("peer_router_id")
        peer_ip = expectation.expected.get("peer_ipv4")
        peer_row = next(
            (item for item in rows
             if isinstance(peer_id, str) and item.neighbor_id == peer_id),
            None,
        )
        fields = self._unobservable_fields(expectation)
        self._certify_source_device(fields, expectation, show)
        fields["protocol"] = FieldVerificationStatus.VERIFIED
        if isinstance(peer_id, str):
            fields["peer_router_id"] = self._field(peer_row is not None)
        if isinstance(peer_ip, str):
            fields["peer_ipv4"] = self._field(
                peer_row is not None and peer_row.address == peer_ip
            )
        adjacent = expectation.expected.get("adjacent")
        if isinstance(adjacent, bool):
            fields["adjacent"] = self._field(
                peer_row is not None
                and (peer_row.state.casefold() == "full") is adjacent
            )
        return self._direct_observation(
            expectation, fields, "fresh_show_ip_ospf_neighbor",
            "Fresh OSPF neighbor rows were matched by router ID, peer IPv4, "
            "and FULL adjacency state.",
        )

    def _observe_ospf_route(self, expectation, action, query_cache):
        if not self._is_ospf_expectation(expectation, action):
            return self._unobservable(
                expectation, ControlPlaneExecutionStage.OBSERVED,
                "No registered live-fixture-backed query observes this route protocol.",
            )
        show = self._fresh_show(
            action.device_name, OperationalQueryId.SHOW_IP_ROUTE_OSPF,
            expectation, query_cache,
        )
        if isinstance(show, RuntimeControlPlaneVerification):
            return show
        rows = parse_show_ip_route_ospf(show.output)
        if not rows:
            return self._unobservable(
                expectation, ControlPlaneExecutionStage.OBSERVED,
                "Fresh OSPF route output had no parser-backed route row.",
            )
        network = expectation.expected.get("network")
        route = next(
            (
                item for item in rows
                if isinstance(network, str)
                and item.prefix == network
                and item.code == "O"
            ),
            None,
        )
        fields = self._unobservable_fields(expectation)
        self._certify_source_device(fields, expectation, show)
        fields["protocol"] = self._field(route is not None)
        if isinstance(network, str):
            fields["network"] = self._field(route is not None)
        prefix_length = expectation.expected.get("prefix_length")
        if isinstance(prefix_length, int) and route is not None:
            if route.prefix_length is not None:
                fields["prefix_length"] = self._field(
                    route.prefix_length == prefix_length
                )
        next_hop = expectation.expected.get("next_hop")
        if isinstance(next_hop, str) and route is not None:
            fields["next_hop"] = self._field(route.next_hop == next_hop)
        outgoing = expectation.expected.get("outgoing_interface")
        if isinstance(outgoing, str) and route is not None:
            fields["outgoing_interface"] = self._field(
                self._interface_key(route.interface) == self._interface_key(outgoing)
            )
        return self._direct_observation(
            expectation, fields, "fresh_show_ip_route_ospf",
            "Fresh OSPF route rows were matched by exact prefix, protocol, and "
            "any explicitly observable route attributes.",
        )

    def _fresh_show(
        self,
        device_name: str,
        query_id: OperationalQueryId,
        expectation: ControlPlaneVerificationExpectation,
        query_cache: dict[tuple[str, OperationalQueryId], IosCommandResult],
        *,
        permit_truncated: bool = False,
    ) -> IosCommandResult | RuntimeControlPlaneVerification:
        key = (device_name, query_id)
        if key not in query_cache:
            try:
                query_cache[key] = self._ios.execute(device_name, query_id)
            except Exception as exc:
                return self._unobservable(
                    expectation, ControlPlaneExecutionStage.OBSERVED,
                    f"Registered IOS query raised {type(exc).__name__}: {exc}",
                )
        show = query_cache[key]
        if not show.executed or not show.fresh_output_observed:
            return self._unobservable(
                expectation, ControlPlaneExecutionStage.OBSERVED,
                show.failure_reason
                or "Registered IOS query produced no fresh current-command window.",
            )
        if show.truncated_by_pager and not permit_truncated:
            return self._unobservable(
                expectation,
                ControlPlaneExecutionStage.OBSERVED,
                "The registered IOS read-back was truncated by the pager; "
                "partial output cannot establish complete control-plane state.",
                evidence_method="registered_ios_output_truncated",
            )
        return show

    @staticmethod
    def _is_ospf_expectation(expectation, action) -> bool:
        return (
            isinstance(action, ConfigureOspfv2)
            and expectation.expected.get("protocol") == "ospfv2"
        )

    @staticmethod
    def _is_eigrp_expectation(expectation, action) -> bool:
        return (
            isinstance(action, ConfigureEigrpIpv4)
            and expectation.expected.get("protocol") == "eigrp"
        )

    def _applied_eigrp_action_for_device(
        self, device_id: str,
    ) -> ConfigureEigrpIpv4 | None:
        return next(
            (
                item for item in self._applied_actions.values()
                if isinstance(item, ConfigureEigrpIpv4)
                and item.device_id == device_id
            ),
            None,
        )

    @staticmethod
    def _typed_int_list(value) -> list[int] | None:
        if not isinstance(value, list) or any(type(item) is not int for item in value):
            return None
        return value

    @staticmethod
    def _typed_int_mapping(value) -> dict[int, int] | None:
        if not isinstance(value, dict):
            return None
        result: dict[int, int] = {}
        for raw_key, raw_value in value.items():
            if type(raw_value) is not int:
                return None
            if type(raw_key) is int:
                key = raw_key
            elif isinstance(raw_key, str) and raw_key.isdigit():
                key = int(raw_key)
            else:
                return None
            result[key] = raw_value
        return result

    @staticmethod
    def _typed_str_list(value) -> list[str] | None:
        if not isinstance(value, list) or any(type(item) is not str for item in value):
            return None
        return value

    @staticmethod
    def _interface_key(value: str) -> str:
        normalized = value.casefold().replace("-", "")
        for prefix, canonical in (
            ("fastethernet", "fa"),
            ("gigabitethernet", "gi"),
            ("portchannel", "po"),
            ("fa", "fa"),
            ("gi", "gi"),
            ("po", "po"),
        ):
            if normalized.startswith(prefix):
                return canonical + normalized[len(prefix):]
        return normalized

    @staticmethod
    def _unobservable_fields(expectation) -> dict[str, FieldVerificationStatus]:
        """Campos reclamados MAS los declarados explicitamente no reclamables.

        Los `unclaimed_fields` entran aqui a proposito. Si solo se partiera de
        `expected`, estrechar la expectativa bastaria para que
        `_direct_observation` viera "todos los campos VERIFIED" y devolviera
        VERIFIED, subiendo la afirmacion sin haber observado nada nuevo.
        """
        return {
            field: FieldVerificationStatus.UNOBSERVABLE
            for field in (
                *expectation.expected,
                *getattr(expectation, "unclaimed_fields", ()),
            )
        }

    @classmethod
    def _certify_source_device(cls, fields, expectation, show) -> None:
        """Ata `source_device_name` a QUIEN ejecuto, no a quien se pidio.

        Solo una atribucion unica del runtime certifica. Sin atribucion, o con
        mas de un candidato, el campo se queda UNOBSERVABLE: la alternativa
        seria escribir el nombre pedido, que es exactamente la sustitucion que
        esta evidencia existe para impedir. Y si la sesion atribuida no es la
        que el manifiesto ata a este device semantico, el campo FALLA -- no se
        omite, porque una mezcla de resultados entre devices es un defecto, no
        una ausencia de evidencia.
        """
        if "source_device_name" not in fields:
            return
        claimed = str(expectation.expected.get("source_device_name") or "")
        if not claimed:
            return
        try:
            provenance = DeviceIdentityProvenance(show.device_identity_provenance)
        except ValueError:
            # Una clasificacion que este observador no conoce no puede
            # certificar: no saber que significa no es haber observado.
            return
        if provenance is not DeviceIdentityProvenance.CONFIRMED_UNIQUE:
            return
        fields["source_device_name"] = cls._field(
            show.observed_device_name == claimed
        )

    @staticmethod
    def _field(matched: bool) -> FieldVerificationStatus:
        return (
            FieldVerificationStatus.VERIFIED
            if matched else FieldVerificationStatus.FAILED
        )

    @staticmethod
    def _applied_protocol(action) -> str:
        """Protocolo de la accion tipada que de verdad se aplico."""
        if isinstance(action, ConfigureRipv2):
            return DynamicRoutingProtocol.RIPV2.value
        if isinstance(action, ConfigureOspfv2):
            return DynamicRoutingProtocol.OSPFV2.value
        if isinstance(action, ConfigureEigrpIpv4):
            return DynamicRoutingProtocol.EIGRP.value
        return ""

    @staticmethod
    def _aggregate_status(fields) -> ActionExecutionStatus:
        """Un campo fallado FALLA; todo verificado VERIFICA; lo demas no afirma."""
        statuses = set(fields.values())
        return (
            ActionExecutionStatus.FAILED
            if FieldVerificationStatus.FAILED in statuses
            else ActionExecutionStatus.VERIFIED
            if statuses == {FieldVerificationStatus.VERIFIED}
            else ActionExecutionStatus.UNOBSERVABLE
        )

    @classmethod
    def _direct_observation(
        cls,
        expectation,
        fields,
        evidence_method,
        message,
        *,
        allow_partial=False,
        stage=ControlPlaneExecutionStage.OBSERVED,
    ):
        status = cls._aggregate_status(fields)
        if (
            allow_partial
            and status is ActionExecutionStatus.UNOBSERVABLE
            and FieldVerificationStatus.VERIFIED in set(fields.values())
        ):
            # PARTIAL is reserved for a new direct observation that proves at
            # least one claimed field while preserving another explicit ceiling.
            # Merely narrowing an expectation still cannot promote its status.
            status = ActionExecutionStatus.PARTIAL
        return RuntimeControlPlaneVerification(
            expectation_id=expectation.id,
            stage=stage,
            status=status,
            evidence_method=evidence_method,
            fresh_evidence=True,
            fields=fields,
            message=message,
        )

    @staticmethod
    def _unobservable(
        expectation: ControlPlaneVerificationExpectation,
        stage: ControlPlaneExecutionStage,
        message: str,
        *,
        evidence_method: str = "runtime_observability_limit",
    ) -> RuntimeControlPlaneVerification:
        return RuntimeControlPlaneVerification(
            expectation_id=expectation.id,
            stage=stage,
            status=ActionExecutionStatus.UNOBSERVABLE,
            evidence_method=evidence_method,
            fresh_evidence=False,
            fields={
                field: FieldVerificationStatus.UNOBSERVABLE
                for field in expectation.expected
            },
            message=message,
        )
