"""Adapter Packet Tracer para mutaciones y evidencia cerradas de E9."""

from __future__ import annotations

from collections.abc import Callable, Sequence
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
    IosCommandResult,
    OperationalQueryId,
    parse_show_etherchannel_summary,
    parse_show_ip_ospf_neighbor,
    parse_show_ip_interface,
    parse_show_ip_protocols_rip,
    parse_show_ip_route_rip,
    parse_show_ip_route_ospf,
    parse_show_spanning_tree,
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
        # RIP anuncia cada 30 s. Medido en R2-B fase 4: tras esperar 35 s las
        # rutas ya estaban, con edades 00:00:26 y 00:00:00. El presupuesto
        # cubre un ciclo completo de actualizacion con margen, y se agota
        # releyendo, nunca reaplicando.
        route_convergence_timeout_seconds: float = 45.0,
        route_convergence_interval_seconds: float = 5.0,
        route_convergence_attempts: int = 10,
        clock: Callable[[], float] = monotonic,
        sleeper: Callable[[float], None] = sleep,
    ) -> None:
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
                observed.failure_reason or "No fresh typed-ping result was observed.",
            )
        expected = expected_value
        matched = observed.reachable is expected
        status = (
            ActionExecutionStatus.VERIFIED if matched else ActionExecutionStatus.FAILED
        )
        return RuntimeControlPlaneVerification(
            expectation_id=expectation.id,
            stage=ControlPlaneExecutionStage.BEHAVIOR,
            status=status,
            evidence_method="typed_ping_current_command_window",
            fresh_evidence=True,
            fields={
                "reachable": (
                    FieldVerificationStatus.VERIFIED
                    if matched else FieldVerificationStatus.FAILED
                )
            },
            message=(
                f"Fresh typed ping matched reachable={expected}."
                if matched else f"Fresh typed ping differed from reachable={expected}."
            ),
            convergence=ConvergenceReport(
                attempts=1,
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
        show = self._fresh_show(
            action.device_name, OperationalQueryId.SHOW_SPANNING_TREE,
            expectation, query_cache,
        )
        if isinstance(show, RuntimeControlPlaneVerification):
            return show
        instances = parse_show_spanning_tree(show.output)
        if not instances:
            return self._unobservable(
                expectation, ControlPlaneExecutionStage.OBSERVED,
                "Fresh spanning-tree output had no parser-backed instance.",
            )
        fields = self._unobservable_fields(expectation)
        vlan_ids = self._typed_int_list(expectation.expected.get("vlan_ids"))
        root_vlans = self._typed_int_list(
            expectation.expected.get("root_primary_vlans")
        )
        by_vlan = {item.vlan_id: item for item in instances}
        selected = [by_vlan[item] for item in vlan_ids or [] if item in by_vlan]
        all_vlans_present = (
            vlan_ids is not None and len(selected) == len(vlan_ids)
        )
        if vlan_ids is not None:
            fields["vlan_ids"] = self._field(all_vlans_present)
        mode = expectation.expected.get("mode")
        if mode == "rapid-pvst" and all_vlans_present:
            fields["mode"] = self._field(
                bool(selected)
                and all(item.protocol.casefold() == "rstp" for item in selected)
            )
        if root_vlans is not None:
            fields["root_primary_vlans"] = self._field(all(
                vlan in by_vlan and by_vlan[vlan].root_is_local
                for vlan in root_vlans
            ))
        return self._direct_observation(
            expectation, fields, "fresh_show_spanning_tree",
            "Fresh parser-backed STP instances were compared by VLAN.",
        )

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
            return self._unobservable(
                expectation,
                ControlPlaneExecutionStage.OBSERVED,
                f"EIGRP AS {action.as_number} query support is known, but no "
                "non-empty PT neighbor row is fixture-backed.",
                evidence_method="eigrp_readback_unavailable",
            )
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
            return self._unobservable(
                expectation,
                ControlPlaneExecutionStage.OBSERVED,
                "EIGRP adjacency cannot be promoted from an empty neighbor table.",
                evidence_method="eigrp_readback_unavailable",
            )
        return self._observe_ospf_neighbor(expectation, action, query_cache)

    def _observe_route(self, expectation, action, query_cache):
        if isinstance(action, ConfigureRipv2):
            return self._observe_rip_route(expectation, action, query_cache)
        if isinstance(action, ConfigureEigrpIpv4):
            return self._unobservable(
                expectation,
                ControlPlaneExecutionStage.OBSERVED,
                "EIGRP route state cannot be promoted from an empty route table.",
                evidence_method="eigrp_readback_unavailable",
            )
        return self._observe_ospf_route(expectation, action, query_cache)

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
        show = self._fresh_show(
            action.device_name, OperationalQueryId.SHOW_IP_PROTOCOLS,
            expectation, query_cache, permit_truncated=True,
        )
        if isinstance(show, RuntimeControlPlaneVerification):
            return show
        if show.truncated_by_pager:
            # Un `show ip protocols` cortado por el pager puede esconder
            # sentencias de red o interfaces pasivas: leerlo como ausencia
            # produciria un FAILED falso.
            return self._unobservable(
                expectation, ControlPlaneExecutionStage.OBSERVED,
                "The RIP read-back was truncated by the IOS pager.",
                evidence_method="rip_readback_truncated",
            )
        observed = parse_show_ip_protocols_rip(show.output)
        fields = self._unobservable_fields(expectation)
        if observed is None:
            return self._direct_observation(
                expectation,
                {field: FieldVerificationStatus.FAILED for field in fields},
                "fresh_show_ip_protocols",
                "Fresh output reports no RIP routing process on the device.",
            )
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
        return self._direct_observation(
            expectation, fields, "fresh_show_ip_protocols",
            "Fresh RIP state was compared semantically against the typed intent.",
        )

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
    def _typed_int_list(value) -> list[int] | None:
        if not isinstance(value, list) or any(type(item) is not int for item in value):
            return None
        return value

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

    @staticmethod
    def _field(matched: bool) -> FieldVerificationStatus:
        return (
            FieldVerificationStatus.VERIFIED
            if matched else FieldVerificationStatus.FAILED
        )

    @staticmethod
    def _direct_observation(expectation, fields, evidence_method, message):
        statuses = set(fields.values())
        status = (
            ActionExecutionStatus.FAILED
            if FieldVerificationStatus.FAILED in statuses
            else ActionExecutionStatus.VERIFIED
            if statuses == {FieldVerificationStatus.VERIFIED}
            else ActionExecutionStatus.UNOBSERVABLE
        )
        return RuntimeControlPlaneVerification(
            expectation_id=expectation.id,
            stage=ControlPlaneExecutionStage.OBSERVED,
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
