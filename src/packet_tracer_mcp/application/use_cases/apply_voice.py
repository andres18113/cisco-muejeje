"""Aplicación E7 con preflight, registro y verificación de llamadas frescas."""

from __future__ import annotations

from collections.abc import Sequence
from time import monotonic, time_ns
from typing import Protocol
from uuid import uuid4

from ...domain.enterprise.models.configuration_runtime import (
    ActionApplicationResult,
    ActionExecutionStatus,
    ConfigurationFailureCode,
    ConfigurationRuntimeContext,
    FieldVerificationStatus,
    RuntimeActionMutation,
    RuntimeConfigurationTarget,
)
from ...domain.enterprise.models.voice_plan import (
    CallExpectation,
    CallExpectationResult,
    VoiceAction,
    VoiceCapabilityDimension,
    VoiceCapabilityProfile,
    VoiceCapabilityStatus,
    VoicePlan,
    VoiceVerificationKind,
)
from ...domain.enterprise.models.voice_runtime import (
    CallState,
    CallVerificationResult,
    PhoneRegistrationResult,
    PhoneVoiceOutcome,
    RuntimeCallObservation,
    RuntimePhoneRegistration,
    VoiceApplicationResult,
)
from ...domain.enterprise.services.configuration_dependencies import (
    ConfigurationDependencyError,
    order_dependency_actions,
)


class VoiceRuntime(Protocol):
    def inventory(self) -> list[RuntimeConfigurationTarget]: ...

    def apply_actions(self, actions: Sequence[VoiceAction]) -> list[RuntimeActionMutation]: ...

    def observe_registration(self, expectation) -> RuntimePhoneRegistration: ...

    def verify_call(
        self, expectation: CallExpectation, call_attempt_id: str, started_ns: int,
    ) -> RuntimeCallObservation: ...


class VoiceApplicator:
    """Ejecuta sólo VoicePlan; nunca recompila E4, E5 ni E6."""

    def __init__(self, runtime: VoiceRuntime) -> None:
        self._runtime = runtime

    def apply(
        self,
        plan: VoicePlan,
        *,
        actual_source_topology_hash: str,
        actual_source_configuration_hash: str,
        foundational_statuses: dict[str, ActionExecutionStatus],
        actual_source_service_hash: str = "",
        capabilities: dict[str, VoiceCapabilityProfile] | None = None,
        runtime_context: ConfigurationRuntimeContext | None = None,
    ) -> VoiceApplicationResult:
        started = monotonic()
        context = runtime_context or ConfigurationRuntimeContext()
        if actual_source_topology_hash != plan.source_topology_hash:
            return self._failure(
                plan, ConfigurationFailureCode.SOURCE_TOPOLOGY_MISMATCH,
                "VoicePlan source hash does not match deployed E4.", context, started,
            )
        if actual_source_configuration_hash != plan.source_configuration_hash:
            return self._failure(
                plan, ConfigurationFailureCode.SOURCE_CONFIGURATION_MISMATCH,
                "VoicePlan source hash does not match applied E5.", context, started,
            )
        if plan.source_service_hash and actual_source_service_hash != plan.source_service_hash:
            return self._failure(
                plan, ConfigurationFailureCode.SOURCE_CONFIGURATION_MISMATCH,
                "VoicePlan service hash does not match applied E6.", context, started,
            )
        try:
            ordered = order_dependency_actions(plan.actions)
        except ConfigurationDependencyError as exc:
            return self._failure(
                plan, ConfigurationFailureCode.DEPENDENCY_BLOCKED, str(exc), context, started,
            )
        if [item.id for item in ordered] != [item.id for item in plan.actions]:
            return self._failure(
                plan, ConfigurationFailureCode.DEPENDENCY_BLOCKED,
                "VoicePlan actions are not in deterministic dependency order.", context, started,
            )
        missing = sorted(
            item.source_id for item in plan.foundational_requirements
            if foundational_statuses.get(item.source_id) is not ActionExecutionStatus.VERIFIED
        )
        if missing:
            return self._failure(
                plan, ConfigurationFailureCode.FOUNDATIONAL_CONFIGURATION_MISSING,
                "Voice foundations are not VERIFIED: " + ", ".join(missing), context, started,
            )
        try:
            inventory = {item.device_name: item for item in self._runtime.inventory()}
        except Exception as exc:
            return self._failure(
                plan, ConfigurationFailureCode.SESSION_FAILED,
                f"Voice runtime inventory failed: {exc}", context, started,
            )
        target_errors = []
        for control in plan.call_controls:
            target = inventory.get(control.host_device_name)
            if target is None:
                target_errors.append(f"Target {control.host_device_name} was not found.")
            elif target.model.casefold() != control.host_model.casefold():
                target_errors.append(
                    f"Target {control.host_device_name} model {target.model} does not match "
                    f"{control.host_model}."
                )
        for phone in plan.phone_assignments:
            target = inventory.get(phone.physical_device_name)
            if target is None:
                target_errors.append(f"Target {phone.physical_device_name} was not found.")
            elif target.model.casefold() != phone.model.casefold():
                target_errors.append(
                    f"Target {phone.physical_device_name} model {target.model} does not match "
                    f"{phone.model}."
                )
        if target_errors:
            return self._failure(
                plan, ConfigurationFailureCode.TARGET_NOT_FOUND,
                " ".join(sorted(target_errors)), context, started,
            )

        capabilities = capabilities or {}
        action_results = self._apply_actions(plan, capabilities)
        application_status = self._application_status(action_results)
        registrations = self._registrations(plan, action_results, capabilities)
        calls = self._calls(plan, registrations, capabilities)
        phones = self._phone_outcomes(plan, action_results, registrations, calls)
        status, failure_code = self._overall(application_status, phones, calls)
        return VoiceApplicationResult(
            voice_plan_id=plan.id, voice_semantic_hash=plan.semantic_hash,
            source_topology_hash=plan.source_topology_hash,
            source_configuration_hash=plan.source_configuration_hash,
            source_service_hash=plan.source_service_hash,
            runtime_context=context, status=status, application_status=application_status,
            failure_code=failure_code, action_results=action_results,
            registrations=registrations, calls=calls, phones=phones,
            duration_ms=int((monotonic() - started) * 1000),
        )

    def _apply_actions(self, plan, capabilities):
        results: dict[str, ActionApplicationResult] = {}
        for action in plan.actions:
            profile = capabilities.get(action.host_model)
            support = profile.status(action.required_capability) if profile else VoiceCapabilityStatus.UNKNOWN
            if support is VoiceCapabilityStatus.SUPPORTED:
                continue
            results[action.id] = ActionApplicationResult(
                action_id=action.id, status=ActionExecutionStatus.SKIPPED,
                failure_code=(
                    ConfigurationFailureCode.CAPABILITY_UNSUPPORTED
                    if support is VoiceCapabilityStatus.UNSUPPORTED
                    else ConfigurationFailureCode.CAPABILITY_UNKNOWN
                ),
                message=f"{action.host_model}:{action.required_capability.value} is {support.value}.",
            )
        pending = [item for item in plan.actions if item.id not in results]
        while pending:
            progress = False
            for action in list(pending):
                blocked = [
                    dependency for dependency in action.depends_on
                    if dependency in results
                    and results[dependency].status is not ActionExecutionStatus.APPLIED
                ]
                if blocked:
                    results[action.id] = ActionApplicationResult(
                        action_id=action.id, status=ActionExecutionStatus.DEPENDENCY_BLOCKED,
                        failure_code=ConfigurationFailureCode.DEPENDENCY_BLOCKED,
                        message="Blocked by: " + ", ".join(sorted(blocked)),
                    )
                    pending.remove(action)
                    progress = True
            ready = [
                item for item in pending
                if all(
                    dependency in results
                    and results[dependency].status is ActionExecutionStatus.APPLIED
                    for dependency in item.depends_on
                )
            ]
            if ready:
                first = ready[0]
                batch = [
                    item for item in ready
                    if item.phase == first.phase and item.call_control_id == first.call_control_id
                ]
                try:
                    mutations = {item.action_id: item for item in self._runtime.apply_actions(batch)}
                except Exception as exc:
                    mutations = {
                        item.id: RuntimeActionMutation(
                            action_id=item.id, applied=False,
                            failure_code=ConfigurationFailureCode.SESSION_FAILED,
                            message=str(exc),
                        ) for item in batch
                    }
                for item in batch:
                    mutation = mutations.get(item.id)
                    applied = bool(mutation and mutation.applied)
                    results[item.id] = ActionApplicationResult(
                        action_id=item.id,
                        status=ActionExecutionStatus.APPLIED if applied else ActionExecutionStatus.FAILED,
                        failure_code=(
                            ConfigurationFailureCode.NONE if applied
                            else mutation.failure_code if mutation else
                            ConfigurationFailureCode.CALL_CONTROL_APPLICATION_FAILED
                        ),
                        message=mutation.message if mutation else "Runtime returned no mutation.",
                        batch_id=mutation.batch_id if mutation else "",
                    )
                    pending.remove(item)
                progress = True
            if not progress:
                for item in pending:
                    results[item.id] = ActionApplicationResult(
                        action_id=item.id, status=ActionExecutionStatus.DEPENDENCY_BLOCKED,
                        failure_code=ConfigurationFailureCode.DEPENDENCY_BLOCKED,
                    )
                break
        return [results[item.id] for item in plan.actions]

    def _registrations(self, plan, actions, capabilities):
        action_results = {item.action_id: item for item in actions}
        controls = {item.id: item for item in plan.call_controls}
        results = []
        for expectation in (
            item for item in plan.verification_expectations
            if item.kind is VoiceVerificationKind.PHONE_REGISTRATION
        ):
            action = action_results[expectation.action_id]
            if action.status is not ActionExecutionStatus.APPLIED:
                results.append(PhoneRegistrationResult(
                    expectation_id=expectation.id, phone_id=expectation.phone_id,
                    extension=expectation.extension,
                    status=ActionExecutionStatus.DEPENDENCY_BLOCKED,
                    failure_code=ConfigurationFailureCode.DEPENDENCY_BLOCKED,
                    message=f"Binding action {action.action_id} is not applied.",
                ))
                continue
            control = controls[expectation.call_control_id]
            profile = capabilities.get(control.host_model)
            support = (
                profile.status(VoiceCapabilityDimension.PHONE_REGISTRATION)
                if profile else VoiceCapabilityStatus.UNKNOWN
            )
            if support is VoiceCapabilityStatus.UNOBSERVABLE:
                results.append(PhoneRegistrationResult(
                    expectation_id=expectation.id, phone_id=expectation.phone_id,
                    extension=expectation.extension, status=ActionExecutionStatus.PARTIAL,
                    direct_readback=FieldVerificationStatus.UNOBSERVABLE,
                    failure_code=ConfigurationFailureCode.PHONE_REGISTRATION_UNOBSERVABLE,
                    evidence_method="runtime_capability_matrix",
                    message="Direct phone registration is unobservable.",
                ))
                continue
            if support is not VoiceCapabilityStatus.SUPPORTED:
                results.append(PhoneRegistrationResult(
                    expectation_id=expectation.id, phone_id=expectation.phone_id,
                    extension=expectation.extension, status=ActionExecutionStatus.SKIPPED,
                    failure_code=(
                        ConfigurationFailureCode.CAPABILITY_UNSUPPORTED
                        if support is VoiceCapabilityStatus.UNSUPPORTED
                        else ConfigurationFailureCode.CAPABILITY_UNKNOWN
                    ), message=f"Phone registration is {support.value}.",
                ))
                continue
            try:
                observed = self._runtime.observe_registration(expectation)
                failure = (
                    ConfigurationFailureCode.NONE
                    if observed.status is ActionExecutionStatus.VERIFIED
                    else ConfigurationFailureCode.PHONE_REGISTRATION_TIMEOUT
                )
                results.append(PhoneRegistrationResult(
                    **observed.model_dump(), failure_code=failure,
                ))
            except Exception as exc:
                results.append(PhoneRegistrationResult(
                    expectation_id=expectation.id, phone_id=expectation.phone_id,
                    extension=expectation.extension, status=ActionExecutionStatus.FAILED,
                    failure_code=ConfigurationFailureCode.SESSION_FAILED, message=str(exc),
                ))
        return results

    def _calls(self, plan, registrations, capabilities):
        registration_by_phone = {item.phone_id: item for item in registrations}
        assignments = {item.phone_id: item for item in plan.phone_assignments}
        controls = {item.id: item for item in plan.call_controls}
        results = []
        for expectation in plan.call_expectations:
            source_registration = registration_by_phone.get(expectation.source_phone_id)
            target_registration = registration_by_phone.get(expectation.expected_target_phone_id)
            hard_block = (
                source_registration is None
                or source_registration.status in {
                    ActionExecutionStatus.FAILED, ActionExecutionStatus.DEPENDENCY_BLOCKED,
                }
                or expectation.expected_target_phone_id
                and (
                    target_registration is None
                    or target_registration.status in {
                        ActionExecutionStatus.FAILED, ActionExecutionStatus.DEPENDENCY_BLOCKED,
                    }
                )
            )
            if hard_block:
                results.append(CallVerificationResult(
                    call_expectation_id=expectation.id, call_attempt_id="",
                    source_phone_id=expectation.source_phone_id,
                    dialed_extension=expectation.dialed_extension,
                    expected_result=expectation.expected_result,
                    expected_target_phone_id=expectation.expected_target_phone_id,
                    status=ActionExecutionStatus.DEPENDENCY_BLOCKED,
                    failure_code=ConfigurationFailureCode.DEPENDENCY_BLOCKED,
                    message="A required phone did not reach a usable registration state.",
                ))
                continue
            assignment = assignments[expectation.source_phone_id]
            control = controls[assignment.call_control_id]
            profile = capabilities.get(control.host_model)
            initiation = (
                profile.status(VoiceCapabilityDimension.CALL_INITIATION)
                if profile else VoiceCapabilityStatus.UNKNOWN
            )
            readback = (
                profile.status(VoiceCapabilityDimension.CALL_STATE_READBACK)
                if profile else VoiceCapabilityStatus.UNKNOWN
            )
            if initiation is not VoiceCapabilityStatus.SUPPORTED or readback not in {
                VoiceCapabilityStatus.SUPPORTED, VoiceCapabilityStatus.UNOBSERVABLE,
            }:
                results.append(CallVerificationResult(
                    call_expectation_id=expectation.id, call_attempt_id="",
                    source_phone_id=expectation.source_phone_id,
                    dialed_extension=expectation.dialed_extension,
                    expected_result=expectation.expected_result,
                    expected_target_phone_id=expectation.expected_target_phone_id,
                    status=ActionExecutionStatus.SKIPPED,
                    failure_code=ConfigurationFailureCode.CAPABILITY_UNKNOWN,
                    message=f"Call initiation/readback is {initiation.value}/{readback.value}.",
                ))
                continue
            attempt_id = f"call-{uuid4().hex}"
            started_ns = time_ns()
            try:
                observed = self._runtime.verify_call(expectation, attempt_id, started_ns)
            except Exception as exc:
                results.append(CallVerificationResult(
                    call_expectation_id=expectation.id, call_attempt_id=attempt_id,
                    source_phone_id=expectation.source_phone_id,
                    dialed_extension=expectation.dialed_extension,
                    expected_result=expectation.expected_result,
                    expected_target_phone_id=expectation.expected_target_phone_id,
                    status=ActionExecutionStatus.FAILED,
                    failure_code=ConfigurationFailureCode.SESSION_FAILED, message=str(exc),
                ))
                continue
            fresh = bool(
                observed.fresh_evidence and observed.call_attempt_id == attempt_id
                and observed.observed_after_ns >= started_ns
            )
            connected_state = CallState.CONNECTED in observed.states
            expected_connected = expectation.expected_result is CallExpectationResult.ESTABLISHED
            behavior_matches = (
                observed.connected and connected_state if expected_connected
                else not observed.connected and not connected_state
            )
            if not fresh or not behavior_matches:
                status = ActionExecutionStatus.FAILED
                failure = ConfigurationFailureCode.CALL_SETUP_FAILED
            elif not observed.teardown_verified:
                status = ActionExecutionStatus.PARTIAL
                failure = ConfigurationFailureCode.CALL_TEARDOWN_FAILED
            else:
                status = ActionExecutionStatus.VERIFIED
                failure = ConfigurationFailureCode.NONE
            results.append(CallVerificationResult(
                **observed.model_dump(exclude={"status", "fresh_evidence"}),
                fresh_evidence=fresh, status=status,
                expected_result=expectation.expected_result,
                expected_target_phone_id=expectation.expected_target_phone_id,
                failure_code=failure,
            ))
        return results

    @staticmethod
    def _phone_outcomes(plan, actions, registrations, calls):
        action_results = {item.action_id: item for item in actions}
        registration_by_phone = {item.phone_id: item for item in registrations}
        outcomes = []
        for assignment in plan.phone_assignments:
            registration = registration_by_phone.get(assignment.phone_id)
            relevant = [
                item for item in calls
                if item.expected_result is CallExpectationResult.ESTABLISHED
                and (item.source_phone_id == assignment.phone_id
                     or item.expected_target_phone_id == assignment.phone_id)
            ]
            call_status = (
                ActionExecutionStatus.VERIFIED
                if any(item.status is ActionExecutionStatus.VERIFIED for item in relevant)
                else ActionExecutionStatus.FAILED
                if any(item.status is ActionExecutionStatus.FAILED for item in relevant)
                else ActionExecutionStatus.UNKNOWN
            )
            usability = (
                ActionExecutionStatus.VERIFIED
                if (registration and registration.status is ActionExecutionStatus.VERIFIED)
                or call_status is ActionExecutionStatus.VERIFIED
                else ActionExecutionStatus.UNKNOWN
            )
            outcomes.append(PhoneVoiceOutcome(
                phone_id=assignment.phone_id, extension=assignment.extension,
                application_status=action_results[assignment.binding_action_id].status,
                registration_status=registration.status if registration else ActionExecutionStatus.UNKNOWN,
                direct_registration_readback=(
                    registration.direct_readback if registration else FieldVerificationStatus.UNKNOWN
                ),
                call_behavior_status=call_status, usability_status=usability,
            ))
        return outcomes

    @staticmethod
    def _application_status(results):
        if any(item.status is ActionExecutionStatus.FAILED for item in results):
            return ActionExecutionStatus.FAILED
        if any(item.status is not ActionExecutionStatus.APPLIED for item in results):
            return ActionExecutionStatus.PARTIAL
        return ActionExecutionStatus.APPLIED

    @staticmethod
    def _overall(application, phones, calls):
        if application is ActionExecutionStatus.FAILED:
            return ActionExecutionStatus.FAILED, ConfigurationFailureCode.CALL_CONTROL_APPLICATION_FAILED
        if calls and all(item.status is ActionExecutionStatus.VERIFIED for item in calls) and all(
            item.usability_status is ActionExecutionStatus.VERIFIED for item in phones
        ):
            return ActionExecutionStatus.VERIFIED, ConfigurationFailureCode.NONE
        if any(item.status is ActionExecutionStatus.FAILED for item in calls):
            return ActionExecutionStatus.FAILED, ConfigurationFailureCode.BEHAVIORAL_VERIFICATION_FAILED
        return ActionExecutionStatus.PARTIAL, ConfigurationFailureCode.NONE

    @staticmethod
    def _failure(plan, code, message, context, started):
        return VoiceApplicationResult(
            voice_plan_id=plan.id, voice_semantic_hash=plan.semantic_hash,
            source_topology_hash=plan.source_topology_hash,
            source_configuration_hash=plan.source_configuration_hash,
            source_service_hash=plan.source_service_hash,
            runtime_context=context, status=ActionExecutionStatus.FAILED,
            failure_code=code, preflight_errors=[message],
            duration_ms=int((monotonic() - started) * 1000),
        )
