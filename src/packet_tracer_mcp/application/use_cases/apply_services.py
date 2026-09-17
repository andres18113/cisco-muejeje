"""Aplicación E6 con preflight, DAG y verificación conductual independiente."""

from __future__ import annotations

from collections.abc import Sequence
from time import monotonic
from typing import Protocol

from ...domain.enterprise.models.capabilities import CapabilityStatus
from ...domain.enterprise.models.configuration_runtime import (
    ActionApplicationResult,
    ActionExecutionStatus,
    ConfigurationApplicationStatus,
    ConfigurationFailureCode,
    ConfigurationRuntimeContext,
    MutationDecision,
    MutationResidue,
    RuntimeActionMutation,
    RuntimeConfigurationTarget,
    decide_mutation,
    sanitized_mutation_snapshot,
)
from ...domain.enterprise.models.deployment import (
    DeploymentIdentityError,
    DeploymentManifest,
    requires_deployment_manifest,
    resolve_manifest_targets,
    validate_manifest_environment,
)
from ...domain.enterprise.models.evidence import (
    ReadinessStatus,
)
from ...domain.enterprise.models.execution import (
    DispatchFact,
    FootprintFact,
    PostconditionFact,
    ResultFact,
    TransitionFact,
    journal_from_action_results,
    satisfies_apply_dependency,
)
from ...domain.enterprise.models.service_plan import (
    ServiceAction,
    ServiceCapabilityProfile,
    ServiceEvidenceKind,
    ServicePlan,
    ServiceVerificationExpectation,
    ServiceVerificationKind,
)
from ...domain.enterprise.models.service_runtime import (
    ObservationFact,
    RuntimeServiceVerification,
    ServiceApplicationResult,
    ServiceOutcome,
    ServiceVerificationResult,
    evidence_from_service_verification,
)
from ...domain.enterprise.models.verification import (
    PrerequisiteKind,
    VerificationPrerequisite,
    order_verification_expectations,
    prerequisites_satisfied,
)
from ...domain.enterprise.services.configuration_dependencies import (
    ConfigurationDependencyError,
    order_dependency_actions,
)

#: How a verification expectation touches the environment it reads. It decides
#: what may still run after the action it depends on left its outcome
#: unresolved: a read-only probe and a probe that creates and releases its own
#: client can both run again safely, while a probe that changes user-visible
#: state cannot be repeated on an unresolved prerequisite.
VERIFICATION_EFFECT_CLASSES: dict[ServiceVerificationKind, str] = {
    ServiceVerificationKind.DIRECT_SERVICE_STATE: "read_only",
    ServiceVerificationKind.DNS_RESOLUTION: "owned_temporary",
    ServiceVerificationKind.DNS_NEGATIVE_CONTROL: "owned_temporary",
    ServiceVerificationKind.HTTP_FETCH: "owned_temporary",
    ServiceVerificationKind.HTTPS_FETCH: "owned_temporary",
    ServiceVerificationKind.HTTP_BY_HOSTNAME: "owned_temporary",
    ServiceVerificationKind.NTP_SYNC: "read_only",
    ServiceVerificationKind.TFTP_RETRIEVE: "read_only",
}

#: Verification failure code per status, split by whether the read was a
#: direct read-back of the service's own state or an independent behavioral
#: observation. Derived from the status, never from the reader's own opinion:
#: the runtime states what it observed and the applicator names the code.
_DIRECT_FAILURE_CODES = {
    ActionExecutionStatus.VERIFIED: ConfigurationFailureCode.NONE,
    ActionExecutionStatus.FAILED: ConfigurationFailureCode.VERIFICATION_FAILED,
    ActionExecutionStatus.UNKNOWN: ConfigurationFailureCode.OUTCOME_UNKNOWN,
    ActionExecutionStatus.UNOBSERVABLE: (
        ConfigurationFailureCode.DIRECT_READBACK_UNOBSERVABLE
    ),
    ActionExecutionStatus.PARTIAL: ConfigurationFailureCode.OBSERVABILITY_LIMITATION,
}

_BEHAVIORAL_FAILURE_CODES = {
    ActionExecutionStatus.VERIFIED: ConfigurationFailureCode.NONE,
    ActionExecutionStatus.FAILED: (
        ConfigurationFailureCode.BEHAVIORAL_VERIFICATION_FAILED
    ),
    ActionExecutionStatus.UNKNOWN: ConfigurationFailureCode.OUTCOME_UNKNOWN,
    ActionExecutionStatus.UNOBSERVABLE: (
        ConfigurationFailureCode.OBSERVABILITY_LIMITATION
    ),
    ActionExecutionStatus.PARTIAL: ConfigurationFailureCode.OBSERVABILITY_LIMITATION,
}


class ServiceRuntime(Protocol):
    """The port an E6 service runtime must implement."""

    def inventory(self) -> list[RuntimeConfigurationTarget]:
        """Return the devices the runtime can see."""

    def apply_actions(
        self,
        actions: Sequence[ServiceAction],
    ) -> list[RuntimeActionMutation]:
        """Apply one batch and report what was observed per action."""

    def verify(
        self,
        expectation: ServiceVerificationExpectation,
    ) -> RuntimeServiceVerification:
        """Observe one expectation."""


class ServiceApplicator:
    """Ejecuta un ServicePlan; nunca compila ni aplica configuración E5."""

    def __init__(self, runtime: ServiceRuntime) -> None:
        """Bind the applicator to one service runtime."""
        self._runtime = runtime

    def apply(
        self,
        plan: ServicePlan,
        *,
        actual_source_topology_hash: str,
        actual_source_configuration_hash: str,
        foundational_statuses: dict[str, ActionExecutionStatus],
        capabilities: dict[str, ServiceCapabilityProfile] | None = None,
        runtime_context: ConfigurationRuntimeContext | None = None,
        deployment_manifest: DeploymentManifest | None = None,
    ) -> ServiceApplicationResult:
        """Apply one ServicePlan and return its full typed outcome."""
        started = monotonic()
        runtime_context = runtime_context or ConfigurationRuntimeContext()
        deployment_id = deployment_manifest.deployment_id if deployment_manifest else ""
        if actual_source_topology_hash != plan.source_topology_hash:
            return self._failure(
                plan,
                ConfigurationFailureCode.SOURCE_TOPOLOGY_MISMATCH,
                "ServicePlan source hash does not match the deployed E4 topology.",
                context=runtime_context,
                deployment_id=deployment_id,
                started=started,
            )
        if (
            deployment_manifest is not None
            and deployment_manifest.physical_topology_hash != plan.source_topology_hash
        ):
            return self._failure(
                plan,
                ConfigurationFailureCode.TARGET_IDENTITY_MISMATCH,
                "DeploymentManifest physical topology hash does not match ServicePlan.",
                context=runtime_context,
                deployment_id=deployment_id,
                started=started,
            )
        if deployment_manifest is None and requires_deployment_manifest(
            plan.source_topology_hash_schema
        ):
            return self._failure(
                plan,
                ConfigurationFailureCode.DEPLOYMENT_MANIFEST_REQUIRED,
                "ServicePlan uses physical-topology-v2 identity and requires a "
                "DeploymentManifest; name-only runtime fallback is legacy-only.",
                context=runtime_context,
                deployment_id=deployment_id,
                started=started,
            )
        if deployment_manifest is not None:
            try:
                validate_manifest_environment(
                    deployment_manifest,
                    runtime_context.environment_fingerprint,
                )
            except DeploymentIdentityError as exc:
                return self._failure(
                    plan,
                    ConfigurationFailureCode.ENVIRONMENT_FINGERPRINT_MISMATCH,
                    str(exc),
                    context=runtime_context,
                    deployment_id=deployment_id,
                    started=started,
                )
        if actual_source_configuration_hash != plan.source_configuration_hash:
            return self._failure(
                plan,
                ConfigurationFailureCode.SOURCE_CONFIGURATION_MISMATCH,
                "ServicePlan source hash does not match the applied E5 configuration.",
                context=runtime_context,
                deployment_id=deployment_id,
                started=started,
            )
        try:
            ordered = order_dependency_actions(plan.actions)
        except ConfigurationDependencyError as exc:
            return self._failure(
                plan,
                ConfigurationFailureCode.DEPENDENCY_BLOCKED,
                str(exc),
                context=runtime_context,
                deployment_id=deployment_id,
                started=started,
            )
        if [item.id for item in ordered] != [item.id for item in plan.actions]:
            return self._failure(
                plan,
                ConfigurationFailureCode.DEPENDENCY_BLOCKED,
                "ServicePlan actions are not in deterministic dependency order.",
                context=runtime_context,
                deployment_id=deployment_id,
                started=started,
            )
        missing_foundation = sorted(
            item.configuration_action_id
            for item in plan.foundational_requirements
            if foundational_statuses.get(item.configuration_action_id)
            is not ActionExecutionStatus.VERIFIED
        )
        if missing_foundation:
            return self._failure(
                plan,
                ConfigurationFailureCode.FOUNDATIONAL_CONFIGURATION_MISSING,
                "Foundational E5 actions are not VERIFIED: "
                + ", ".join(missing_foundation),
                context=runtime_context,
                deployment_id=deployment_id,
                started=started,
            )
        try:
            runtime_inventory = self._runtime.inventory()
        except Exception as exc:
            return self._failure(
                plan,
                ConfigurationFailureCode.SESSION_FAILED,
                f"Runtime inventory failed: {exc}",
                context=runtime_context,
                deployment_id=deployment_id,
                started=started,
            )
        deployed_names: dict[str, str] = {}
        if deployment_manifest is not None:
            semantic_device_ids = (
                [item.device_id for item in plan.foundational_requirements]
                + [item.host_device_id for item in plan.actions]
                + [
                    identifier
                    for item in plan.verification_expectations
                    for identifier in (item.host_device_id, item.client_device_id)
                    if identifier
                ]
            )
            try:
                semantic_targets = resolve_manifest_targets(
                    deployment_manifest,
                    physical_topology_hash=plan.source_topology_hash,
                    semantic_device_ids=semantic_device_ids,
                    inventory=runtime_inventory,
                )
            except DeploymentIdentityError as exc:
                return self._failure(
                    plan,
                    ConfigurationFailureCode.TARGET_IDENTITY_MISMATCH,
                    str(exc),
                    context=runtime_context,
                    deployment_id=deployment_id,
                    started=started,
                )
            deployed_names = {
                identifier: target.device_name
                for identifier, target in semantic_targets.items()
            }
            targets = semantic_targets
        else:
            inventory_by_name = {item.device_name: item for item in runtime_inventory}
            deployed_names = {
                item.device_id: item.device_name
                for item in plan.foundational_requirements
            }
            deployed_names.update(
                {item.host_device_id: item.host_device_name for item in plan.actions}
            )
            deployed_names.update(
                {
                    identifier: name
                    for item in plan.verification_expectations
                    for identifier, name in (
                        (item.host_device_id, item.host_device_name),
                        (item.client_device_id, item.client_device_name),
                    )
                    if identifier
                }
            )
            targets = {
                item.device_id: inventory_by_name[item.device_name]
                for item in plan.foundational_requirements
                if item.device_name in inventory_by_name
            }
        target_errors = []
        for requirement in plan.foundational_requirements:
            target = targets.get(requirement.device_id)
            if target is None:
                target_errors.append(f"Target {requirement.device_name} was not found.")
            elif target.model.casefold() != requirement.model.casefold():
                target_errors.append(
                    f"Target {requirement.device_name} model {target.model} does not match "
                    f"{requirement.model}."
                )
        if target_errors:
            code = (
                ConfigurationFailureCode.TARGET_IDENTITY_MISMATCH
                if any("model" in item.casefold() for item in target_errors)
                else ConfigurationFailureCode.TARGET_NOT_FOUND
            )
            return self._failure(
                plan,
                code,
                *sorted(target_errors),
                context=runtime_context,
                started=started,
                deployment_id=deployment_id,
            )

        capabilities = capabilities or {}
        results: dict[str, ActionApplicationResult] = {}
        # One decision per mutation row, computed once and reused. A second
        # call would be a second chance to disagree, and an audit
        # re-evaluation must run on the retained input snapshot instead.
        decisions: dict[str, MutationDecision] = {}
        for action in plan.actions:
            profile = capabilities.get(
                f"{action.host_model}:{action.service_type.value}"
            )
            support = (
                profile.action_application_support.get(
                    action.action_type.value,
                    profile.application_support,
                )
                if profile
                else CapabilityStatus.UNKNOWN
            )
            if support is CapabilityStatus.SUPPORTED:
                continue
            failure = (
                ConfigurationFailureCode.CAPABILITY_UNSUPPORTED
                if support is CapabilityStatus.UNSUPPORTED
                else ConfigurationFailureCode.CAPABILITY_UNKNOWN
            )
            results[action.id] = ActionApplicationResult(
                action_id=action.id,
                status=ActionExecutionStatus.SKIPPED,
                failure_code=failure,
                message=(
                    f"{action.host_model}:{action.service_type.value}:"
                    f"{action.action_type.value} is {support.value}."
                ),
            )

        pending = [item for item in plan.actions if item.id not in results]
        while pending:
            progress = False
            for action in list(pending):
                failed_dependencies = [
                    dependency
                    for dependency in action.depends_on
                    if dependency in results
                    and not self._effect_established(dependency, decisions, results)
                ]
                if failed_dependencies:
                    results[action.id] = ActionApplicationResult(
                        action_id=action.id,
                        status=ActionExecutionStatus.DEPENDENCY_BLOCKED,
                        failure_code=ConfigurationFailureCode.DEPENDENCY_BLOCKED,
                        message="Blocked by: "
                        + ", ".join(
                            self._blocked_message(dependency, decisions, results)
                            for dependency in sorted(failed_dependencies)
                        ),
                    )
                    pending.remove(action)
                    progress = True
            ready = [
                item
                for item in pending
                if all(
                    dependency in results
                    and self._effect_established(dependency, decisions, results)
                    for dependency in item.depends_on
                )
            ]
            if ready:
                first = ready[0]
                batch = [
                    item
                    for item in ready
                    if item.phase == first.phase
                    and item.host_device_id == first.host_device_id
                ]
                try:
                    runtime_batch = [
                        item.model_copy(
                            update={
                                "host_device_name": deployed_names[item.host_device_id],
                            }
                        )
                        for item in batch
                    ]
                    mutations = {
                        item.action_id: item
                        for item in self._runtime.apply_actions(runtime_batch)
                    }
                except Exception as exc:
                    mutations = {
                        item.id: self._session_failed_mutation(
                            item,
                            type(exc).__name__,
                        )
                        for item in batch
                    }
                for item in batch:
                    mutation = mutations.get(item.id)
                    if mutation is None:
                        # TD-12.2. This port holds no acceptance evidence for
                        # the missing item, so it must not conclude row 7,
                        # which asserts a proven ACCEPTED, CORRELATED
                        # envelope. An absent item is a runtime-boundary
                        # contract error and takes the row 15 uncertainty
                        # path: the command may have run, and an empty list
                        # from a runtime that dispatched nothing is not proof
                        # of dispatch either way.
                        mutation = self._session_failed_mutation(
                            item,
                            "MissingRuntimeMutationResult",
                        )
                    decision = decide_mutation(mutation)
                    decisions[item.id] = decision
                    results[item.id] = ActionApplicationResult(
                        action_id=item.id,
                        status=decision.status,
                        failure_code=decision.failure_code,
                        message=mutation.message,
                        batch_id=mutation.batch_id,
                        operation=item.operation,
                        disposition=decision.disposition,
                        dispatch=mutation.dispatch,
                        result=mutation.result,
                        postcondition=mutation.postcondition,
                        transition=mutation.transition,
                        footprint=mutation.footprint,
                        attempted=mutation.attempted,
                        residual_change=decision.residue is MutationResidue.CHANGED,
                        cause=decision.cause,
                        received_mutation=sanitized_mutation_snapshot(mutation),
                    )
                    pending.remove(item)
                progress = True
            if not progress:
                for item in pending:
                    results[item.id] = ActionApplicationResult(
                        action_id=item.id,
                        status=ActionExecutionStatus.DEPENDENCY_BLOCKED,
                        failure_code=ConfigurationFailureCode.DEPENDENCY_BLOCKED,
                        message="No executable dependency frontier remained.",
                    )
                break

        action_results = [results[item.id] for item in plan.actions]
        limitations = [
            f"residue_unknown:{identifier}:{decision.cause or decision.row}"
            for identifier, decision in sorted(decisions.items())
            if decision.residue is MutationResidue.UNKNOWN
        ]
        verification, recovery_limitations = self._verify(
            plan,
            results,
            capabilities,
            deployed_names,
            decisions,
        )
        limitations.extend(recovery_limitations)
        outcomes = self._outcomes(plan, results, verification)
        journal = journal_from_action_results(
            plan_id=plan.id,
            deployment_id=deployment_id,
            actions=list(plan.actions),
            results=action_results,
        )
        sticky = sorted(
            identifier for identifier, decision in decisions.items() if decision.sticky
        )
        if sticky:
            # Exactly the decisions that said so. No field predicate
            # re-derives this: the flag is an output of the decision, and
            # re-deriving it from fields is how a row could be sticky in one
            # place and not in another.
            journal.mark_transport_unknown(
                "transport_unknown: " + ", ".join(sticky),
            )
        status, failure_code = self._overall(
            action_results,
            outcomes,
            transport_unknown=bool(sticky),
        )
        if sticky:
            limitations.extend(
                f"transport_unknown:{identifier}" for identifier in sticky
            )
        expectations_by_id = {item.id: item for item in plan.verification_expectations}
        evidence_records = [
            evidence_from_service_verification(
                item,
                identifier=f"evidence/{item.expectation_id}",
                subject=item.service_id,
                claim=expectations_by_id[item.expectation_id].kind.value,
                backend=runtime_context.evidence_backend,
                backend_version=runtime_context.evidence_backend_version,
                environment_fingerprint=runtime_context.environment_semantic_hash,
                capability_snapshot_hash=runtime_context.capability_snapshot_hash,
            )
            for item in verification
        ]
        return ServiceApplicationResult(
            service_plan_id=plan.id,
            service_semantic_hash=plan.semantic_hash,
            source_topology_hash=plan.source_topology_hash,
            source_configuration_hash=plan.source_configuration_hash,
            runtime_context=runtime_context,
            status=status,
            failure_code=failure_code,
            action_results=action_results,
            verification_results=verification,
            services=outcomes,
            deployment_id=deployment_id,
            execution_journal=journal,
            dirty_state=journal.dirty_state,
            evidence_records=evidence_records,
            limitations=limitations,
            duration_ms=int((monotonic() - started) * 1000),
        )

    @staticmethod
    def _session_failed_mutation(
        action: ServiceAction,
        type_name: str,
    ) -> RuntimeActionMutation:
        """Build the row 15 fact tuple for one action of a failed batch.

        Row 15, not `applied=False` with FAILED. FAILED is a definite local
        negative -- the payload never left the process -- and a runtime that
        raised after dispatching cannot support that claim. The postcondition
        and the transition are UNOBSERVED, `attempted` stays None, and the
        decision turns this into UNKNOWN with SESSION_FAILED and a sticky
        flag.
        """
        return RuntimeActionMutation(
            action_id=action.id,
            applied=False,
            operation=action.operation,
            dispatch=DispatchFact.UNSPECIFIED,
            result=ResultFact.NOT_APPLICABLE,
            postcondition=PostconditionFact.UNOBSERVED,
            transition=TransitionFact.UNOBSERVED,
            footprint=FootprintFact.NOT_APPLICABLE,
            attempted=None,
            cause=f"exception:{type_name}",
            message=f"The service runtime raised {type_name} for this batch.",
        )

    @staticmethod
    def _effect_established(
        action_id: str,
        decisions: dict[str, object],
        results: dict[str, ActionApplicationResult],
    ) -> bool:
        """Whether a dependent may proceed on this action's outcome.

        The decision's `frontier` is the only input. The raw `postcondition`
        field is never consulted: a SATISFIED postcondition inside an
        inconsistent tuple is exactly the value that must grant nothing, and
        reading the field directly is how it would have granted something.
        """
        decision = decisions.get(action_id)
        if decision is not None:
            return bool(decision.frontier)
        result = results.get(action_id)
        return result is not None and satisfies_apply_dependency(result.status)

    @staticmethod
    def _blocked_message(
        dependency: str,
        decisions: dict[str, object],
        results: dict[str, ActionApplicationResult],
    ) -> str:
        """Name why a prerequisite did not open the frontier.

        Unresolved and unsatisfied are different problems and lead to
        different operator actions, so they get different messages.
        """
        result = results.get(dependency)
        decision = decisions.get(dependency)
        unsatisfied = (
            result is not None
            and result.postcondition is PostconditionFact.UNSATISFIED
            and decision is not None
            and decision.row != "inconsistent"
        )
        if unsatisfied:
            return f"prerequisite_unsatisfied:{dependency}"
        return f"prerequisite_outcome_unknown:{dependency}"

    def _verify(self, plan, action_results, capabilities, deployed_names, decisions):
        """Observe every expectation the frontier and the capabilities admit.

        Returns the rows plus the limitations that recovery reads added, so a
        run that read anything after an unresolved action says so in its own
        result rather than only in a message.
        """
        results: dict[str, ServiceVerificationResult] = {}
        recovery_limitations: list[str] = []
        services = {item.id: item for item in plan.services}
        action_statuses = {
            identifier: result.status for identifier, result in action_results.items()
        }
        dag_expectations = [
            expectation
            if expectation.verification_prerequisites
            else expectation.model_copy(
                update={
                    "verification_prerequisites": [
                        VerificationPrerequisite(
                            kind=PrerequisiteKind.ACTION_APPLIED,
                            reference_id=expectation.action_id,
                        ),
                        *[
                            VerificationPrerequisite(
                                kind=PrerequisiteKind.VERIFICATION_VERIFIED,
                                reference_id=identifier,
                            )
                            for identifier in expectation.depends_on
                        ],
                    ],
                }
            )
            for expectation in plan.verification_expectations
        ]
        try:
            ordered = order_verification_expectations(dag_expectations)
        except Exception as exc:
            return (
                [
                    ServiceVerificationResult(
                        expectation_id=expectation.id,
                        service_id=expectation.service_id,
                        status=ActionExecutionStatus.DEPENDENCY_BLOCKED,
                        evidence_kind=expectation.evidence_kind,
                        failure_code=ConfigurationFailureCode.DEPENDENCY_BLOCKED,
                        message=str(exc),
                    )
                    for expectation in plan.verification_expectations
                ],
                [],
            )
        for expectation in ordered:
            prerequisites = expectation.verification_prerequisites or [
                VerificationPrerequisite(
                    kind=PrerequisiteKind.ACTION_APPLIED,
                    reference_id=expectation.action_id,
                ),
                *[
                    VerificationPrerequisite(
                        kind=PrerequisiteKind.VERIFICATION_VERIFIED,
                        reference_id=identifier,
                    )
                    for identifier in expectation.depends_on
                ],
            ]
            satisfied, blocked = prerequisites_satisfied(
                prerequisites,
                action_statuses=action_statuses,
                verification_statuses={
                    identifier: result.status for identifier, result in results.items()
                },
                resource_statuses={},
            )
            unresolved = sorted(
                item.reference_id
                for item in prerequisites
                if item.kind is PrerequisiteKind.ACTION_APPLIED
                and item.reference_id in action_results
                and not self._effect_established(
                    item.reference_id, decisions, action_results
                )
            )
            recovery = ""
            if unresolved:
                # An ACTION_APPLIED prerequisite is satisfied only by the
                # frontier. A read-only or owned-temporary probe may still run
                # as a RECOVERY read: it creates nothing the operator has to
                # undo, and a fresh reading is exactly what an unresolved
                # action needs. It never rewrites the action row, never clears
                # the sticky flag and never claims an execution count. A
                # user-state probe cannot be repeated on an unresolved
                # prerequisite, so it stays blocked.
                effect_class = VERIFICATION_EFFECT_CLASSES.get(expectation.kind)
                if effect_class in {"read_only", "owned_temporary"}:
                    recovery = "recovery_read_after_unresolved_action:" + ",".join(
                        unresolved
                    )
                    satisfied = True
                    blocked = [
                        item
                        for item in blocked
                        if not any(item.endswith(name) for name in unresolved)
                    ]
                    satisfied = not blocked
                else:
                    blocked = sorted(
                        set(blocked)
                        | {
                            self._blocked_message(name, decisions, action_results)
                            for name in unresolved
                        }
                    )
                    satisfied = False
            if not satisfied:
                results[expectation.id] = ServiceVerificationResult(
                    expectation_id=expectation.id,
                    service_id=expectation.service_id,
                    status=ActionExecutionStatus.DEPENDENCY_BLOCKED,
                    evidence_kind=expectation.evidence_kind,
                    failure_code=ConfigurationFailureCode.DEPENDENCY_BLOCKED,
                    message="Blocked by: " + ", ".join(blocked),
                )
                continue
            service = services[expectation.service_id]
            profile = capabilities.get(
                f"{service.host_model}:{service.service_type.value}"
            )
            support = CapabilityStatus.UNKNOWN
            if profile is not None:
                support = (
                    profile.direct_readback_support
                    if expectation.evidence_kind is ServiceEvidenceKind.DIRECT_STATE
                    else profile.behavioral_verification_support
                )
            readiness = (
                profile.capability_readiness.get("behavioral_verification")
                if profile is not None
                and expectation.evidence_kind is not ServiceEvidenceKind.DIRECT_STATE
                else None
            )
            if (
                readiness is not None
                and readiness.verify is ReadinessStatus.UNOBSERVABLE
            ):
                reasons = readiness.reasons.get("verify", [])
                results[expectation.id] = ServiceVerificationResult(
                    expectation_id=expectation.id,
                    service_id=expectation.service_id,
                    status=ActionExecutionStatus.UNOBSERVABLE,
                    evidence_kind=expectation.evidence_kind,
                    failure_code=ConfigurationFailureCode.OBSERVABILITY_LIMITATION,
                    message=" ".join(reasons) or "Behavioral state is unobservable.",
                )
                continue
            if support is not CapabilityStatus.SUPPORTED:
                results[expectation.id] = ServiceVerificationResult(
                    expectation_id=expectation.id,
                    service_id=expectation.service_id,
                    status=(
                        ActionExecutionStatus.UNKNOWN
                        if support is CapabilityStatus.UNKNOWN
                        else ActionExecutionStatus.PARTIAL
                    ),
                    evidence_kind=expectation.evidence_kind,
                    failure_code=(
                        ConfigurationFailureCode.DIRECT_READBACK_UNOBSERVABLE
                        if expectation.evidence_kind is ServiceEvidenceKind.DIRECT_STATE
                        else ConfigurationFailureCode.CAPABILITY_UNKNOWN
                    ),
                    message=f"Verification capability is {support.value}.",
                )
                continue
            try:
                runtime_expectation = expectation.model_copy(
                    update={
                        "host_device_name": deployed_names[expectation.host_device_id],
                        "client_device_name": (
                            deployed_names[expectation.client_device_id]
                            if expectation.client_device_id
                            else expectation.client_device_name
                        ),
                    }
                )
                observed = self._runtime.verify(runtime_expectation)
                row = ServiceVerificationResult(
                    **observed.model_dump(),
                    service_id=expectation.service_id,
                    failure_code=self._verification_failure_code(
                        observed.status,
                        direct=(
                            expectation.evidence_kind
                            is ServiceEvidenceKind.DIRECT_STATE
                        ),
                    ),
                )
                if recovery:
                    recovery_limitations.append(recovery)
                    row = row.model_copy(
                        update={"limitations": [*row.limitations, recovery]},
                    )
                results[expectation.id] = row
            except Exception as exc:
                # A reader that raised observed nothing, so the outcome is
                # unknown, not failed. FAILED here would be a fresh negative
                # observation the run never made.
                results[expectation.id] = ServiceVerificationResult(
                    expectation_id=expectation.id,
                    service_id=expectation.service_id,
                    status=ActionExecutionStatus.UNKNOWN,
                    evidence_kind=expectation.evidence_kind,
                    failure_code=ConfigurationFailureCode.SESSION_FAILED,
                    observation=ObservationFact.INCONCLUSIVE,
                    cause=f"exception:{type(exc).__name__}",
                    message=str(exc),
                )
        return (
            [results[item.id] for item in plan.verification_expectations],
            recovery_limitations,
        )

    @staticmethod
    def _verification_failure_code(
        status: ActionExecutionStatus,
        *,
        direct: bool,
    ) -> ConfigurationFailureCode:
        """Name the code the verification status implies.

        Derived from the status alone, and split only by whether the read was
        a direct read-back or an independent behavioral observation. A reader
        never supplies its own code: it states what it observed.
        """
        table = _DIRECT_FAILURE_CODES if direct else _BEHAVIORAL_FAILURE_CODES
        return table.get(status, ConfigurationFailureCode.OUTCOME_UNKNOWN)

    @staticmethod
    def _outcomes(plan, actions, verification):
        outcomes = []
        for service in plan.services:
            service_actions = [actions[item] for item in service.action_ids]
            application = (
                ActionExecutionStatus.APPLIED
                if service_actions
                and all(
                    satisfies_apply_dependency(item.status) for item in service_actions
                )
                else ActionExecutionStatus.FAILED
                if any(
                    item.status is ActionExecutionStatus.FAILED
                    for item in service_actions
                )
                else ActionExecutionStatus.PARTIAL
            )
            observed = [item for item in verification if item.service_id == service.id]
            direct = [
                item
                for item in observed
                if item.evidence_kind is ServiceEvidenceKind.DIRECT_STATE
            ]
            behavior = [
                item
                for item in observed
                if item.evidence_kind is not ServiceEvidenceKind.DIRECT_STATE
            ]
            direct_status = ServiceApplicator._aggregate(direct)
            behavior_status = ServiceApplicator._aggregate(behavior)
            usability = (
                ActionExecutionStatus.VERIFIED
                if behavior and behavior_status is ActionExecutionStatus.VERIFIED
                else ActionExecutionStatus.FAILED
                if behavior_status is ActionExecutionStatus.FAILED
                else ActionExecutionStatus.PARTIAL
                if behavior
                else application
            )
            # A direct read that FRESHLY contradicted the service's own state
            # caps usability even when behavior verified. The two readings
            # disagree, and the optimistic one does not get to win: PARTIAL or
            # UNOBSERVABLE direct state keeps the existing rule, because
            # neither of those observed a contradiction.
            if usability is ActionExecutionStatus.VERIFIED and any(
                item.status is ActionExecutionStatus.FAILED and item.fresh_evidence
                for item in direct
            ):
                usability = ActionExecutionStatus.PARTIAL
            outcomes.append(
                ServiceOutcome(
                    service_id=service.id,
                    service_type=service.service_type,
                    application_status=application,
                    direct_readback_status=direct_status,
                    behavioral_status=behavior_status,
                    usability_status=usability,
                )
            )
        return outcomes

    @staticmethod
    def _aggregate(items):
        if not items:
            return ActionExecutionStatus.UNKNOWN
        if any(item.status is ActionExecutionStatus.FAILED for item in items):
            return ActionExecutionStatus.FAILED
        if any(
            item.status is ActionExecutionStatus.DEPENDENCY_BLOCKED for item in items
        ):
            return ActionExecutionStatus.PARTIAL
        if all(item.status is ActionExecutionStatus.VERIFIED for item in items):
            return ActionExecutionStatus.VERIFIED
        return ActionExecutionStatus.PARTIAL

    @staticmethod
    def _overall(actions, outcomes, *, transport_unknown: bool = False):
        """Aggregate one run, never above what its weakest fact supports.

        `transport_unknown` caps the run at PARTIAL. A run holding a sticky
        row does not know whether one of its own mutations happened, and
        VERIFIED would assert that every intended state is in place.
        Residue-only uncertainty (rows 9 and 18) does NOT come through here:
        a satisfied postcondition with an unobserved residue is a different
        claim, so such a run may still be VERIFIED and reports its
        `residue_unknown` limitation and an UNKNOWN `dirty_state`.
        """
        if any(item.status is ActionExecutionStatus.FAILED for item in actions):
            return (
                ConfigurationApplicationStatus.FAILED,
                ConfigurationFailureCode.APPLICATION_FAILED,
            )
        critical_unsatisfied = any(
            item.status is ActionExecutionStatus.PARTIAL
            and item.failure_code is ConfigurationFailureCode.POSTCONDITION_UNSATISFIED
            for item in actions
        )
        if critical_unsatisfied:
            return (
                ConfigurationApplicationStatus.FAILED,
                ConfigurationFailureCode.POSTCONDITION_UNSATISFIED,
            )
        if any(
            item.status
            in {
                ActionExecutionStatus.SKIPPED,
                ActionExecutionStatus.DEPENDENCY_BLOCKED,
            }
            for item in actions
        ):
            return ConfigurationApplicationStatus.PARTIAL, ConfigurationFailureCode.NONE
        if transport_unknown:
            return (
                ConfigurationApplicationStatus.PARTIAL,
                ConfigurationFailureCode.OUTCOME_UNKNOWN,
            )
        if outcomes and all(
            item.usability_status is ActionExecutionStatus.VERIFIED for item in outcomes
        ):
            return (
                ConfigurationApplicationStatus.VERIFIED,
                ConfigurationFailureCode.NONE,
            )
        if any(
            item.usability_status is ActionExecutionStatus.FAILED for item in outcomes
        ):
            return (
                ConfigurationApplicationStatus.PARTIAL,
                ConfigurationFailureCode.BEHAVIORAL_VERIFICATION_FAILED,
            )
        if actions:
            return ConfigurationApplicationStatus.PARTIAL, ConfigurationFailureCode.NONE
        return ConfigurationApplicationStatus.SKIPPED, ConfigurationFailureCode.NONE

    @staticmethod
    def _failure(plan, code, *messages, context, deployment_id="", started):
        journal = journal_from_action_results(
            plan_id=plan.id,
            deployment_id=deployment_id,
            actions=list(plan.actions),
            results=[],
        )
        for message in messages:
            journal.mark_preflight_failure(message)
        return ServiceApplicationResult(
            service_plan_id=plan.id,
            service_semantic_hash=plan.semantic_hash,
            source_topology_hash=plan.source_topology_hash,
            source_configuration_hash=plan.source_configuration_hash,
            runtime_context=context,
            status=ConfigurationApplicationStatus.FAILED,
            failure_code=code,
            preflight_errors=list(messages),
            deployment_id=deployment_id,
            execution_journal=journal,
            dirty_state=journal.dirty_state,
            duration_ms=int((monotonic() - started) * 1000),
        )
