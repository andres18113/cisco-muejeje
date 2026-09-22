"""Per-VLAN access-forwarding admission and the documented port light enum.

Two decisions live here and neither performs I/O. The first answers whether
one bounded switch/VLAN spanning-tree sample grants forwarding permission for
an exact interface set. The second interprets `Port::getLightStatus()` through
the enum Cisco documents, and refuses to interpret anything else.

The rule is deliberately narrow. A permission is per VLAN, per interface and
per sample: a port that is up, a green light and a forwarding row observed
before the last topology change are auxiliary evidence, never a substitute for
a fresh, complete, uniquely attributed row of the exact VLAN this question is
about. Every dimension refuses on its own so the caller can say which one did.

Per sample also means per sample when the news is bad. The rule reads the
authorizing sample's own facts -- the last one, whose rows it is about -- and
never an episode aggregate. An earlier read that failed recoverably is kept as
a diagnostic and refuses nothing, while a boundary that really did close the
window refuses under the name of the boundary that closed it.
"""

from __future__ import annotations

from ..models.forwarding import (
    AccessForwardingAdmission,
    AccessForwardingObservation,
    PortLightReading,
)

#: Cisco's documented `LightStatus` enumeration, read from the installed
#: reference (`help/default/IpcAPI/class_port.html`, `Port::getLightStatus`):
#: `eOffLight = 0, eAmberLight = 1, eGreenLight = 2, eBlink = 3`. A value
#: outside the table is never named; it stays `unknown`.
PORT_LIGHT_STATUS: dict[int, str] = {0: "off", 1: "amber", 2: "green", 3: "blink"}
LIGHT_UNKNOWN = "unknown"

#: The only spanning-tree port states that forward user frames, matched
#: exactly. IOS prints `FWD`; the long spelling is accepted because the same
#: parser feeds several builds. A prefix rule was rejected on purpose: it
#: would have admitted any state whose name merely begins with one of these.
FORWARDING_STATES = frozenset({"FWD", "FORWARDING"})

#: Dimensions the admission refuses on, most specific first. `NONE` means the
#: sample was admitted.
DIMENSION_NOT_ATTEMPTED = "NOT_ATTEMPTED"
DIMENSION_EXECUTION = "EXECUTION"
DIMENSION_FRESHNESS = "FRESHNESS"
DIMENSION_COMPLETENESS = "COMPLETENESS"
DIMENSION_IDENTITY = "IDENTITY"
DIMENSION_DEADLINE = "DEADLINE"
DIMENSION_SAMPLE_BUDGET = "SAMPLE_CALL_BUDGET_EXHAUSTED"
DIMENSION_VLAN_INSTANCE = "VLAN_INSTANCE"
DIMENSION_REQUEST = "REQUEST"
DIMENSION_MISSING_INTERFACE = "MISSING_INTERFACE"
DIMENSION_AMBIGUOUS_INTERFACE = "AMBIGUOUS_INTERFACE"
DIMENSION_NON_FORWARDING = "NON_FORWARDING"
DIMENSION_NONE = "NONE"

#: The causes the two boundary dimensions report. Each names the lifetime it
#: is about, so a reader never has to guess whether a refusal is about one
#: read, the episode around it, or the parent allowance above both.
CAUSE_SAMPLE_AFTER_DEADLINE = "sample_after_deadline"
CAUSE_AUXILIARY_READ_AFTER_DEADLINE = "auxiliary_read_after_deadline"
CAUSE_EPISODE_WINDOW_ENDED = "episode_window_ended_without_admissible_sample"
CAUSE_GROUP_DEADLINE_REACHED = "group_deadline_reached"
CAUSE_SAMPLE_BUDGET_EXHAUSTED = "sample_call_budget_exhausted"
CAUSE_AUXILIARY_BUDGET_EXHAUSTED = "auxiliary_read_call_budget_exhausted"

CONFIRMED_UNIQUE = "confirmed_unique"


def interpret_port_light(raw: object, raw_type: str) -> str:
    """Return the documented name of one light value, or `unknown`.

    Only an actual integer reported as a number is interpreted. A boolean is
    not an integer here: `True` would otherwise be read as `amber`.
    """
    if raw_type != "number" or isinstance(raw, bool) or not isinstance(raw, int):
        return LIGHT_UNKNOWN
    return PORT_LIGHT_STATUS.get(raw, LIGHT_UNKNOWN)


def port_light_reading(
    device_name: str,
    interface: str,
    *,
    raw: object = None,
    raw_type: str = "absent",
    failure_reason: str = "",
) -> PortLightReading:
    """Build one strictly typed light reading and its documented meaning."""
    typed = (
        raw
        if raw_type == "number" and isinstance(raw, int) and not isinstance(raw, bool)
        else None
    )
    return PortLightReading(
        device_name=device_name,
        interface=interface,
        raw=typed,
        raw_type=raw_type,
        interpretation=interpret_port_light(raw, raw_type),
        failure_reason=failure_reason,
    )


def access_forwarding_admission(
    observation: AccessForwardingObservation,
) -> AccessForwardingAdmission:
    """Decide whether one sample grants forwarding on every named interface.

    Fail-closed and ordered: a sample that did not execute says nothing about
    freshness, a stale one says nothing about the VLAN, and a VLAN instance
    that is absent says nothing about any interface. The first dimension that
    refuses is the one reported, with every cause it collected.
    """
    requested = tuple(observation.requested_interfaces)
    if not requested:
        return AccessForwardingAdmission(
            False, DIMENSION_REQUEST, causes=("no_interface_requested",)
        )
    if not observation.samples:
        return AccessForwardingAdmission(
            False,
            DIMENSION_NOT_ATTEMPTED,
            causes=(observation.failure_reason or "no_sample_taken",),
        )
    if not observation.executed:
        return AccessForwardingAdmission(
            False,
            DIMENSION_EXECUTION,
            causes=(observation.failure_reason or "show_not_executed",),
        )
    if not observation.fresh_output_observed:
        return AccessForwardingAdmission(
            False, DIMENSION_FRESHNESS, causes=("stale_terminal_window",)
        )
    if not observation.output_complete:
        return AccessForwardingAdmission(
            False, DIMENSION_COMPLETENESS, causes=("paged_or_truncated_output",)
        )
    if (
        observation.observed_device_name != observation.switch_name
        or observation.device_identity_provenance != CONFIRMED_UNIQUE
    ):
        return AccessForwardingAdmission(
            False,
            DIMENSION_IDENTITY,
            causes=(
                "observed_device:"
                + (observation.observed_device_name or "unattributed"),
            ),
        )
    if observation.deadline_reached:
        # The window is closed, so nothing here authorizes a request. Which
        # boundary closed it is the observation's to state: a sample that
        # really did arrive late, an auxiliary read that consumed the rest, a
        # window that simply ended, or a parent bound the product applied.
        # A record written before those names existed meant the late sample.
        return AccessForwardingAdmission(
            False,
            DIMENSION_DEADLINE,
            causes=(observation.deadline_cause or CAUSE_SAMPLE_AFTER_DEADLINE,),
        )
    if observation.sample_budget_exhausted or observation.auxiliary_budget_exhausted:
        # An earlier sample's exhaustion is deliberately absent from this
        # test. It is retained as an episode diagnostic, and a read that
        # failed recoverably never refuses the complete read that followed it.
        return AccessForwardingAdmission(
            False,
            DIMENSION_SAMPLE_BUDGET,
            causes=(
                CAUSE_SAMPLE_BUDGET_EXHAUSTED
                if observation.sample_budget_exhausted
                else CAUSE_AUXILIARY_BUDGET_EXHAUSTED,
            ),
        )
    if not observation.vlan_present:
        return AccessForwardingAdmission(
            False,
            DIMENSION_VLAN_INSTANCE,
            causes=(f"vlan_instance_absent:{observation.vlan_id}",),
        )
    by_interface = {item.interface: item for item in observation.rows}
    missing = tuple(item for item in requested if item not in by_interface)
    if missing or any(by_interface[item].matches == 0 for item in requested):
        absent = missing + tuple(
            item
            for item in requested
            if item in by_interface and by_interface[item].matches == 0
        )
        return AccessForwardingAdmission(
            False,
            DIMENSION_MISSING_INTERFACE,
            causes=tuple(f"interface_absent:{item}" for item in absent),
        )
    ambiguous = tuple(item for item in requested if by_interface[item].matches > 1)
    if ambiguous:
        return AccessForwardingAdmission(
            False,
            DIMENSION_AMBIGUOUS_INTERFACE,
            causes=tuple(
                f"interface_rows:{item}={by_interface[item].matches}"
                for item in ambiguous
            ),
        )
    non_forwarding = tuple(
        item
        for item in requested
        if str(by_interface[item].state).upper() not in FORWARDING_STATES
    )
    if non_forwarding:
        return AccessForwardingAdmission(
            False,
            DIMENSION_NON_FORWARDING,
            causes=tuple(
                f"{item}={by_interface[item].state or 'unobservable'}"
                for item in non_forwarding
            ),
        )
    return AccessForwardingAdmission(True, DIMENSION_NONE, requested)


def access_forwarding_facts(
    observation: AccessForwardingObservation,
    admission: AccessForwardingAdmission,
) -> dict[str, object]:
    """Return the record shape of one sample and what it was admitted for."""
    return {
        "switch": observation.switch_name,
        "vlan_id": observation.vlan_id,
        "requested_interfaces": list(observation.requested_interfaces),
        "rows": [
            {
                "interface": item.interface,
                "matches": item.matches,
                "state": item.state,
                "role": item.role,
            }
            for item in observation.rows
        ],
        "executed": observation.executed,
        "fresh_output_observed": observation.fresh_output_observed,
        "output_complete": observation.output_complete,
        "observed_device_name": observation.observed_device_name,
        "device_identity_provenance": observation.device_identity_provenance,
        "vlan_present": observation.vlan_present,
        "samples": observation.samples,
        "sample_history": [
            {
                "elapsed_ms": sample.elapsed_ms,
                "rows": [
                    {
                        "interface": row.interface,
                        "matches": row.matches,
                        "state": row.state,
                        "role": row.role,
                    }
                    for row in sample.rows
                ],
                "executed": sample.executed,
                "fresh_output_observed": sample.fresh_output_observed,
                "output_complete": sample.output_complete,
                "observed_device_name": sample.observed_device_name,
                "device_identity_provenance": sample.device_identity_provenance,
                "vlan_present": sample.vlan_present,
                "channel_calls": sample.channel_calls,
                "sample_budget_exhausted": sample.sample_budget_exhausted,
                "deadline_reached": sample.deadline_reached,
            }
            for sample in observation.sample_history
        ],
        "max_samples": observation.max_samples,
        "deadline_seconds": observation.deadline_seconds,
        "elapsed_ms": observation.elapsed_ms,
        "deadline_reached": observation.deadline_reached,
        "sample_call_budget": observation.sample_call_budget,
        "channel_calls": observation.channel_calls,
        "sample_budget_exhausted": observation.sample_budget_exhausted,
        # Raw timeliness and budget facts about the authorizing sample, the
        # episode diagnostics around it, the auxiliary read's own facts, and
        # the applicable parent bound -- each under its own key, so a reader
        # of the durable record never has to infer which one a flag meant.
        "sample_after_deadline": observation.sample_after_deadline,
        "episode_budget_exhausted": observation.episode_budget_exhausted,
        "episode_end_reason": observation.episode_end_reason,
        "auxiliary_budget_exhausted": observation.auxiliary_budget_exhausted,
        "auxiliary_read_after_deadline": observation.auxiliary_read_after_deadline,
        "deadline_scope": observation.deadline_scope,
        "deadline_cause": observation.deadline_cause,
        "simulation_time": observation.simulation_time,
        "failure_reason": observation.failure_reason,
        "lights": [
            {
                "device": item.device_name,
                "interface": item.interface,
                "raw": item.raw,
                "raw_type": item.raw_type,
                "interpretation": item.interpretation,
                "failure_reason": item.failure_reason,
            }
            for item in observation.lights
        ],
        "admitted": admission.admitted,
        "dimension": admission.dimension,
        "forwarding_interfaces": list(admission.forwarding_interfaces),
        "causes": list(admission.causes),
        # Stated on every sample so no reader can promote the auxiliary
        # evidence beside it into a forwarding or reachability claim.
        "light_status_is_auxiliary": True,
    }
