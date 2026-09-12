"""Compatibility JSON is materialized only when the runner publishes evidence."""

from __future__ import annotations

import collections
from dataclasses import asdict

from ...application.cp_scale_live.contracts import (
    CP_SCALE_REALTIME_FIELDS,
    CPScaleLiveStageResult,
    CPScaleRealtimeObservation,
    CPScaleRealtimeState,
    CPScaleVoiceStageResult,
)
from ...application.use_cases.compose_cp_scale_canonical import CPScaleCanonicalStageProjection
from ...domain.enterprise.models.configuration import VerificationKind
from ...domain.enterprise.models.configuration_runtime import ActionExecutionStatus
from ...domain.models.typed_ping import TypedPingResult
from ...infrastructure.execution.forwarding_probe import forwarding_probe_evidence
from ...shared.utils import serialize_typed_ping_evidence


def realtime_state_evidence(state: CPScaleRealtimeState | None) -> dict[str, object] | None:
    if state is None or type(state) is not CPScaleRealtimeState:
        return None
    present = state.present if type(state.present) is tuple else ()
    return {
        name: getattr(state, name)
        for name in CP_SCALE_REALTIME_FIELDS
        if name in present
    }


def _trunk_vlan_traversal_evidence(plan, result) -> list[dict[str, object]]:
    """Project typed trunk verification into human-auditable path evidence."""
    expectations = {
        item.id: item for item in plan.verification_expectations
        if item.kind is VerificationKind.TRUNK
    }
    evidence: list[dict[str, object]] = []
    for item in result.verification_results:
        expectation = expectations.get(item.expectation_id)
        if expectation is None:
            continue
        evidence.append({
            "expectation_id": item.expectation_id,
            "device_id": expectation.device_id,
            "device_name": expectation.device_name,
            "interface": str(expectation.expected.get("interface", "")),
            "expected_vlans": sorted({
                int(vlan)
                for vlan in expectation.expected.get("allowed_vlans", [])
            }),
            "status": item.status.value,
            "evidence_method": item.evidence_method,
            "fresh_evidence": item.fresh_evidence,
            "fields": {
                name: status.value for name, status in sorted(item.fields.items())
            },
            "message": item.message,
        })
    return evidence



def voice_stage_evidence(
    projection: CPScaleCanonicalStageProjection, voice: CPScaleVoiceStageResult,
) -> dict[str, object]:
    """Preserve legacy report shape; error authority belongs to VoiceStage."""
    if not voice.staged:
        return {"staged": False, "reason": voice.reason}
    if voice.result is None:
        return {"staged": True, "error": voice.error}
    plan = projection.voice
    result = voice.result
    evidence: dict[str, object] = {
        "staged": True,
        "result": result.model_dump(mode="json"),
        "phones": len(plan.phone_assignments),
        "actions": len(plan.actions),
        "mutation_actions": len(result.mutation_action_ids),
        "retained_actions": len(result.retained_action_ids),
        "runtime_diagnostics": (
            voice.runtime_diagnostics.evidence or ({"error": voice.runtime_diagnostics.error} if voice.runtime_diagnostics.error else {})
            if voice.runtime_diagnostics else {}
        ),
    }

    refused = sorted(
        f"{item.action_id}: {item.message}" for item in result.action_results
        if item.status is ActionExecutionStatus.FAILED
    )
    if result.preflight_errors:
        evidence["error"] = voice.error
        return evidence
    if refused:
        evidence["error"] = voice.error
        return evidence

    addressing = collections.Counter(
        item.addressing_status.value for item in result.registrations
    )
    registration = collections.Counter(
        item.status.value for item in result.registrations
    )
    expected_call_ids = collections.Counter(
        item.id for item in getattr(plan, "call_expectations", [])
    )
    call_results = list(getattr(result, "calls", []))
    observed_call_ids = collections.Counter(
        item.call_expectation_id for item in call_results
    )
    calls = collections.Counter(item.status.value for item in call_results)
    evidence["addressing_by_status"] = dict(sorted(addressing.items()))
    evidence["registration_by_status"] = dict(sorted(registration.items()))
    evidence["calls_by_status"] = dict(sorted(calls.items()))
    if expected_call_ids != observed_call_ids:
        evidence["error"] = voice.error
        return evidence
    failed_calls = [
        item.call_expectation_id
        for item in call_results
        if item.status is ActionExecutionStatus.FAILED
    ]
    if failed_calls:
        evidence["error"] = voice.error
        return evidence
    # The voice path, one link at a time. A phone that never built its voice SVI
    # and one that built it and got no lease are different failures, and a
    # registration table that was truncated is not a statement about either.
    evidence["voice_interface_present"] = sum(
        1 for item in result.registrations if item.endpoint_interface_present
    )
    # Present is not the same as readable. A voice SVI that exposes no address
    # getter answers "" exactly like one that answered and holds no lease, and
    # only one of those is a statement about DHCP.
    evidence["voice_interface_address_channel"] = sum(
        1 for item in result.registrations if item.endpoint_address_channel
    )
    evidence["voice_interface_addressed"] = sum(
        1 for item in result.registrations
        if item.endpoint_address_channel and item.endpoint_ipv4
    )
    # And whether the phone was ever asked to acquire. A voice SVI with DHCP
    # off did not fail to lease; nothing solicited on it.
    # And the phone itself, which PT does not necessarily answer for in the
    # same place as its ports.
    evidence["voice_device_addressed"] = sorted(
        f"{item.phone_id}={item.device_ipv4}"
        for item in result.registrations if item.device_ipv4
    )
    evidence["voice_device_dhcp"] = dict(sorted(
        collections.Counter(
            "unreadable" if item.device_dhcp_enabled is None
            else ("enabled" if item.device_dhcp_enabled else "disabled")
            for item in result.registrations
        ).items()
    ))
    evidence["voice_interface_dhcp"] = dict(sorted(
        collections.Counter(
            "unreadable" if item.endpoint_dhcp_enabled is None
            else ("enabled" if item.endpoint_dhcp_enabled else "disabled")
            for item in result.registrations
        ).items()
    ))
    evidence["registration_evidence_method"] = dict(sorted(
        collections.Counter(
            item.evidence_method for item in result.registrations
        ).items()
    ))
    evidence["contradicted_addressing"] = sorted(
        f"{item.phone_id}: {item.addressing_message}"
        for item in result.registrations
        if item.addressing_status is ActionExecutionStatus.FAILED
    )
    evidence["addressed_phones"] = sorted(
        f"{item.phone_id}={item.call_control_ipv4 or item.endpoint_ipv4}"
        for item in result.registrations
        if item.addressing_status in {
            ActionExecutionStatus.VERIFIED, ActionExecutionStatus.PARTIAL,
        }
    )
    if evidence["contradicted_addressing"]:
        evidence["error"] = voice.error
        return evidence
    # A registration this build cannot observe is bounded evidence, not a
    # failure; a registration it can observe and reports UNREGISTERED is a
    # contradiction of a claim the plan made.
    evidence["contradicted_registration"] = sorted(
        f"{item.phone_id}: {item.message}" for item in result.registrations
        if item.status is ActionExecutionStatus.FAILED
    )
    if evidence["contradicted_registration"]:
        evidence["error"] = voice.error
        return evidence
    evidence["error"] = voice.error
    return evidence



def _forwarding_attempt_evidence(attempts: tuple[TypedPingResult, ...]) -> dict[str, object]:
    if attempts:
        return serialize_typed_ping_evidence(attempts[-1])
    # A missing slot is not a synthetic ping. Preserve the stable evidence keys
    # while explicitly withholding freshness, attribution and any measurement.
    return {
        "reachable": False, "fresh_output_observed": False, "window_strategy": "none",
        "failure_reason": "No typed forwarding attempt was acquired.", "attempts": 0,
        "statistics": "", "dispatched_destination": "", "observed_device_name": "",
        "device_identity_provenance": "not_observed", "device_identity_evidence": "none",
    }


def stage_result_evidence(result: CPScaleLiveStageResult) -> dict[str, object]:
    projection = result.projection
    report = result.report
    scope = report.scope
    if scope is None:
        return {"stage": result.stage.value}
    configuration_mutation_ids = scope.configuration
    retained_configuration_ids = scope.retained_configuration
    control_plane_mutation_ids = scope.control_plane
    retained_control_plane_ids = scope.retained_control_plane
    voice_mutation_ids = scope.voice
    retained_voice_ids = scope.retained_voice
    site_forwarding_checks = report.site_forwarding_checks
    user_forwarding_checks = report.user_forwarding_checks
    evidence = {
        "stage": projection.stage.value,
        "plan": {
            "topology_hash": projection.topology.physical_identity_hash,
            "configuration_hash": projection.configuration.semantic_hash,
            "control_plane_hash": projection.control_plane.semantic_hash,
            "devices": len(projection.topology.devices),
            "modules": len(projection.topology.modules),
            "links": len(projection.topology.links),
            "configuration_actions": len(projection.configuration.actions),
            "configuration_mutation_actions": len(
                configuration_mutation_ids
            ),
            "configuration_retained_actions": len(retained_configuration_ids),
            "configuration_mutation_action_ids": list(
                configuration_mutation_ids
            ),
            "configuration_retained_action_ids": sorted(
                retained_configuration_ids
            ),
            "voice_actions": (
                len(projection.voice.actions) if projection.voice is not None else 0
            ),
            "voice_mutation_actions": len(voice_mutation_ids),
            "voice_retained_actions": len(retained_voice_ids),
            "voice_mutation_action_ids": list(voice_mutation_ids),
            "voice_retained_action_ids": sorted(retained_voice_ids),
            "voice_phones": (
                len(projection.voice.phone_assignments)
                if projection.voice is not None else 0
            ),
            "control_plane_actions": len(projection.control_plane.actions),
            "control_plane_mutation_actions": len(
                control_plane_mutation_ids
            ),
            "control_plane_retained_actions": len(
                retained_control_plane_ids
            ),
            "control_plane_mutation_action_ids": list(
                control_plane_mutation_ids
            ),
            "control_plane_retained_action_ids": sorted(
                retained_control_plane_ids
            ),
            "verification_expectations": len(
                projection.control_plane.verification_expectations
            ),
            "branch_forwarding_checks": [
                asdict(item) for item in site_forwarding_checks
            ],
            "branch_user_forwarding_checks": [
                asdict(item) for item in user_forwarding_checks
            ],
        },
        "physical": result.deployment.model_dump(mode="json"),
        "physical_delta": result.delta_deployment.model_dump(mode="json") if result.delta_deployment is not None else None,
        "network_state_timeline": [],
        "voice_lifecycle": [
            dict(asdict(item), recorded_at=item.recorded_at.isoformat()) for item in report.lifecycle
        ],
    }
    if result.orientation is not None:
        evidence["serial_orientation"] = result.orientation.model_dump(mode="json")
    if result.configuration_attempts:
        evidence["configuration_attempts"] = [item.model_dump(mode="json") for item in result.configuration_attempts]
        evidence["trunk_vlan_traversal_attempts"] = [
            _trunk_vlan_traversal_evidence(projection.configuration, item) for item in result.configuration_attempts
        ]
        evidence["trunk_vlan_traversal"] = evidence["trunk_vlan_traversal_attempts"][-1]
    if report.configuration is not None:
        configured = report.configuration
        evidence["configuration_contradictions"] = list(configured.contradictions)
        if configured.reread_scope is not None:
            reread = configured.reread_scope
            evidence["configuration_reread_scope"] = {
                "claim": "CONFIGURATION_REREAD_MUTATION_SCOPE_EMPTY", "verified": reread.verified,
            }
            if reread.error:
                evidence["configuration_reread_scope"]["error"] = reread.error
            else:
                evidence["configuration_reread_scope"].update({
                    "mutation_action_ids": list(reread.mutation_action_ids),
                    "retained_action_ids": list(reread.retained_action_ids),
                    "retained_deferred_voice_action_ids": list(reread.retained_deferred_voice_action_ids),
                })
        if configured.acceptance_error is not None:
            evidence["configuration"] = result.configuration.model_dump(mode="json")
            evidence["configuration_acceptance_error"] = configured.acceptance_error
    for observation in result.required_observations:
        if isinstance(observation, CPScaleRealtimeObservation):
            continue
        if observation.kind == "network_state":
            evidence["network_state_timeline"].append(observation.evidence)
        elif observation.kind == "serial_interfaces":
            evidence["serial_interfaces"] = observation.evidence["readings"]
        elif observation.kind == "dhcp_server_bindings":
            if not observation.error:
                evidence["dhcp_server_bindings"] = observation.evidence["bindings"]
        elif observation.kind in {"stp_realtime_before_voice", "stp_realtime_after_voice", "dhcp_voice_exchange"}:
            evidence[observation.kind] = observation.evidence
    if report.realtime is not None:
        window = report.realtime
        evidence["voice_realtime_continuity"] = {
            "window": "NORMAL_WINDOW", "mode_required": "realtime",
            "proves": "Both boundaries of the authoritative window were observed in Realtime. It does NOT prove the mode was never toggled between the two reads.",
            "before": realtime_state_evidence(window.before.state),
            "after": realtime_state_evidence(window.after.state) if window.after is not None else None,
            "verified": window.verified, "failure_reason": window.failure_reason,
        }
    if report.voice is not None:
        evidence["voice"] = voice_stage_evidence(projection, report.voice)
    if report.canonical_voice is not None:
        evidence["canonical_voice_verification"] = report.canonical_voice.model_dump(mode="json")
    if report.canonical_voice_error:
        evidence["canonical_voice_verification_error"] = report.canonical_voice_error
    if result.secondary_failures:
        evidence["secondary_failures"] = [asdict(item) for item in result.secondary_failures]
    for diagnostic in result.diagnostics:
        evidence["post_failure_simulation"] = diagnostic.evidence or {
            "status": "FAILED", "failure_reason": diagnostic.error,
        }
    if result.control_plane is not None:
        evidence["control_plane"] = result.control_plane.model_dump(mode="json")
    if result.replay_audit is not None:
        evidence["mutation_replay_audit"] = result.replay_audit.compact_summary()
    if report.forwarding is not None:
        forwarded = report.forwarding
        evidence["core_forwarding"] = {
            item.source_device_name: _forwarding_attempt_evidence(item.attempts) for item in forwarded.core
        }
        evidence["core_forwarding_verified"] = forwarded.core_verified
        if forwarded.site_verified is not None:
            evidence["site_forwarding"] = [
                {
                    "check": asdict(item.check),
                    "result": _forwarding_attempt_evidence(item.attempts),
                    "attempts": [
                        serialize_typed_ping_evidence(attempt)
                        for attempt in item.attempts
                    ],
                    "resolved_binding": (
                        asdict(item.destination_binding)
                        if getattr(item, "destination_binding", None) else None
                    ),
                    "binding_probes": [
                        forwarding_probe_evidence(probe)
                        for probe in getattr(item, "probes", ())
                    ],
                    "verified": item.verified and bool(item.attempts),
                }
                for item in forwarded.site
            ]
            evidence["site_forwarding_verified"] = forwarded.site_verified
            evidence["site_forwarding_first_failure"] = forwarded.first_failure
        if forwarded.user_verified is not None:
            evidence["user_forwarding"] = [
                {
                    "check": asdict(item.check),
                    "status": item.status.value,
                    "attempts": [
                        serialize_typed_ping_evidence(attempt)
                        for attempt in item.attempts
                    ],
                    "source_binding": (
                        asdict(item.source_binding) if item.source_binding else None
                    ),
                    "destination_binding": (
                        asdict(item.destination_binding)
                        if item.destination_binding else None
                    ),
                    "binding_probes": [
                        forwarding_probe_evidence(probe) for probe in item.probes
                    ],
                    "verified": item.verified and bool(item.attempts),
                    "error": item.error,
                }
                for item in forwarded.user
            ]
            evidence["user_forwarding_verified"] = forwarded.user_verified
            evidence["user_forwarding_first_failure"] = (
                forwarded.user_first_failure
            )
    if report.workspace_first is not None:
        evidence["workspace_first"] = report.workspace_first.compact_summary()
        evidence["workspace_second"] = report.workspace_second.compact_summary() if report.workspace_second is not None else None
        evidence["workspace_verified_twice"] = report.workspace_verified
    if result.outcome == "verified":
        evidence["verified"] = True
        evidence["verification_scope"] = "VERIFIED_BOUNDED_RETAINED"
    return evidence
