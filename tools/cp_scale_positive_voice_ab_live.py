"""Governed LIVE for the positive disposable Voice slice (A side of the A/B).

Every adapter here maps a production runtime onto the qualifier's protocol. No
adapter invents a mutation: the reads reuse the same `verify` comparison and the
same registered operational queries the canonical run uses, and the writes are
the same typed actions.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

GOVERNED_ROOT = Path(__file__).resolve().parents[1]
if str(GOVERNED_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(GOVERNED_ROOT / "src"))

import packet_tracer_mcp  # noqa: E402

from packet_tracer_mcp.application.use_cases.qualify_cp_scale_live import (  # noqa: E402
    read_git_repository_state,
)
from packet_tracer_mcp.application.use_cases.qualify_positive_voice_slice import (  # noqa: E402
    DATA_VLAN_ID,
    ROUTER_VOICE_SUBINTERFACE,
    STP_FAILURE_COMPLETENESS,
    STP_FAILURE_EXECUTION,
    STP_FAILURE_FRESHNESS,
    STP_FAILURE_IDENTITY,
    STP_FAILURE_PARSING,
    STP_FAILURE_QUERY_SESSION,
    VOICE_VLAN_ID,
    PositiveVoiceSliceQualifier,
    StpReadObservation,
)
from packet_tracer_mcp.domain.enterprise.models.configuration import (  # noqa: E402
    VerificationExpectation,
    VerificationKind,
)
from packet_tracer_mcp.domain.enterprise.models.physical_deployment import (  # noqa: E402
    physical_workspace_restoration_matches,
)
from packet_tracer_mcp.infrastructure.execution.configuration_runtime import (  # noqa: E402
    PacketTracerConfigurationRuntime,
)
from packet_tracer_mcp.infrastructure.execution.enterprise_configuration_runtime import (  # noqa: E402
    PacketTracerEnterpriseConfigurationRuntime,
)
from packet_tracer_mcp.infrastructure.execution.enterprise_control_plane_runtime import (  # noqa: E402
    PacketTracerEnterpriseControlPlaneRuntime,
)
from packet_tracer_mcp.infrastructure.execution.enterprise_voice_runtime import (  # noqa: E402
    PacketTracerEnterpriseVoiceRuntime,
)
from packet_tracer_mcp.infrastructure.execution.ios_terminal import (  # noqa: E402
    ControlledIosExecutor,
    DeviceIdentityProvenance,
    OperationalQueryId,
    StpQueryClassification,
    classify_show_spanning_tree,
    parse_show_ip_dhcp_binding,
    parse_show_ip_interface,
    parse_show_ip_interface_brief,
    parse_show_spanning_tree,
)
from packet_tracer_mcp.infrastructure.execution.import_isolation_preflight import (  # noqa: E402
    ImportIsolationPreflight,
)
from packet_tracer_mcp.infrastructure.execution.live_environment_preflight import (  # noqa: E402
    packet_tracer_process_error,
)
from packet_tracer_mcp.infrastructure.execution.live_bridge import (  # noqa: E402
    PacketTracerHttpTransport,
)
from packet_tracer_mcp.infrastructure.execution.packet_tracer_physical_runtime import (  # noqa: E402
    PacketTracerPhysicalTopologyRuntime,
)
from packet_tracer_mcp.infrastructure.execution.simulation_trace_runtime import (  # noqa: E402
    SimulationTraceRuntime,
)
from packet_tracer_mcp.shared.utils import same_interface_name  # noqa: E402

EVIDENCE_PATH = GOVERNED_ROOT / "data" / "cp-scale" / "positive-voice-ab.json"
ROUTER_MODEL = "2811"
SWITCH_MODEL = "3560-24PS"
PHONE_MODEL = "7960"
EXPECTED_BRANCH = "feature/runtime-ripv2"
EXPECTED_UPSTREAM = "personal/feature/runtime-ripv2"

#: A value that can never equal a real VLAN id, so a FAILED field reads as
#: CONTRADICTED without inventing the number that was actually observed.
_CONTRADICTED_VLAN = -1


def _git_output(*arguments: str) -> str:
    return subprocess.run(
        ["git", *arguments],
        cwd=GOVERNED_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _packet_tracer_processes() -> list[dict[str, object]]:
    command = (
        "Get-Process | Where-Object { $_.ProcessName -like 'PacketTracer*' } | "
        "ForEach-Object { [PSCustomObject]@{ "
        "ProcessName=$_.ProcessName; Id=$_.Id; "
        "MainWindowHandle=$_.MainWindowHandle; "
        "ProductVersion=$_.MainModule.FileVersionInfo.ProductVersion; "
        "FileVersion=$_.MainModule.FileVersionInfo.FileVersion; "
        "Path=$_.MainModule.FileName } } | ConvertTo-Json -Compress"
    )
    completed = subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command", command],
        check=True,
        capture_output=True,
        text=True,
    )
    raw = completed.stdout.strip()
    if not raw:
        return []
    parsed = json.loads(raw)
    return parsed if isinstance(parsed, list) else [parsed]


def _hard_stop(message: str, preflight: dict[str, object]) -> int:
    print(json.dumps({"hard_stop": message, "preflight": preflight}))
    return 2


class _ReadPort:
    __slots__ = ("data_vlan_id", "voice_vlan_id")

    def __init__(self, data_vlan_id, voice_vlan_id):
        self.data_vlan_id = data_vlan_id
        self.voice_vlan_id = voice_vlan_id


def _table_readable(show) -> bool:
    """The three dimensions a registered operational read has to establish.

    EXECUTED is only the terminal answering.  FRESH is this capture being of
    this moment, and COMPLETE is it being the whole logical read rather than
    the first page of one.  Parsing a table that fails either of the last two
    turns a property of the READ into a property of the network: an STP row
    that never got printed reads ABSENT, and a binding table that stopped at a
    pager reads as zero bindings.  Both are discriminants of this A/B, so both
    have to come from a read that established all three.
    """
    return bool(
        getattr(show, "executed", False)
        and getattr(show, "fresh_output_observed", False)
        and getattr(show, "output_complete", False)
    )


def _authoritative_stp_readable(show) -> bool:
    """The RUN10 mutation gate also requires unique source attribution."""
    return bool(
        _table_readable(show)
        and getattr(show, "device_identity_provenance", "")
        == DeviceIdentityProvenance.CONFIRMED_UNIQUE.value
    )


def _field_text(value) -> str:
    return str(getattr(value, "value", value) or "")


def _bounded_stp_failure_reason(
    show, dimensions: tuple[str, ...], query_classification,
) -> str:
    """Keep only the metadata that explains why this one read was rejected."""
    details: list[str] = []
    supplied = " ".join(str(getattr(show, "failure_reason", "") or "").split())
    if supplied:
        details.append(supplied)
    if STP_FAILURE_EXECUTION in dimensions:
        details.append(
            "session=" + _field_text(getattr(show, "session_state", ""))
        )
        details.append(
            "dispatch=" + _field_text(
                getattr(show, "dispatch_classification", "")
            )
        )
        attempts = int(getattr(show, "dispatch_attempts", 0) or 0)
        if attempts > 1:
            details.append(f"dispatch_attempts={attempts}")
    if STP_FAILURE_FRESHNESS in dimensions:
        details.append(
            "fresh_output_observed=false; window_strategy="
            + str(getattr(show, "window_strategy", "") or "none")
        )
    if STP_FAILURE_COMPLETENESS in dimensions:
        details.append(
            "output_complete=false; pager="
            + str(getattr(show, "pager_continuation", "") or "unknown")
            + "; pages="
            + str(getattr(show, "pager_pages_captured", 0) or 0)
        )
    if STP_FAILURE_IDENTITY in dimensions:
        identity = str(
            getattr(show, "device_identity_provenance", "") or "not_observed"
        )
        observed = str(getattr(show, "observed_device_name", "") or "")
        evidence = str(getattr(show, "device_identity_evidence", "") or "")
        detail = f"identity={identity}"
        if observed:
            detail += f"; observed_device={observed}"
        if evidence:
            detail += f"; evidence={evidence}"
        details.append(detail)
    if query_classification is not None and (
        STP_FAILURE_PARSING in dimensions
        or STP_FAILURE_QUERY_SESSION in dimensions
    ):
        details.append(
            "query_classification=" + _field_text(query_classification)
        )
    return "; ".join(item for item in details if item)[:240]


def _field_to_vlan(status_name: str, expected: int):
    """VERIFIED keeps the expected value; FAILED contradicts; anything else is
    unread.  The comparison itself already happened inside the runtime."""
    text = str(status_name or "").upper()
    if "VERIFIED" in text:
        return expected
    if "FAILED" in text:
        return _CONTRADICTED_VLAN
    return None


class _ConfigurationAdapter:
    """Applies typed configuration and reads back through production paths."""

    def __init__(self, enterprise, ios):
        self._enterprise = enterprise
        self._ios = ios
        #: Kept ONLY for the boundary case below, never for the happy path.
        self.pool_boundary_captures: list = []

    def apply_actions(self, actions):
        return self._enterprise.apply_actions(actions)

    def read_access_port(
        self, device_name: str, interface: str, expected_access_vlan: int,
    ):
        expectation = VerificationExpectation(
            id=f"voiceab/verify/{interface}",
            action_id="voiceab/access",
            kind=VerificationKind.ACCESS_PORT,
            device_id="voiceab/sw",
            device_name=device_name,
            expected={
                "interface": interface,
                # The paired A/B judges each port against ITS OWN intent: the
                # control port against the data VLAN, the intervention port
                # against the voice VLAN.  Comparing both against the data
                # VLAN would manufacture a contradiction on the intervention
                # half of a mapping the switch applied exactly as asked.
                "vlan_id": expected_access_vlan,
                "voice_vlan_id": VOICE_VLAN_ID,
            },
        )
        results = self._enterprise.verify([expectation])
        if not results:
            return None
        fields = getattr(results[0], "fields", {}) or {}
        return _ReadPort(
            _field_to_vlan(fields.get("vlan_id"), expected_access_vlan),
            _field_to_vlan(fields.get("voice_vlan_id"), VOICE_VLAN_ID),
        )

    def read_spanning_tree(self, device_name: str):
        """None means the table was never read; it never means no rows.

        The qualifier turns None into UNOBSERVABLE and a parsed table with no
        phone row into ABSENT, and those are different answers to the causal
        question.  Only a read that was fresh and complete may produce either.
        """
        observation = self.read_spanning_tree_observation(device_name)
        return observation.instances if observation.authoritative else None

    def read_spanning_tree_observation(
        self, device_name: str,
    ) -> StpReadObservation:
        """Parse and retain authority from one SHOW_SPANNING_TREE result."""
        show = self._ios.execute(
            device_name, OperationalQueryId.SHOW_SPANNING_TREE,
        )
        executed = bool(getattr(show, "executed", False))
        fresh = bool(getattr(show, "fresh_output_observed", False))
        complete = bool(getattr(show, "output_complete", False))
        identity = str(
            getattr(show, "device_identity_provenance", "") or ""
        )
        dimensions: list[str] = []
        if not executed:
            dimensions.append(STP_FAILURE_EXECUTION)
        if not fresh:
            dimensions.append(STP_FAILURE_FRESHNESS)
        if not complete:
            dimensions.append(STP_FAILURE_COMPLETENESS)
        if identity != DeviceIdentityProvenance.CONFIRMED_UNIQUE.value:
            dimensions.append(STP_FAILURE_IDENTITY)

        instances = None
        query_classification = None
        if not dimensions:
            query_classification = classify_show_spanning_tree(
                show.output, executed=executed,
            )
            if query_classification in {
                StpQueryClassification.INVALID_COMMAND,
                StpQueryClassification.UNIMPLEMENTED,
                StpQueryClassification.QUERY_TIMEOUT,
            }:
                dimensions.append(STP_FAILURE_QUERY_SESSION)
            elif query_classification is StpQueryClassification.PARSER_UNAVAILABLE:
                dimensions.append(STP_FAILURE_PARSING)
            else:
                instances = parse_show_spanning_tree(show.output)

        failure_dimensions = tuple(dimensions)
        return StpReadObservation(
            instances=instances,
            executed=executed,
            fresh=fresh,
            complete=complete,
            identity_provenance=identity,
            failure_reason=_bounded_stp_failure_reason(
                show, failure_dimensions, query_classification,
            ),
            duration_ms=int(getattr(show, "duration_ms", 0) or 0),
            failure_dimensions=failure_dimensions,
        )

    def read_dhcp_bindings(self, device_name: str):
        """Same gate: an incomplete binding table is not zero bindings."""
        show = self._ios.execute(
            device_name, OperationalQueryId.SHOW_IP_DHCP_BINDING,
        )
        if not _table_readable(show):
            return None
        return parse_show_ip_dhcp_binding(show.output)

    def read_dhcp_pool(
        self, device_name: str, pool_name: str, lease_start: str, lease_end: str,
    ):
        """The measured pool table, judged by the production readback.

        If it comes back with nothing established -- an unread, incomplete,
        wrongly attributed or unparsable table -- the exact text that defeated
        it is captured once and archived.  Absence is never inferred from that,
        and keeping the boundary means the next parser fix does not cost
        another LIVE.
        """
        observed = self._enterprise.read_dhcp_pool(
            device_name, pool_name, lease_start, lease_end,
        )
        if getattr(observed, "pool_present", None) is None:
            show = self._ios.execute(
                device_name, OperationalQueryId.SHOW_IP_DHCP_POOL,
            )
            self.pool_boundary_captures.append({
                "device_name": device_name,
                "requested_pool_name": pool_name,
                "failure_reason": getattr(observed, "failure_reason", ""),
                "executed": getattr(show, "executed", False),
                "fresh_output_observed": getattr(
                    show, "fresh_output_observed", False,
                ),
                "output_complete": getattr(show, "output_complete", False),
                "device_identity_provenance": getattr(
                    show, "device_identity_provenance", "",
                ),
                "output": getattr(show, "output", ""),
            })
        return observed

    def read_trunk(self, device_name: str, interface: str):
        """The existing typed trunk readback, unchanged.

        It publishes the native VLAN and the allowed, active and forwarding
        sections as four independent answers, plus the freshness and
        completeness of the capture they came from.  Nothing is added here.
        """
        return self._enterprise.read_trunk(device_name, interface)

    def read_interface_addresses(self, device_name: str):
        """Router L3 state through two REGISTERED reads, or nothing at all.

        `show ip interface brief` is the table; if it is unreadable this
        returns None and every router dimension stays UNOBSERVABLE.  If it IS
        readable but does not list the voice subinterface, the bounded
        per-interface `show ip interface <sub>` is asked before the absence is
        allowed to stand -- and if THAT read is unreadable, this still returns
        None.  A build that simply does not print subinterfaces in the brief
        table must never be published as a router that lacks one.
        """
        show = self._ios.execute(
            device_name, OperationalQueryId.SHOW_IP_INTERFACE_BRIEF,
        )
        if not _table_readable(show):
            return None
        rows = parse_show_ip_interface_brief(show.output)
        if any(
            same_interface_name(item.interface, ROUTER_VOICE_SUBINTERFACE)
            for item in rows
        ):
            return rows
        scoped = self._ios.execute(
            device_name, OperationalQueryId.SHOW_IP_INTERFACE,
            interface=ROUTER_VOICE_SUBINTERFACE,
        )
        if not _table_readable(scoped):
            return None
        row = parse_show_ip_interface(scoped.output)
        return rows + [row] if row is not None else rows


class _ControlPlaneAdapter:
    """The typed control-plane runtime, exposed as the one call the slice makes.

    Deliberately narrow: the intervention applies edge ports and nothing else,
    so nothing here can reach the failure-scenario or verification surfaces the
    canonical run uses.
    """

    def __init__(self, control_plane):
        self._control_plane = control_plane

    def apply_actions(self, actions):
        return self._control_plane.apply_actions(actions)


class _CallControlAdapter:
    def __init__(self, voice):
        self._voice = voice

    def apply_actions(self, actions):
        return self._voice.apply_actions(actions)

    def observe_registrations(self, expectations):
        return self._voice.observe_registrations(expectations)

    def inspect_call_control(self, device_name: str):
        """The one call-control table PT 9.0.1 publishes, read as itself.

        `show telephony-service` does not exist on this build, so this is the
        whole governed CME foundation surface: whether the table answered, and
        whether it answered completely.
        """
        return self._voice.inspect_call_control(device_name)


class _EndpointAdapter:
    def __init__(self, configuration, voice=None):
        self._configuration = configuration
        self._voice = voice

    def configure_endpoint_dhcp(self, device_name: str, interface: str):
        return self._configuration.configure_endpoint_dhcp(device_name, interface)

    def read_endpoint_address(self, device_name: str, interface: str):
        # The production voice runtime's own per-phone SVI read, standalone --
        # the same surface every registration episode already reads, callable
        # here BEFORE arming so the OFF-to-ON transition is a measured fact
        # rather than an assumption about a new phone's default.
        if self._voice is not None:
            return self._voice.observe_endpoint(device_name, interface)
        reader = getattr(self._configuration, "read_endpoint_address", None)
        if reader is None:
            # No separate endpoint reader on this runtime: the registration
            # surface stays the only address evidence, and its absence must read
            # UNOBSERVABLE rather than as a missing address.
            return None
        return reader(device_name, interface)

    def set_endpoint_dhcp_client_state(
        self, device_name: str, interface: str, enabled: bool,
    ):
        if self._voice is None:
            raise RuntimeError("the typed phone-SVI DHCP runtime is unavailable")
        return self._voice.set_endpoint_dhcp_client_state(
            device_name, interface, enabled,
        )


def _serialize(result) -> dict:
    voice_vlan_boundaries = [
        item for item in result.lifecycle
        if item.name == "WHEN_VOICE_VLAN_APPLICATION_BOUNDARY"
    ]
    control_voice_vlan_boundaries = [
        item for item in result.lifecycle
        if item.name == "WHEN_CONTROL_VOICE_VLAN_APPLIED"
    ]
    intervention_voice_vlan_boundaries = [
        item for item in result.lifecycle
        if item.name == "WHEN_INTERVENTION_VOICE_VLAN_APPLIED"
    ]
    return {
        "diagnostic": "POSITIVE_DISPOSABLE_VOICE_AB",
        "router_model": result.router_model,
        "switch_model": result.switch_model,
        "phone_model": result.phone_model,
        "router_name": result.router_name,
        "switch_name": result.switch_name,
        "voice_vlan_id": result.voice_vlan_id,
        "outcome": result.outcome,
        "experiment": result.experiment,
        "causal_experiment_result": result.causal_experiment_result,
        "all_endpoint_arms_accepted": result.all_endpoint_arms_accepted,
        "dhcp_flag_transition": result.dhcp_flag_transition,
        "dhcp_flag_transition_valid_for_experiment": (
            result.dhcp_flag_transition_valid_for_experiment
        ),
        "fresh_7960_dhcp_transaction": result.fresh_7960_dhcp_transaction,
        "server_receives_discover": "UNOBSERVABLE",
        "dhcp_transaction_progress": "UNOBSERVABLE",
        "stp_timing_controls_dhcp_acquisition": (
            result.stp_timing_controls_dhcp_acquisition
        ),
        "shared_foundation_ready": result.shared_foundation_ready,
        "shared_foundation_wait": (
            result.shared_foundation_wait.as_evidence()
            if result.shared_foundation_wait is not None else None
        ),
        "pre_control_foundation": (
            result.pre_control_foundation.as_evidence()
            if result.pre_control_foundation is not None else None
        ),
        "pre_control_foundation_status": (
            result.pre_control_foundation_status
        ),
        "post_control_signal_foundation": (
            result.post_control_signal_foundation.as_evidence()
            if result.post_control_signal_foundation is not None else None
        ),
        "post_control_signal_foundation_status": (
            result.post_control_signal_foundation_status
        ),
        "pre_intervention_foundation": (
            result.pre_intervention_foundation.as_evidence()
            if result.pre_intervention_foundation is not None else None
        ),
        "trunk_order_forwarding_transition": (
            result.trunk_order_forwarding_transition
        ),
        "trunk_forwarding_controls_voice_acquisition": (
            result.trunk_forwarding_controls_voice_acquisition
        ),
        "trunk_roles_reversed": result.trunk_roles_reversed,
        "paired_stp_timing_comparability": (
            result.paired_stp_timing_comparability
        ),
        "voice_bootstrap_dispatch": result.voice_bootstrap_dispatch,
        "control_voice_bootstrap_dispatch": (
            result.control_voice_bootstrap_dispatch
        ),
        "bootstrap_foundation_ready": result.bootstrap_foundation_ready,
        "bootstrap_foundation_wait": (
            result.bootstrap_foundation_wait.as_evidence()
            if result.bootstrap_foundation_wait is not None else None
        ),
        "bootstrap_roles_reversed": result.bootstrap_roles_reversed,
        "voice_bootstrap_controls_acquisition": (
            result.voice_bootstrap_controls_acquisition
        ),
        "trunk_forwarding_convergence": (
            result.trunk_forwarding_convergence
        ),
        "control_edge_dispatch": "NOT_APPLIED",
        "intervention_edge_dispatch": result.edge_policy_dispatch,
        "intervention_edge_runtime_state": (
            result.edge_policy_runtime_state
        ),
        "voice_vlan_clock_boundary": (
            voice_vlan_boundaries[0].as_evidence()
            if len(voice_vlan_boundaries) == 1 else None
        ),
        "control_voice_vlan_boundary": (
            control_voice_vlan_boundaries[0].as_evidence()
            if len(control_voice_vlan_boundaries) == 1 else None
        ),
        "intervention_voice_vlan_boundary": (
            intervention_voice_vlan_boundaries[0].as_evidence()
            if len(intervention_voice_vlan_boundaries) == 1 else None
        ),
        "edge_policy_dispatch": result.edge_policy_dispatch,
        "edge_policy_runtime_state": result.edge_policy_runtime_state,
        "edge_stp_effect_observed": result.edge_stp_effect_observed,
        "control_stp_port_gate": (
            result.control_stp_port_gate.as_evidence()
            if result.control_stp_port_gate is not None else None
        ),
        "intervention_stp_port_gate": (
            result.intervention_stp_port_gate.as_evidence()
            if result.intervention_stp_port_gate is not None else None
        ),
        "edge_voice_svi_lifecycle": [
            item.as_evidence() for item in result.edge_voice_svi_lifecycle
        ],
        "control_matching_binding": result.control_matching_binding,
        "intervention_matching_binding": (
            result.intervention_matching_binding
        ),
        "phone_dhcp_lifecycle": [
            item.as_evidence() for item in result.phone_dhcp_lifecycle
        ],
        "pre_retrigger_endpoint_states": [
            item.as_evidence()
            for item in result.pre_retrigger_endpoint_states
        ],
        "pre_retrigger_address_baseline_valid": (
            result.pre_retrigger_address_baseline_valid
        ),
        "phone_svi_dhcp_transitions": [
            item.as_evidence() for item in result.phone_svi_dhcp_transitions
        ],
        "phone_svi_dhcp_transition_valid_for_experiment": (
            result.phone_svi_dhcp_transition_valid_for_experiment
        ),
        "first_observed_svi_dhcp_enabled_milestone": (
            result.first_observed_svi_dhcp_enabled_milestone
        ),
        "first_observed_device_dhcp_enabled_milestone": (
            result.first_observed_device_dhcp_enabled_milestone
        ),
        "svi_dhcp_enabled_before_fwd": result.svi_dhcp_enabled_before_fwd,
        "device_dhcp_enabled_before_fwd": (
            result.device_dhcp_enabled_before_fwd
        ),
        "first_observed_svi_dhcp_enabled_milestone_by_phone": (
            result.first_observed_svi_dhcp_enabled_milestone_by_phone
        ),
        "first_observed_device_dhcp_enabled_milestone_by_phone": (
            result.first_observed_device_dhcp_enabled_milestone_by_phone
        ),
        "svi_dhcp_enabled_before_fwd_by_phone": (
            result.svi_dhcp_enabled_before_fwd_by_phone
        ),
        "device_dhcp_enabled_before_fwd_by_phone": (
            result.device_dhcp_enabled_before_fwd_by_phone
        ),
        "timing_intrusion_assessment": (
            "ONE_BOUNDED_EXISTING_ENDPOINT_SVI_READ_PER_PHONE_AT_EACH_OF_"
            "SEVEN_MILESTONES_NO_RETRY; READ_LATENCY_MAY_SHIFT_LATER_"
            "OBSERVATION_TIMES"
        ),
        "acquisition_started": result.acquisition_started,
        "acquisition_boundary": result.acquisition_boundary,
        "stp_gate": (
            result.stp_gate.as_evidence() if result.stp_gate is not None else None
        ),
        "control_stp_gate": (
            result.control_stp_gate.as_evidence()
            if result.control_stp_gate is not None else None
        ),
        "intervention_stp_gate": (
            result.intervention_stp_gate.as_evidence()
            if result.intervention_stp_gate is not None else None
        ),
        "both_phone_ports_authoritative_fwd": (
            result.both_phone_ports_authoritative_fwd
        ),
        "portfast": result.portfast,
        "voice_binding_count": result.voice_binding_count,
        "voice_binding_ipv4s": (
            list(result.voice_binding_ipv4s)
            if result.voice_binding_ipv4s is not None else None
        ),
        "voice_bindings_observed": result.voice_bindings_observed,
        "matching_intervention_binding": (
            result.matching_intervention_binding
        ),
        "stp_phone_row_after": result.stp_phone_row_after,
        "portfast_readback": result.portfast_readback,
        "foundation": result.foundation.as_evidence(),
        "foundation_ladder": [
            {"stage": stage, "status": status}
            for stage, status in result.foundation_ladder
        ],
        "first_boundary_stage": result.first_boundary_stage,
        "first_boundary_status": result.first_boundary_status,
        "realtime_before": result.realtime_before,
        "realtime_after": result.realtime_after,
        # The milestone publishes its own retained shape: APPLIED, VERIFIED and
        # UNOBSERVABLE are three different claims, and a hand-built dict here is
        # what dropped the distinction out of the run 3 artefact.
        "lifecycle": [item.as_evidence() for item in result.lifecycle],
        "phones": [
            {
                "phone_name": item.phone_name,
                "extension": item.extension,
                "switch_interface": item.switch_interface,
                "access_vlan_expected": item.access_vlan_expected,
                "data_vlan_readback": item.data_vlan_readback,
                "voice_vlan_readback": item.voice_vlan_readback,
                "dhcp_enabled": item.dhcp_enabled,
                "dhcp_enabled_pre_arm": item.dhcp_enabled_pre_arm,
                "arm_call_accepted": item.arm_call_accepted,
                "dhcp_enabled_post_arm": item.dhcp_enabled_post_arm,
                "ipv4": item.ipv4,
                "voice_svi_present": item.voice_svi_present,
                "address_channel": item.address_channel,
                "portfast_readback": item.portfast_readback,
                "stp_link_types": list(item.stp_link_types),
                "device_ipv4": item.device_ipv4,
                "addressed": item.addressed,
                "registration": item.registration,
                "stp_row_before": item.stp_row_before,
                "stp_row_after": item.stp_row_after,
                "succeeded": item.succeeded,
                "matches_cp_scale_signature": item.matches_cp_scale_signature,
            }
            for item in result.phones
        ],
        "baseline": (
            result.baseline_inventory.compact_summary()
            if result.baseline_inventory is not None else None
        ),
        "final": (
            result.final_inventory.compact_summary()
            if result.final_inventory is not None else None
        ),
        "workspace_restored": result.workspace_restored,
        "realtime_restored": result.realtime_restored,
        "owned_links": list(result.owned_links),
        "removed": list(result.removed),
        "errors": list(result.errors),
    }


def _inventory(physical) -> list[dict]:
    observation = physical.observe_workspace()
    if not observation.observed:
        raise RuntimeError("Live inventory became unobservable: " + observation.message)
    return [
        {"name": item.name, "model": item.model, "ports": list(item.ports)}
        for item in observation.semantic_devices
    ]


def run(
    packet_tracer_version: str,
    *,
    edge_portfast: bool = False,
    paired_access_vlan: bool = False,
    paired_access_vlan_fwd_gated: bool = False,
    phone_dhcp_lifecycle: bool = False,
    phone_svi_dhcp_retrigger: bool = False,
    edge_before_voice_vlan: bool = False,
    trunk_before_voice_vlan: bool = False,
    trunk_roles_reversed: bool = False,
    bootstrap_before_voice_vlan: bool = False,
    bootstrap_roles_reversed: bool = False,
) -> int:
    preflight: dict[str, object] = {
        "python_executable": sys.executable,
        "package_file": packet_tracer_mcp.__file__,
        "loaded_namespaces": [
            name for name in ("packet_tracer_mcp", "src.packet_tracer_mcp")
            if name in sys.modules
        ],
    }
    isolation = ImportIsolationPreflight(GOVERNED_ROOT).ensure_isolated()
    preflight["import_isolation"] = {
        "state": isolation.state.value,
        "detail": isolation.detail,
    }
    if not isolation.isolated:
        return _hard_stop(isolation.render(), preflight)

    repository = read_git_repository_state(GOVERNED_ROOT)
    preflight["repository"] = repository.model_dump(mode="json")
    try:
        dirty = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=GOVERNED_ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        upstream_head = _git_output("rev-parse", "@{upstream}")
    except (OSError, subprocess.CalledProcessError) as exc:
        return _hard_stop(f"Repository preflight failed: {exc}", preflight)
    preflight["repository_dirty"] = bool(dirty)
    preflight["upstream_head"] = upstream_head
    repository_errors = []
    if repository.branch != EXPECTED_BRANCH:
        repository_errors.append(
            f"Expected branch {EXPECTED_BRANCH!r}; observed {repository.branch!r}."
        )
    if repository.upstream != EXPECTED_UPSTREAM:
        repository_errors.append(
            "Expected upstream "
            f"{EXPECTED_UPSTREAM!r}; observed {repository.upstream!r}."
        )
    if repository.error:
        repository_errors.append(repository.error)
    if dirty:
        repository_errors.append("Live session requires a clean initial worktree.")
    if not repository.head or repository.head != upstream_head:
        repository_errors.append(
            "Live session requires its exact initial HEAD pushed to upstream."
        )
    if repository_errors:
        return _hard_stop(" ".join(repository_errors), preflight)

    try:
        processes = _packet_tracer_processes()
    except (OSError, subprocess.CalledProcessError, json.JSONDecodeError) as exc:
        return _hard_stop(
            f"Packet Tracer process preflight failed: {exc}", preflight,
        )
    preflight["packet_tracer_processes"] = processes
    process_error = packet_tracer_process_error(
        processes, packet_tracer_version,
    )
    if process_error:
        return _hard_stop(process_error, preflight)

    transport = PacketTracerHttpTransport()
    if not transport.start(timeout_seconds=20.0):
        preflight["http_bridge"] = transport.status_dict()
        transport.stop()
        return _hard_stop(
            "The authenticated Packet Tracer bridge did not connect.",
            preflight,
        )
    preflight["http_bridge"] = transport.status_dict()
    independent_final = None
    independent_workspace_restored = False
    independent_final_error = ""
    independent_mode = None
    independent_realtime_restored = False
    independent_mode_error = ""
    try:
        physical = PacketTracerPhysicalTopologyRuntime(
            transport.send_and_wait,
            mutation_timeout_seconds=30.0,
            observation_timeout_seconds=12.0,
        )
        baseline = physical.observe_workspace()
        preflight["baseline"] = baseline.compact_summary()
        if not baseline.safe_for_disposable_mutation:
            return _hard_stop(
                "The read-only baseline is not a complete empty semantic "
                "workspace; refusing mutation.",
                preflight,
            )
        mode_runtime = SimulationTraceRuntime(transport.send_and_wait)
        preflight_mode = mode_runtime.read_simulation_state()
        preflight["realtime"] = {
            "observed": preflight_mode.observed,
            "simulation_mode": preflight_mode.simulation_mode,
            "message": preflight_mode.message,
        }
        if not preflight_mode.observed or preflight_mode.simulation_mode:
            return _hard_stop(
                "Realtime was not independently established before mutation.",
                preflight,
            )
        enterprise = PacketTracerEnterpriseConfigurationRuntime(
            lambda: _inventory(physical),
            transport.send,
            transport.send_and_wait,
            l3_timeout_seconds=20.0,
        )
        ios = ControlledIosExecutor(transport.send_and_wait)
        configuration = PacketTracerConfigurationRuntime(transport.send)
        # Built only for the intervention.  The baseline half of the A/B never
        # receives a control-plane runtime, so it cannot apply one by accident.
        control_plane = _ControlPlaneAdapter(
            PacketTracerEnterpriseControlPlaneRuntime(
                lambda: _inventory(physical),
                transport.send,
                transport.send_and_wait,
            )
        ) if (edge_portfast or edge_before_voice_vlan) else None
        configuration_adapter = _ConfigurationAdapter(enterprise, ios)
        voice_runtime = PacketTracerEnterpriseVoiceRuntime(
            lambda: _inventory(physical),
            transport.send,
            transport.send_and_wait,
        )
        paired = (
            paired_access_vlan
            or paired_access_vlan_fwd_gated
            or phone_dhcp_lifecycle
            or phone_svi_dhcp_retrigger
        )
        result = PositiveVoiceSliceQualifier(
            physical,
            configuration_adapter,
            _CallControlAdapter(voice_runtime),
            _EndpointAdapter(configuration, voice_runtime),
            mode_runtime,
            control_plane=control_plane,
            edge_portfast=edge_portfast,
            # Historical paired modes keep access 931/930.  The retrigger A/B
            # removes that network-shape difference: both ports use access
            # 930 / voice 930, and P2's later exact-SVI transition is the only
            # causal difference after both independent FWD gates succeed.
            phone_access_vlans=(
                (VOICE_VLAN_ID, VOICE_VLAN_ID)
                if phone_svi_dhcp_retrigger
                else ((DATA_VLAN_ID, VOICE_VLAN_ID) if paired else None)
            ),
            # Run 10: the acquisition trigger fires only AFTER a fresh+complete
            # qualified STP read observes the intervention port FORWARDING, and
            # only when the pre-arm readback proves the trigger is a real
            # OFF-to-ON transition.  Anything less fails closed with a named
            # boundary instead of another SAME_FAILURE.
            fwd_gated_fresh_dhcp=paired_access_vlan_fwd_gated,
            # Lifecycle qualification reuses the same paired topology and FWD
            # gate, but never calls the endpoint DHCP mutation.  Seven selected
            # boundaries each perform one bounded existing SVI read per phone.
            phone_dhcp_lifecycle=phone_dhcp_lifecycle,
            # One exact-interface SVI DHCP-client YES -> NO -> YES transition
            # on P2, only after the existing authoritative FWD gate.  P1 is a
            # no-mutation control and configurePcIp is not used by this mode.
            phone_svi_dhcp_retrigger=phone_svi_dhcp_retrigger,
            # Run 15: the shared foundation is brought up and VERIFIED while
            # neither phone has been told about a voice VLAN, one typed edge
            # policy reaches the intervention port, and only then does the SAME
            # voice VLAN reach both ports in one batch.  That batch is the
            # causal clock boundary both ports are measured from, by one
            # paired STP read per sample.  No DHCP flag is touched.
            edge_before_voice_vlan=edge_before_voice_vlan,
            # Same-run causal contrast: P1 sees VLAN930 while every readable
            # foundation dimension except trunk forwarding is ready; P2 sees
            # it only after that same authoritative trunk transitions to FWD.
            trunk_before_voice_vlan=trunk_before_voice_vlan,
            trunk_roles_reversed=trunk_roles_reversed,
            # Both phones share the same prepared network.  P1 is signalled
            # before the existing typed Option150/CME/ephone/cnf batch, and P2
            # after it; trunk forwarding is deliberately not a gate here.
            bootstrap_before_voice_vlan=bootstrap_before_voice_vlan,
            bootstrap_roles_reversed=bootstrap_roles_reversed,
        ).qualify(ROUTER_MODEL, SWITCH_MODEL, PHONE_MODEL)
        try:
            independent_final = physical.observe_workspace()
            independent_workspace_restored = (
                physical_workspace_restoration_matches(
                    baseline, independent_final,
                )
            )
        except Exception as exc:  # noqa: BLE001
            independent_final_error = (
                f"independent_final_inventory_failed: {exc}"
            )
        try:
            independent_mode = mode_runtime.read_simulation_state()
            independent_realtime_restored = bool(
                independent_mode.observed
                and not independent_mode.simulation_mode
            )
        except Exception as exc:  # noqa: BLE001
            independent_mode_error = f"independent_mode_read_failed: {exc}"
    finally:
        transport.stop()

    evidence = _serialize(result)
    evidence["packet_tracer_version"] = packet_tracer_version
    evidence["live_source_head"] = repository.head
    evidence["live_preflight"] = preflight
    evidence["independent_final"] = (
        independent_final.compact_summary()
        if independent_final is not None else None
    )
    evidence["independent_workspace_restored"] = (
        independent_workspace_restored
    )
    evidence["independent_final_error"] = independent_final_error
    evidence["independent_realtime"] = (
        {
            "observed": independent_mode.observed,
            "simulation_mode": independent_mode.simulation_mode,
            "message": independent_mode.message,
        }
        if independent_mode is not None else None
    )
    evidence["independent_realtime_restored"] = (
        independent_realtime_restored
    )
    evidence["independent_mode_error"] = independent_mode_error
    # Empty whenever the pool table was read and understood, which is the
    # point: a non-empty list IS the unresolved observability boundary.
    evidence["dhcp_pool_boundary_captures"] = (
        configuration_adapter.pool_boundary_captures
    )
    EVIDENCE_PATH.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE_PATH.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(json.dumps({
        "event": "POSITIVE_VOICE_AB_COMPLETE",
        "live_source_head": evidence["live_source_head"],
        "live_preflight": evidence["live_preflight"],
        "outcome": evidence["outcome"],
        "experiment": evidence["experiment"],
        "causal_experiment_result": evidence["causal_experiment_result"],
        "acquisition_started": evidence["acquisition_started"],
        "acquisition_boundary": evidence["acquisition_boundary"],
        "shared_foundation_ready": evidence["shared_foundation_ready"],
        "shared_foundation_wait": evidence["shared_foundation_wait"],
        "pre_control_foundation_status": evidence[
            "pre_control_foundation_status"
        ],
        "post_control_signal_foundation_status": evidence[
            "post_control_signal_foundation_status"
        ],
        "trunk_order_forwarding_transition": evidence[
            "trunk_order_forwarding_transition"
        ],
        "trunk_forwarding_controls_voice_acquisition": evidence[
            "trunk_forwarding_controls_voice_acquisition"
        ],
        "trunk_roles_reversed": evidence["trunk_roles_reversed"],
        "voice_bootstrap_dispatch": evidence["voice_bootstrap_dispatch"],
        "control_voice_bootstrap_dispatch": evidence[
            "control_voice_bootstrap_dispatch"
        ],
        "bootstrap_foundation_ready": evidence[
            "bootstrap_foundation_ready"
        ],
        "bootstrap_foundation_wait": evidence["bootstrap_foundation_wait"],
        "bootstrap_roles_reversed": evidence["bootstrap_roles_reversed"],
        "voice_bootstrap_controls_acquisition": evidence[
            "voice_bootstrap_controls_acquisition"
        ],
        "trunk_forwarding_convergence": evidence[
            "trunk_forwarding_convergence"
        ],
        "pre_retrigger_endpoint_states": evidence[
            "pre_retrigger_endpoint_states"
        ],
        "pre_retrigger_address_baseline_valid": evidence[
            "pre_retrigger_address_baseline_valid"
        ],
        "phone_svi_dhcp_transitions": evidence[
            "phone_svi_dhcp_transitions"
        ],
        "phone_svi_dhcp_transition_valid_for_experiment": evidence[
            "phone_svi_dhcp_transition_valid_for_experiment"
        ],
        "stp_gate": evidence["stp_gate"],
        "control_stp_gate": evidence["control_stp_gate"],
        "intervention_stp_gate": evidence["intervention_stp_gate"],
        "both_phone_ports_authoritative_fwd": evidence[
            "both_phone_ports_authoritative_fwd"
        ],
        "first_observed_svi_dhcp_enabled_milestone": evidence[
            "first_observed_svi_dhcp_enabled_milestone"
        ],
        "first_observed_device_dhcp_enabled_milestone": evidence[
            "first_observed_device_dhcp_enabled_milestone"
        ],
        "svi_dhcp_enabled_before_fwd": evidence[
            "svi_dhcp_enabled_before_fwd"
        ],
        "device_dhcp_enabled_before_fwd": evidence[
            "device_dhcp_enabled_before_fwd"
        ],
        "first_observed_svi_dhcp_enabled_milestone_by_phone": evidence[
            "first_observed_svi_dhcp_enabled_milestone_by_phone"
        ],
        "first_observed_device_dhcp_enabled_milestone_by_phone": evidence[
            "first_observed_device_dhcp_enabled_milestone_by_phone"
        ],
        "svi_dhcp_enabled_before_fwd_by_phone": evidence[
            "svi_dhcp_enabled_before_fwd_by_phone"
        ],
        "device_dhcp_enabled_before_fwd_by_phone": evidence[
            "device_dhcp_enabled_before_fwd_by_phone"
        ],
        "portfast": evidence["portfast"],
        "portfast_readback": evidence["portfast_readback"],
        "voice_bindings": evidence["voice_bindings_observed"],
        "voice_binding_ipv4s": evidence["voice_binding_ipv4s"],
        "matching_intervention_binding": evidence[
            "matching_intervention_binding"
        ],
        "stp_phone_row_after": evidence["stp_phone_row_after"],
        "foundation": evidence["foundation"],
        "foundation_ladder": evidence["foundation_ladder"],
        "dhcp_pool_boundary_captures": len(
            evidence["dhcp_pool_boundary_captures"]
        ),
        "first_boundary_stage": evidence["first_boundary_stage"],
        "first_boundary_status": evidence["first_boundary_status"],
        "phones": [
            {
                key: item[key]
                for key in (
                    "extension", "access_vlan_expected", "voice_vlan_readback",
                    "dhcp_enabled", "addressed", "registration",
                    "stp_row_after", "portfast_readback", "stp_link_types",
                )
            }
            for item in evidence["phones"]
        ],
        "workspace_restored": evidence["workspace_restored"],
        "independent_final": evidence["independent_final"],
        "independent_workspace_restored": evidence[
            "independent_workspace_restored"
        ],
        "independent_final_error": evidence["independent_final_error"],
        "independent_realtime": evidence["independent_realtime"],
        "independent_realtime_restored": evidence[
            "independent_realtime_restored"
        ],
        "independent_mode_error": evidence["independent_mode_error"],
        "realtime_restored": evidence["realtime_restored"],
        "errors": evidence["errors"][:5],
    }))
    return (
        0
        if (
            result.workspace_restored
            and independent_workspace_restored
            and independent_realtime_restored
        )
        else 1
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packet-tracer-version", required=True)
    parser.add_argument(
        "--edge-portfast", action="store_true",
        help=(
            "apply phone-facing edge PortFast (BPDU Guard stays off).  This is "
            "the ONE variable the causal A/B changes; without it the run is "
            "byte-for-byte the same experiment as run 4."
        ),
    )
    parser.add_argument(
        "--paired-access-vlan", action="store_true",
        help=(
            "run the same-run two-phone access-VLAN causal control: the "
            "control phone keeps access 931 / voice 930 and the intervention "
            "phone's port carries access 930 / voice 930.  This is the ONE "
            "variable this experiment changes."
        ),
    )
    parser.add_argument(
        "--paired-access-vlan-fwd-gated", action="store_true",
        help=(
            "run the paired access-VLAN control with the run-10 FWD gate: "
            "DHCP is armed only after the intervention port is independently "
            "observed FORWARDING in the voice VLAN, and only when the pre-arm "
            "readback proves the arming call is a real OFF-to-ON transition.  "
            "Unmet preconditions fail closed with a named boundary."
        ),
    )
    parser.add_argument(
        "--phone-dhcp-lifecycle", action="store_true",
        help=(
            "run the read-only phone DHCP lifecycle diagnostic on the paired "
            "topology and authoritative FWD gate.  It samples only the "
            "existing endpoint/SVI surface and never arms DHCP."
        ),
    )
    parser.add_argument(
        "--phone-svi-dhcp-retrigger", action="store_true",
        help=(
            "run the paired, authoritative-FWD-gated phone-SVI DHCP client "
            "retrigger experiment.  Both phones must first read DHCP enabled; "
            "only P2 then receives an exact-interface YES-to-NO-to-YES typed "
            "transition with readback before the acquisition window opens."
        ),
    )
    parser.add_argument(
        "--edge-before-voice-vlan", action="store_true",
        help=(
            "run 15: verify the shared foundation while no phone has been "
            "signalled a voice VLAN, dispatch one typed edge policy to the "
            "intervention port only, then apply the SAME voice VLAN to both "
            "phone ports as a causal clock boundary and measure both ports "
            "from it with one paired STP read per sample.  No DHCP flag is "
            "armed, mutated, bounced or power-cycled by this mode."
        ),
    )
    parser.add_argument(
        "--trunk-before-voice-vlan", action="store_true",
        help=(
            "signal the control phone while all readable shared foundation "
            "dimensions except trunk forwarding are ready, wait for that same "
            "trunk to transition to forwarding, then signal the intervention "
            "phone. No DHCP flag, PortFast, topology, pool or CME variable is "
            "changed."
        ),
    )
    parser.add_argument(
        "--reverse-trunk-roles", action="store_true",
        help=(
            "counterbalance the trunk-order experiment: P2 is signalled before "
            "trunk forwarding and P1 after it. Requires "
            "--trunk-before-voice-vlan."
        ),
    )
    parser.add_argument(
        "--bootstrap-before-voice-vlan", action="store_true",
        help=(
            "signal the control phone after the L2/L3/DHCP network is ready "
            "but before Option150/CME/ephone/cnf dispatch, apply that bootstrap "
            "once, then signal the intervention phone. Trunk forwarding is not "
            "a gate and no DHCP flag or PortFast mutation is used."
        ),
    )
    parser.add_argument(
        "--reverse-bootstrap-roles", action="store_true",
        help=(
            "counterbalance the bootstrap-order experiment: P2 is the "
            "pre-bootstrap control and P1 the post-bootstrap intervention. "
            "Requires --bootstrap-before-voice-vlan."
        ),
    )
    args = parser.parse_args()
    modes = [
        name for name, enabled in (
            ("--edge-portfast", args.edge_portfast),
            ("--paired-access-vlan", args.paired_access_vlan),
            ("--paired-access-vlan-fwd-gated", args.paired_access_vlan_fwd_gated),
            ("--phone-dhcp-lifecycle", args.phone_dhcp_lifecycle),
            ("--phone-svi-dhcp-retrigger", args.phone_svi_dhcp_retrigger),
            ("--edge-before-voice-vlan", args.edge_before_voice_vlan),
            ("--trunk-before-voice-vlan", args.trunk_before_voice_vlan),
            (
                "--bootstrap-before-voice-vlan",
                args.bootstrap_before_voice_vlan,
            ),
        ) if enabled
    ]
    if len(modes) > 1:
        parser.error(
            "one causal variable per run: " + " and ".join(modes)
            + " cannot be combined"
        )
    if args.reverse_trunk_roles and not args.trunk_before_voice_vlan:
        parser.error(
            "--reverse-trunk-roles requires --trunk-before-voice-vlan"
        )
    if (
        args.reverse_bootstrap_roles
        and not args.bootstrap_before_voice_vlan
    ):
        parser.error(
            "--reverse-bootstrap-roles requires "
            "--bootstrap-before-voice-vlan"
        )
    return run(
        args.packet_tracer_version,
        edge_portfast=args.edge_portfast,
        paired_access_vlan=args.paired_access_vlan,
        paired_access_vlan_fwd_gated=args.paired_access_vlan_fwd_gated,
        phone_dhcp_lifecycle=args.phone_dhcp_lifecycle,
        phone_svi_dhcp_retrigger=args.phone_svi_dhcp_retrigger,
        edge_before_voice_vlan=args.edge_before_voice_vlan,
        trunk_before_voice_vlan=args.trunk_before_voice_vlan,
        trunk_roles_reversed=args.reverse_trunk_roles,
        bootstrap_before_voice_vlan=args.bootstrap_before_voice_vlan,
        bootstrap_roles_reversed=args.reverse_bootstrap_roles,
    )


if __name__ == "__main__":
    raise SystemExit(main())
