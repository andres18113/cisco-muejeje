"""Positive disposable Voice slice: the A side of the Configuring-IP A/B.

CP-SCALE Floor 1 leaves DHCP enabled on 21/21 phones and addressed on 0/21.
Nothing in that failure says whether Voice works AT ALL on this build, so the
failure cannot yet be called scale-specific.  This qualification builds the
smallest Voice slice that could succeed -- one router, one PoE switch, two
phones -- and reads the same surfaces the canonical run reads.

What it deliberately does NOT do:

* It applies no edge STP policy.  PortFast is emitted by the control-plane
  stage, not by the configuration or voice paths, so a slice built from those
  paths carries none.  Adding one to make the slice succeed would answer a
  question nobody asked; a slice that registers WITHOUT PortFast is exactly the
  evidence that weakens PortFast as the explanation.
* It promotes nothing.  Voice VLAN read back, DHCP enabled, an address, a
  binding and a registration are five independent facts, and each is observed
  on its own surface.  COMPILED != APPLIED != ADDRESSED != REGISTERED.
* It creates no mutation primitive.  Every mutation goes through a typed
  production runtime; this module only orders them and journals when each one
  happened.

The lifecycle journal exists because lifecycle is still a live hypothesis:
historical E7 never retained its ordering, so "it worked once" cannot be
compared against anything.  Here the order is recorded as it happens, and a
milestone nobody could observe is written UNOBSERVABLE rather than assumed.
"""

from __future__ import annotations

import re
import secrets
from dataclasses import dataclass, field
from time import monotonic, sleep
from typing import Protocol

from ...domain.enterprise.models.configuration_runtime import RuntimeActionMutation
from ...domain.enterprise.models.physical_deployment import (
    PhysicalMutationResult,
    PhysicalWorkspaceObservation,
    physical_workspace_restoration_matches,
)
from ...domain.models.plans import DevicePlan, LinkPlan
from ...shared.utils import same_interface_name

#: Reserved prefix, same intent as the other disposables: every object this
#: qualification creates is recognisable as its own and nothing else is touched.
#:
#: It lives in the TYPED namespace (`MCP-...`), not the discovery one
#: (`__MCP_...`), and that is TD-RUNTIME-004 rather than taste.  The trusted
#: control-plane renderer's allowlist requires an alphanumeric first character,
#: and the resolution on record for that conflict is a compatible namespace and
#: never a relaxed validator.  This slice renders edge-port actions through that
#: renderer, so it has to be reachable by it.  The first intervention LIVE is
#: what proved the point: both edge mutations came back `Invalid compiled device
#: name`, PortFast read NOT_APPLIED, and the run was a baseline wearing an
#: experiment's name.  Cleanup was never affected either way -- it tracks the
#: objects it created, not a string.
POSITIVE_VOICE_PREFIX = "MCP-VOICEAB-"

#: The documented historical E7 shape.  930 is a non-default VLAN, so a row that
#: appears for it was created by this slice and not inherited from VLAN 1.
VOICE_VLAN_ID = 930
DATA_VLAN_ID = 931
EXTENSIONS = ("3101", "3102")

#: The call control this slice creates, and the id of the binding action that a
#: registration expectation verifies.  Both live here so the expectation names
#: the action that was actually applied instead of a string that merely looks
#: like it.
CALL_CONTROL_ID = "voiceab/cme"

#: The physical port a phone link lands on, and the interface a phone actually
#: holds an address on.  They are NOT the same port, and the first LIVE proved
#: what happens when one is used for the other: `Switch` is the RJ45 the cable
#: attaches to, while the address lives on the SVI the phone creates for its
#: voice VLAN -- which is the interface the production compiler names for every
#: phone it arms and reads back (`_phone_addressing_interface`).  Arming and
#: reading the physical port answers nothing at all, and nothing at all is
#: indistinguishable from "no address" exactly where this A/B cannot afford the
#: confusion.
PHONE_LINK_PORT = "Switch"
PHONE_ADDRESSING_INTERFACE = f"Vlan{VOICE_VLAN_ID}"

#: The uplink this slice builds, named ONCE.  Every foundation read below is
#: about the objects these names create, so an observation cannot drift from the
#: configuration that produced it by editing one string and not the other.
SWITCH_UPLINK_INTERFACE = "GigabitEthernet0/1"
ROUTER_UPLINK_INTERFACE = "FastEthernet0/0"
ROUTER_VOICE_SUBINTERFACE = f"{ROUTER_UPLINK_INTERFACE}.{VOICE_VLAN_ID}"
ROUTER_DATA_SUBINTERFACE = f"{ROUTER_UPLINK_INTERFACE}.{DATA_VLAN_ID}"
TRUNK_NATIVE_VLAN_ID = 1

#: Phone-facing edge PortFast: the ONE variable the causal A/B changes.
#: `edge_portfast=False` is run 4's behaviour exactly and stays the default, so
#: the baseline half of the comparison cannot drift away from the experiment it
#: is the control for.  BPDU Guard is deliberately NOT turned on with it --
#: `ConfigureStpEdgePort.bpduguard` defaults to True, and taking that default
#: would change two things at once and answer neither question.
PORTFAST_APPLIED = "APPLIED"
PORTFAST_NOT_APPLIED = "NOT_APPLIED"

VOICE_NETWORK = "10.93.0.0"
VOICE_PREFIX = 24
VOICE_NETMASK = "255.255.255.0"
VOICE_GATEWAY = "10.93.0.1"
#: The pool identity and lease window are written ONCE: the readback is
#: only about the intent if it names the same pool and the same window,
#: and drift between two literals would surface as a WRONG absence rather
#: than as an error.
VOICE_POOL_NAME = "VOICEAB_VOICE"
VOICE_LEASE_START = "10.93.0.10"
VOICE_LEASE_END = "10.93.0.254"
DATA_NETWORK = "10.94.0.0"
DATA_GATEWAY = "10.94.0.1"

#: What a milestone's claim RESTS on, which is what bounds the status it may
#: reach.  A typed mutation answering `applied=True` states that the runtime
#: channel accepted the dispatch; it states nothing about what the backend now
#: holds.  Only a read of that backend can.
APPLICATION = "APPLICATION"
OBSERVATION = "OBSERVATION"

#: Statuses.  Absence is never spelled as a negative result.
#: APPLIED and VERIFIED are NOT the same claim and never collapse into one:
#: the run 3 evidence published the router's DHCP pool, its subinterfaces,
#: option 150 and CME as VERIFIED on nothing but their mutations having been
#: accepted, and none of those four had been read back at all.
APPLIED = "APPLIED"
VERIFIED = "VERIFIED"
CONTRADICTED = "CONTRADICTED"
UNOBSERVABLE = "UNOBSERVABLE"

#: A dimension no governed read on this build can reach at all.  It is a fact
#: about the observer, never about the network, and it must never be shortened
#: to "absent": `show telephony-service` does not exist on `9.0.1.0858`, no
#: registered query exposes a DHCP pool DEFINITION or option 150, and
#: `VerificationKind.DHCP_POOL` is pinned UNOBSERVABLE by its own ceiling.
NOT_AVAILABLE = "NOT_AVAILABLE_WITH_CURRENT_GOVERNED_READBACKS"
YES = "YES"
NO = "NO"
REGISTERED = "REGISTERED"
NOT_REGISTERED = "NOT_REGISTERED"

#: STP phone-row classification.  ABSENT is its own answer: CP-SCALE's VLAN20
#: phone rows were absent, and an absent row is not a blocked one.
FORWARDING = "FORWARDING"
BLOCKING = "BLOCKING"
ABSENT = "ABSENT"

#: Outcomes of the whole positive control.
SUCCESS = "SUCCESS"
SAME_FAILURE = "SAME_FAILURE"
DIFFERENT_FAILURE = "DIFFERENT_FAILURE"

#: Which experiment a result belongs to.  The uniform slice and the paired
#: access-VLAN slice answer different questions, and the FWD-gated slice is a
#: third: it withholds the acquisition trigger until forwarding was OBSERVED.
EXPERIMENT_UNIFORM_BASELINE = "UNIFORM_BASELINE"
EXPERIMENT_PAIRED_ACCESS_VLAN = "PAIRED_ACCESS_VLAN"
EXPERIMENT_PAIRED_ACCESS_VLAN_FWD_GATED = "PAIRED_ACCESS_VLAN_FWD_GATED"

#: The FWD gate's terminal statuses.  FORWARDING and UNOBSERVABLE reuse the
#: row classifications above; TIMEOUT is the bounded wait expiring while the
#: port was still read in a non-forwarding state, which is NOT evidence the
#: port never forwards -- two snapshots taught that lesson in run 9.
GATE_TIMEOUT = "TIMEOUT"

#: Run-10 fail-closed boundaries.  Each names the precondition that was NOT
#: met, so the run can never read as another ambiguous SAME_FAILURE: a window
#: that never opened is a different fact from phones that failed inside one.
ACQUISITION_NOT_STARTED_STP_PRECONDITION_UNMET = (
    "ACQUISITION_NOT_STARTED_STP_PRECONDITION_UNMET"
)
ACQUISITION_NOT_STARTED_FRESH_DHCP_TRIGGER_UNPROVEN = (
    "ACQUISITION_NOT_STARTED_FRESH_DHCP_TRIGGER_UNPROVEN"
)
DHCP_FLAG_TRANSITION_OBSERVED_OFF_TO_ON = "OBSERVED_OFF_TO_ON"
DHCP_FLAG_TRANSITION_NOT_OBSERVED = "NOT_OBSERVED"
FRESH_7960_DHCP_TRANSACTION_NOT_INDEPENDENTLY_ESTABLISHED = (
    "NOT_INDEPENDENTLY_ESTABLISHED"
)

#: Natural STP convergence on this build is the classical listening+learning
#: walk, so the bound must outlive it with margin; the interval is coarse
#: because each sample is a full qualified multi-page IOS capture, not a flag.
STP_FWD_GATE_TIMEOUT_SECONDS = 60.0
STP_FWD_GATE_INTERVAL_SECONDS = 2.0


@dataclass(frozen=True)
class StpForwardingGate:
    """What the bounded FWD gate observed, kept compact and terminal.

    `observed_states` collapses adjacent repeats, so a port that sat in LIS
    for twenty samples and then moved reads ("LIS", "LRN", "FORWARDING") --
    the transitions survive without retaining twenty CLI transcripts.
    """

    status: str = UNOBSERVABLE
    observed_states: tuple[str, ...] = ()
    duration_ms: int = 0
    samples: int = 0

    @property
    def forwarding_observed(self) -> bool:
        return self.status == FORWARDING

    def as_evidence(self) -> dict:
        return {
            "status": self.status,
            "observed_states": list(self.observed_states),
            "duration_ms": self.duration_ms,
            "samples": self.samples,
            "forwarding_observed": self.forwarding_observed,
        }


def await_stp_forwarding(
    configuration, switch_name: str, vlan_id: int, interface: str,
    *,
    timeout_seconds: float = STP_FWD_GATE_TIMEOUT_SECONDS,
    interval_seconds: float = STP_FWD_GATE_INTERVAL_SECONDS,
    clock=monotonic,
    sleeper=sleep,
    errors: list[str] | None = None,
) -> StpForwardingGate:
    """Poll the qualified STP read until this port forwards in this VLAN.

    Success is one thing only: a fresh+complete capture whose row for this
    interface in this VLAN's instance reads FORWARDING.  LIS, LRN, BLK and
    ABSENT keep the poll alive until the bound; a read that established
    nothing terminates the gate UNOBSERVABLE immediately, because continuing
    would let the next decision ride on the last valid sample -- a stale FWD
    is exactly the claim this gate exists to never make.
    """
    started = clock()
    observed: list[str] = []
    samples = 0
    while True:
        samples += 1
        try:
            instances = configuration.read_spanning_tree(switch_name)
        except Exception as exc:  # noqa: BLE001
            if errors is not None:
                errors.append(f"stp_gate_read_raised: {exc}")
            instances = None
        classification = (
            UNOBSERVABLE if instances is None
            else _classify_stp_row(instances, vlan_id, interface)
        )
        if not observed or observed[-1] != classification:
            observed.append(classification)
        duration_ms = int((clock() - started) * 1000)
        if classification == FORWARDING:
            return StpForwardingGate(
                FORWARDING, tuple(observed), duration_ms, samples,
            )
        if classification == UNOBSERVABLE:
            return StpForwardingGate(
                UNOBSERVABLE, tuple(observed), duration_ms, samples,
            )
        if clock() - started >= timeout_seconds:
            return StpForwardingGate(
                GATE_TIMEOUT, tuple(observed), duration_ms, samples,
            )
        sleeper(interval_seconds)


@dataclass(frozen=True)
class LifecycleMilestone:
    """One ordered fact about WHEN something happened, and on what evidence.

    `observed` is what separates this journal from a plan: a milestone the
    backend never published stays `observed=False` and reads UNOBSERVABLE, which
    is the honest answer for phone boot state on this build.

    `evidence` is what separates the journal from a claim it has not earned.
    An APPLICATION milestone rests on a typed mutation whose runtime answered
    `applied=True`, and the strongest thing that supports is APPLIED: the
    dispatch was accepted.  Whether the backend now holds the intended state is
    a different question asked on a different surface, and only an OBSERVATION
    milestone -- one that read something back -- may answer it VERIFIED.

    The default is deliberately the weaker one.  A milestone added later that
    forgets to say what it rests on claims APPLIED, never VERIFIED.
    """

    sequence: int
    name: str
    observed: bool = False
    detail: str = ""
    evidence: str = APPLICATION

    @property
    def status(self) -> str:
        if not self.observed:
            return UNOBSERVABLE
        return VERIFIED if self.evidence == OBSERVATION else APPLIED

    def as_evidence(self) -> dict:
        """The retained shape, published here so it cannot drift.

        The runner used to rebuild this dict by hand, which is how a field that
        exists in the model can go missing from the artefact the investigation
        is actually read from.
        """
        return {
            "sequence": self.sequence,
            "name": self.name,
            "observed": self.observed,
            "evidence": self.evidence,
            "status": self.status,
            "detail": self.detail,
        }


#: The ordered common Voice foundation, from the phone port outwards.  The
#: walk stops at the FIRST stage that is not VERIFIED and names it; skipping to
#: the symptom furthest downstream is how a shared foundation stays unexamined.
FOUNDATION_STAGES = (
    "PHONE_ACCESS_AND_VOICE_VLAN",
    "SWITCH_TRUNK",
    "ROUTER_VOICE_SUBINTERFACE",
    "DHCP_POOL_TABLE_READBACK",
    "CALL_CONTROL_FOUNDATION",
    "ENDPOINT_DHCP",
    "ENDPOINT_ADDRESS",
    "VOICE_DHCP_BINDING",
    "SCCP_REGISTRATION",
)


@dataclass(frozen=True)
class PositiveVoiceFoundation:
    """What the slice READ about the foundation both sides of the A/B share.

    Every field is a fact about a read, never a substitute for one.  The three
    trunk VLAN dimensions stay apart because IOS prints them as three separate
    sections and they mean three different things: a VLAN may be permitted on a
    trunk, active on it, and still not forwarding.  The router side stays apart
    for the same reason -- a subinterface that exists, one that carries the
    intended address, and one whose line is up are three answers.

    `NOT_AVAILABLE` is not a fourth status: it says no governed read on this
    build reaches that dimension at all, which is a property of the observer.
    """

    trunk_operational: str = UNOBSERVABLE
    trunk_allowed_voice: str = UNOBSERVABLE
    trunk_active_voice: str = UNOBSERVABLE
    trunk_forwarding_voice: str = UNOBSERVABLE
    trunk_native: str = UNOBSERVABLE
    #: The native VLAN as read, kept beside its verdict.  Reported, never
    #: gating: VLAN 930 crosses this trunk tagged, so the native VLAN cannot
    #: explain a voice failure and must not be allowed to mask one.
    trunk_native_vlan: int | None = None
    router_subinterface_present: str = UNOBSERVABLE
    router_subinterface_ipv4: str = UNOBSERVABLE
    router_subinterface_state: str = UNOBSERVABLE
    #: The raw `status/protocol` pair, so a CONTRADICTED line says which one.
    router_subinterface_state_detail: str = ""
    #: The measured global pool table exposes these three dimensions. They stay
    #: independent because presence does not prove the intended range and a
    #: matching range does not prove that any address remains available.
    dhcp_pool_existence: str = UNOBSERVABLE
    dhcp_pool_range: str = UNOBSERVABLE
    dhcp_pool_available_space: str = UNOBSERVABLE
    dhcp_pool_name: str = ""
    dhcp_pool_range_start: str = ""
    dhcp_pool_range_end: str = ""
    dhcp_pool_total_addresses: int | None = None
    dhcp_pool_leased_addresses: int | None = None
    dhcp_pool_excluded_address_count: int | None = None
    dhcp_pool_available_addresses: int | None = None
    #: The table reports only an excluded COUNT. It does not reveal the
    #: configured default-router or excluded ranges, so neither is verified.
    dhcp_pool_default_router: str = NOT_AVAILABLE
    dhcp_pool_exclusions: str = NOT_AVAILABLE
    option150: str = NOT_AVAILABLE
    #: `show telephony-service` does not exist on this build, so the call
    #: control foundation is observed through the one table PT does publish.
    telephony_service: str = NOT_AVAILABLE
    call_control_table: str = UNOBSERVABLE
    call_control_ephone_rows: int | None = None

    @property
    def dhcp_pool_table_readback(self) -> str:
        """The worst of ONLY the three dimensions `show ip dhcp pool` prints.

        This is not "the DHCP pool is configured correctly".  The measured
        table carries no default-router, no excluded RANGES (only a count) and
        no option 150, so VERIFIED here means the pool exists, its range covers
        the intended lease window and addresses remain -- and nothing more.
        """
        return _worst(
            self.dhcp_pool_existence,
            self.dhcp_pool_range,
            self.dhcp_pool_available_space,
        )

    def as_evidence(self) -> dict:
        return {
            "trunk_operational": self.trunk_operational,
            "trunk_allowed_voice": self.trunk_allowed_voice,
            "trunk_active_voice": self.trunk_active_voice,
            "trunk_forwarding_voice": self.trunk_forwarding_voice,
            "trunk_native": self.trunk_native,
            "trunk_native_vlan": self.trunk_native_vlan,
            "router_subinterface_present": self.router_subinterface_present,
            "router_subinterface_ipv4": self.router_subinterface_ipv4,
            "router_subinterface_state": self.router_subinterface_state,
            "router_subinterface_state_detail": self.router_subinterface_state_detail,
            "dhcp_pool_existence": self.dhcp_pool_existence,
            "dhcp_pool_range": self.dhcp_pool_range,
            "dhcp_pool_available_space": self.dhcp_pool_available_space,
            "dhcp_pool_table_readback": self.dhcp_pool_table_readback,
            "dhcp_pool_name": self.dhcp_pool_name,
            "dhcp_pool_range_start": self.dhcp_pool_range_start,
            "dhcp_pool_range_end": self.dhcp_pool_range_end,
            "dhcp_pool_total_addresses": self.dhcp_pool_total_addresses,
            "dhcp_pool_leased_addresses": self.dhcp_pool_leased_addresses,
            "dhcp_pool_excluded_address_count": (
                self.dhcp_pool_excluded_address_count
            ),
            "dhcp_pool_available_addresses": self.dhcp_pool_available_addresses,
            "dhcp_pool_default_router": self.dhcp_pool_default_router,
            "dhcp_pool_exclusions": self.dhcp_pool_exclusions,
            "option150": self.option150,
            "telephony_service": self.telephony_service,
            "call_control_table": self.call_control_table,
            "call_control_ephone_rows": self.call_control_ephone_rows,
        }


@dataclass(frozen=True)
class PositiveVoicePhoneOutcome:
    """The five success dimensions for one phone, each read independently."""

    phone_name: str = ""
    extension: str = ""
    switch_interface: str = ""
    #: The access VLAN this port was ASKED to carry.  Uniform slices ask for
    #: the data VLAN everywhere; the paired A/B asks the intervention port for
    #: the voice VLAN, and every readback below is judged against this value,
    #: so the evidence must carry which half of the experiment it belongs to.
    access_vlan_expected: int = 0
    data_vlan_readback: str = UNOBSERVABLE
    voice_vlan_readback: str = UNOBSERVABLE
    dhcp_enabled: str = UNOBSERVABLE
    #: The FWD-gated experiment's three-part trigger evidence: what the phone's
    #: own SVI reported immediately BEFORE the typed call, whether that call
    #: was accepted, and what the SVI reported immediately AFTER.  All three
    #: remain independent facts; an accepted call and a changed flag are not
    #: an independently observed Cisco 7960 DHCP transaction.
    dhcp_enabled_pre_arm: str = UNOBSERVABLE
    arm_call_accepted: str = UNOBSERVABLE
    dhcp_enabled_post_arm: str = UNOBSERVABLE
    ipv4: str = ""
    #: Did the phone create the SVI the plan addressed it on, and does that SVI
    #: expose an address channel at all?  Both travel with the address, because
    #: an SVI that never existed, one that exists and cannot be asked, and one
    #: that answered "none" are three different findings and all three come
    #: back as the same empty string.
    voice_svi_present: bool = False
    address_channel: bool = False
    #: What the phone itself reports, beside the SVI the plan named.  Never
    #: promoted into `ipv4`: an address the voice SVI does not report is a
    #: finding about where to read, not a phone that acquired on the voice VLAN.
    device_ipv4: str = ""
    registration: str = UNOBSERVABLE
    stp_row_before: str = UNOBSERVABLE
    stp_row_after: str = UNOBSERVABLE
    #: Whether the port announced itself as an edge port, and EVERY raw Type
    #: column that named it -- one per STP instance that printed the port.  The
    #: values are retained because whether this build prints an edge marker at
    #: all has never been measured, and the next reader needs to see what each
    #: column actually said rather than whichever one came first.
    portfast_readback: str = UNOBSERVABLE
    stp_link_types: tuple[str, ...] = ()
    failure_reason: str = ""

    @property
    def ipv4_observed(self) -> bool:
        """An address only counts when it is a real lease, not a placeholder."""
        value = self.ipv4.strip()
        if not value or value in {"0.0.0.0", "<not set>", "unassigned"}:
            return False
        return not value.startswith("169.254.")

    @property
    def addressed(self) -> str:
        if self.ipv4.strip():
            return YES if self.ipv4_observed else NO
        # Nothing came back.  That is a finding about the phone only if
        # something was actually asked: an SVI with no address getter and an
        # SVI that answered "none" both produce the empty string, and only the
        # second one is a phone that did not acquire.
        return NO if self.address_channel else UNOBSERVABLE

    @property
    def succeeded(self) -> bool:
        return (
            self.voice_vlan_readback == VERIFIED
            and self.dhcp_enabled == YES
            and self.ipv4_observed
            and self.registration == REGISTERED
        )

    @property
    def matches_cp_scale_signature(self) -> bool:
        """DHCP enabled, no address, not registered -- the Floor-1 shape.

        Registration is allowed to be UNOBSERVABLE here: CP-SCALE never got far
        enough to read a registration either, and demanding a definite
        NOT_REGISTERED would make the signature unmatchable for the wrong
        reason.
        """
        return (
            self.dhcp_enabled == YES
            and self.addressed == NO
            and self.registration in {NOT_REGISTERED, UNOBSERVABLE}
        )


@dataclass(frozen=True)
class PositiveVoiceSliceResult:
    """Everything the positive control observed, with nothing collapsed."""

    router_model: str = ""
    switch_model: str = ""
    phone_model: str = ""
    router_name: str = ""
    switch_name: str = ""
    voice_vlan_id: int = VOICE_VLAN_ID
    phones: tuple[PositiveVoicePhoneOutcome, ...] = ()
    lifecycle: tuple[LifecycleMilestone, ...] = ()
    #: Read-only foundation evidence.  It localises the outcome; it never
    #: participates in computing it.
    foundation: PositiveVoiceFoundation = field(
        default_factory=PositiveVoiceFoundation,
    )
    #: `show ip dhcp binding` rows whose address falls in the voice pool.  None
    #: means the table was never read, which is not the same as zero rows.
    voice_binding_count: int | None = None
    #: Whether the phone-facing edge policy was applied.  In the baseline this
    #: is a recorded fact and never a knob turned to obtain a better outcome; in
    #: the causal A/B it is the ONE declared variable, and it is derived from
    #: the milestone rather than set beside it so the two cannot disagree.
    portfast: str = PORTFAST_NOT_APPLIED
    #: And whether anything independently SAW it.  APPLIED is the mutation
    #: being accepted; this is the switch saying so on its own surface.
    portfast_readback: str = UNOBSERVABLE
    realtime_before: bool = False
    realtime_after: bool = False
    #: Which experiment this result belongs to, and -- for the FWD-gated one --
    #: whether the acquisition was ever triggered.  A gated run that stopped at
    #: an unmet precondition reads its named boundary here instead of letting
    #: never-asked phones masquerade as another SAME_FAILURE.
    experiment: str = EXPERIMENT_UNIFORM_BASELINE
    stp_gate: StpForwardingGate | None = None
    acquisition_started: bool = True
    acquisition_boundary: str = ""
    baseline_inventory: PhysicalWorkspaceObservation | None = None
    final_inventory: PhysicalWorkspaceObservation | None = None
    workspace_restored: bool = False
    realtime_restored: bool = False
    owned_links: tuple[str, ...] = ()
    removed: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()

    @property
    def foundation_ladder(self) -> tuple[tuple[str, str], ...]:
        """Every stage from the phone port to registration, in path order.

        The whole ladder is published, not just the boundary: a stage that was
        never reached still has an answer, and hiding the downstream stages
        behind the first gap would lose the symptoms already measured.
        """
        foundation = self.foundation
        return tuple(zip(FOUNDATION_STAGES, (
            _worst(
                *(item.data_vlan_readback for item in self.phones),
                *(item.voice_vlan_readback for item in self.phones),
            ),
            _worst(
                foundation.trunk_operational,
                foundation.trunk_allowed_voice,
                foundation.trunk_active_voice,
                foundation.trunk_forwarding_voice,
            ),
            _worst(
                foundation.router_subinterface_present,
                foundation.router_subinterface_ipv4,
                foundation.router_subinterface_state,
            ),
            foundation.dhcp_pool_table_readback,
            foundation.call_control_table,
            _worst(*(
                _as_status(item.dhcp_enabled, YES, NO) for item in self.phones
            )),
            _worst(*(
                _as_status(item.addressed, YES, NO) for item in self.phones
            )),
            _as_status(self.voice_bindings_observed, YES, NO),
            _worst(*(
                _as_status(item.registration, REGISTERED, NOT_REGISTERED)
                for item in self.phones
            )),
        )))

    @property
    def first_boundary_stage(self) -> str:
        """The first stage that is not VERIFIED, or empty when none is."""
        for stage, status in self.foundation_ladder:
            if status != VERIFIED:
                return stage
        return ""

    @property
    def first_boundary_status(self) -> str:
        for _, status in self.foundation_ladder:
            if status != VERIFIED:
                return status
        return VERIFIED

    @property
    def voice_bindings_observed(self) -> str:
        if self.voice_binding_count is None:
            return UNOBSERVABLE
        return YES if self.voice_binding_count > 0 else NO

    @property
    def all_endpoint_arms_accepted(self) -> str:
        """Aggregate typed-call acceptance without hiding per-phone answers."""
        if not self.phones:
            return UNOBSERVABLE
        answers = {item.arm_call_accepted for item in self.phones}
        if answers == {YES}:
            return YES
        if NO in answers:
            return NO
        return UNOBSERVABLE

    @property
    def dhcp_flag_transition(self) -> str:
        """Observed phone-flag transition, deliberately short of DORA proof."""
        if not self.phones:
            return UNOBSERVABLE
        pairs = {
            (item.dhcp_enabled_pre_arm, item.dhcp_enabled_post_arm)
            for item in self.phones
        }
        if pairs == {(NO, YES)}:
            return DHCP_FLAG_TRANSITION_OBSERVED_OFF_TO_ON
        if any(UNOBSERVABLE in pair for pair in pairs):
            return UNOBSERVABLE
        return DHCP_FLAG_TRANSITION_NOT_OBSERVED

    @property
    def dhcp_flag_transition_valid_for_experiment(self) -> str:
        """Whether every phone established PRE NO + accepted + POST YES."""
        transition = self.dhcp_flag_transition
        accepted = self.all_endpoint_arms_accepted
        if (
            transition == DHCP_FLAG_TRANSITION_OBSERVED_OFF_TO_ON
            and accepted == YES
        ):
            return YES
        if transition == DHCP_FLAG_TRANSITION_NOT_OBSERVED or accepted == NO:
            return NO
        return UNOBSERVABLE

    @property
    def fresh_7960_dhcp_transaction(self) -> str:
        """The flag surface cannot independently establish a 7960 DORA run."""
        return FRESH_7960_DHCP_TRANSACTION_NOT_INDEPENDENTLY_ESTABLISHED

    @property
    def outcome(self) -> str:
        """The decision matrix, computed from independent facts only.

        SUCCESS demands every dimension on every phone AND a voice binding on
        the server.  A phone that reports an address while the server shows no
        binding is not a success; it is a disagreement worth seeing.
        """
        if not self.phones:
            return UNOBSERVABLE
        if not self.acquisition_started:
            # A window that never opened judged nobody: phones that were never
            # asked to acquire are not phones that failed to, and reading their
            # idle surfaces as a failure would be exactly the ambiguous
            # SAME_FAILURE the fail-closed boundaries exist to prevent.
            return UNOBSERVABLE
        if not self.realtime_before or not self.realtime_after:
            # Addressing judged outside Realtime is not judged at all.
            return UNOBSERVABLE
        # The server-side binding table is a dimension like any other: unread
        # is UNOBSERVABLE, and only a table that was actually read can confirm
        # or contradict what the phones reported.
        if all(item.succeeded for item in self.phones):
            if self.voice_binding_count is None:
                return UNOBSERVABLE
            return SUCCESS if self.voice_binding_count > 0 else DIFFERENT_FAILURE
        if all(item.matches_cp_scale_signature for item in self.phones):
            if self.voice_binding_count is None:
                return UNOBSERVABLE
            return SAME_FAILURE if self.voice_binding_count == 0 else DIFFERENT_FAILURE
        # UNKNOWN fails closed in BOTH directions.  A phone whose decisive
        # dimensions were never read has not succeeded, but it has not been
        # shown to fail either, and calling it DIFFERENT_FAILURE would invent a
        # divergence out of a missing observation.
        if any(
            item.dhcp_enabled == UNOBSERVABLE
            or item.addressed == UNOBSERVABLE
            or item.registration == UNOBSERVABLE
            for item in self.phones
        ):
            return UNOBSERVABLE
        return DIFFERENT_FAILURE

    @property
    def stp_phone_row_after(self) -> str:
        """One classification for the phone-facing rows under the voice VLAN."""
        rows = {item.stp_row_after for item in self.phones}
        if not rows:
            return UNOBSERVABLE
        if len(rows) == 1:
            return rows.pop()
        # Disagreeing rows are not averaged into a verdict.
        return "MIXED"

    @property
    def causal_experiment_result(self) -> str:
        """The CAUSAL verdict, kept apart from the endpoint outcome above.

        Run 9 is why these are two fields: its VOICE endpoint outcome was
        SAME_FAILURE while its causal result was PARTIAL_OR_DIVERGENT, and one
        name for both is how a boundary gets read as a refutation.  Only the
        FWD-gated experiment computes a verdict here; every other run answers
        NOT_FWD_GATED, because without the gate the trigger's freshness and
        the port's forwarding state are exactly the unproven premises.
        """
        if self.experiment != EXPERIMENT_PAIRED_ACCESS_VLAN_FWD_GATED:
            return "NOT_FWD_GATED"
        if self.acquisition_boundary == (
            ACQUISITION_NOT_STARTED_STP_PRECONDITION_UNMET
        ):
            return "STP_PRECONDITION_NOT_ESTABLISHED"
        if self.acquisition_boundary == (
            ACQUISITION_NOT_STARTED_FRESH_DHCP_TRIGGER_UNPROVEN
        ):
            return "FRESH_DHCP_TRIGGER_UNPROVEN"
        if self.stp_gate is None or not self.stp_gate.forwarding_observed:
            return "STP_PRECONDITION_NOT_ESTABLISHED"
        if self.dhcp_flag_transition_valid_for_experiment != YES:
            return "FRESH_DHCP_TRIGGER_UNPROVEN"
        control = [
            item for item in self.phones
            if item.access_vlan_expected == DATA_VLAN_ID
        ]
        intervention = [
            item for item in self.phones
            if item.access_vlan_expected == VOICE_VLAN_ID
        ]
        if not control or not intervention:
            return UNOBSERVABLE

        def addressed(group: list) -> str:
            answers = {item.addressed for item in group}
            if answers == {YES}:
                return YES
            if answers == {NO}:
                return NO
            return UNOBSERVABLE

        control_addressed = addressed(control)
        intervention_addressed = addressed(intervention)
        if UNOBSERVABLE in (control_addressed, intervention_addressed):
            return "PARTIAL_OR_DIVERGENT"
        if control_addressed == NO and intervention_addressed == YES:
            return "ACCESS_VLAN_DHCP_CAUSAL_EFFECT_OBSERVED"
        if control_addressed == NO and intervention_addressed == NO:
            return "NO_ADDRESS_AFTER_FWD_AND_DHCP_FLAG_TRANSITION"
        if control_addressed == YES and intervention_addressed == YES:
            return "RUN9_FAILURE_NOT_REPRODUCED"
        return "OBSERVED_REVERSED_ADDRESS_OUTCOME"


class VoicePhysicalRuntime(Protocol):
    def observe_workspace(self) -> PhysicalWorkspaceObservation: ...
    def ensure_device(self, device: DevicePlan) -> PhysicalMutationResult: ...
    def observe_device(self, device: DevicePlan): ...
    def remove_device(self, device: DevicePlan) -> PhysicalMutationResult: ...
    def ensure_link(self, link: LinkPlan) -> PhysicalMutationResult: ...


class VoiceConfigurationRuntime(Protocol):
    def apply_actions(self, actions) -> list[RuntimeActionMutation]: ...
    def read_access_port(
        self, device_name: str, interface: str, expected_access_vlan: int,
    ): ...
    def read_spanning_tree(self, device_name: str): ...
    def read_dhcp_bindings(self, device_name: str): ...


class VoiceFoundationConfigurationRuntime(Protocol):
    """OPTIONAL read-only extension of `VoiceConfigurationRuntime`.

    Separate on purpose: a runtime that does not publish these has not failed,
    it simply exposes no such surface, and every dimension behind it reads
    UNOBSERVABLE without an error being invented for it.
    """

    def read_trunk(self, device_name: str, interface: str): ...
    def read_interface_addresses(self, device_name: str) -> list | None: ...
    def read_dhcp_pool(
        self, device_name: str, pool_name: str, lease_start: str, lease_end: str,
    ): ...


class VoiceCallControlRuntime(Protocol):
    def apply_actions(self, actions) -> list[RuntimeActionMutation]: ...
    def observe_registrations(self, expectations) -> list: ...


class VoiceFoundationCallControlRuntime(Protocol):
    """OPTIONAL read-only extension of `VoiceCallControlRuntime`."""

    def inspect_call_control(self, device_name: str) -> dict: ...


class VoiceControlPlaneRuntime(Protocol):
    """OPTIONAL typed control-plane runtime.  Only the intervention needs it.

    The baseline half of the A/B never calls this, and asking for the
    intervention without it is refused rather than silently downgraded: a run
    that reported PortFast while quietly applying none would poison the only
    comparison this experiment exists to make.
    """

    def apply_actions(self, actions) -> list[RuntimeActionMutation]: ...


class VoiceEndpointRuntime(Protocol):
    def configure_endpoint_dhcp(self, device_name: str, interface: str) -> bool: ...
    def read_endpoint_address(self, device_name: str, interface: str): ...


class VoiceModeRuntime(Protocol):
    def read_simulation_state(self): ...
    def set_simulation_mode(self, on: bool): ...


@dataclass
class _Journal:
    """Monotonic lifecycle recorder.  Order is the evidence."""

    entries: list[LifecycleMilestone] = field(default_factory=list)

    def record(
        self,
        name: str,
        observed: bool = False,
        detail: str = "",
        evidence: str = APPLICATION,
    ) -> None:
        self.entries.append(
            LifecycleMilestone(
                sequence=len(self.entries) + 1,
                name=name,
                observed=observed,
                detail=detail,
                evidence=evidence,
            )
        )

    def frozen(self) -> tuple[LifecycleMilestone, ...]:
        return tuple(self.entries)


def _bind_action_id(extension: str) -> str:
    return f"{CALL_CONTROL_ID}/bind/{extension}"


def _mutation_applied(result) -> bool:
    """Did the typed runtime state that this mutation was applied?

    `applied` is the field `PhysicalMutationResult` and `RuntimeActionMutation`
    both publish, and it is read with NO fail-open default.  A result that does
    not carry it has stated nothing, and a result that carries some other,
    older flag has still not stated this one: only `applied` decides.
    """
    return bool(getattr(result, "applied", False))


def _worst(*statuses: str) -> str:
    """CONTRADICTED beats UNOBSERVABLE beats VERIFIED, and nothing is VERIFIED
    by omission: an empty set of dimensions has established nothing."""
    values = [item for item in statuses]
    if CONTRADICTED in values:
        return CONTRADICTED
    if values and all(item == VERIFIED for item in values):
        return VERIFIED
    return UNOBSERVABLE


def _as_status(value: str, positive: str, negative: str) -> str:
    """Map one already-measured field onto the three-way ladder vocabulary."""
    if value == positive:
        return VERIFIED
    if value == negative:
        return CONTRADICTED
    return UNOBSERVABLE


def _vlan_section(section, vlan_id: int) -> str:
    """`None` is the IOS section never printing; `()` is it printing nothing.

    Only the second is a statement about the trunk.  Collapsing them would turn
    a capture that stopped short into a VLAN that is not carried, which is the
    exact shape of finding this A/B is trying to locate honestly.
    """
    if section is None:
        return UNOBSERVABLE
    return VERIFIED if vlan_id in tuple(section) else CONTRADICTED


def _classify_trunk(observation) -> dict:
    """Five independent answers from ONE fresh and complete trunk read."""
    unread = {
        "trunk_operational": UNOBSERVABLE,
        "trunk_allowed_voice": UNOBSERVABLE,
        "trunk_active_voice": UNOBSERVABLE,
        "trunk_forwarding_voice": UNOBSERVABLE,
        "trunk_native": UNOBSERVABLE,
        "trunk_native_vlan": None,
    }
    if observation is None:
        return unread
    if not (
        getattr(observation, "fresh_evidence", False)
        and getattr(observation, "output_complete", False)
    ):
        return unread
    native = getattr(observation, "native_vlan", None)
    try:
        native_status = (
            UNOBSERVABLE if native is None
            else (VERIFIED if int(native) == TRUNK_NATIVE_VLAN_ID else CONTRADICTED)
        )
    except (TypeError, ValueError):
        native, native_status = None, UNOBSERVABLE
    return {
        # A fresh complete table that did not carry the uplink row states that
        # the uplink is not trunking; the row's absence IS the answer here.
        "trunk_operational": (
            VERIFIED
            if str(getattr(observation, "status", "") or "").casefold() == "trunking"
            else CONTRADICTED
        ),
        "trunk_allowed_voice": _vlan_section(
            getattr(observation, "allowed_vlans", None), VOICE_VLAN_ID,
        ),
        "trunk_active_voice": _vlan_section(
            getattr(observation, "active_vlans", None), VOICE_VLAN_ID,
        ),
        "trunk_forwarding_voice": _vlan_section(
            getattr(observation, "forwarding_vlans", None), VOICE_VLAN_ID,
        ),
        "trunk_native": native_status,
        "trunk_native_vlan": native,
    }


def _classify_router_subinterface(rows) -> dict:
    """`None` rows mean the table was never read -- never that it was empty."""
    if rows is None:
        return {
            "router_subinterface_present": UNOBSERVABLE,
            "router_subinterface_ipv4": UNOBSERVABLE,
            "router_subinterface_state": UNOBSERVABLE,
            "router_subinterface_state_detail": "",
        }
    row = next((
        item for item in rows
        if same_interface_name(
            str(getattr(item, "interface", "") or ""), ROUTER_VOICE_SUBINTERFACE,
        )
    ), None)
    if row is None:
        # The table WAS read and the subinterface was not in it.  That is a
        # finding about the router, and it is the only way to reach one here.
        return {
            "router_subinterface_present": CONTRADICTED,
            "router_subinterface_ipv4": UNOBSERVABLE,
            "router_subinterface_state": UNOBSERVABLE,
            "router_subinterface_state_detail": "",
        }
    address = str(getattr(row, "ip_address", "") or "").strip()
    status = str(getattr(row, "status", "") or "").strip()
    protocol = str(getattr(row, "protocol", "") or "").strip()
    detail = f"{status}/{protocol}" if status or protocol else ""
    return {
        "router_subinterface_present": VERIFIED,
        # An empty address column is a column nobody read, not an interface
        # without an address; `show ip interface brief` prints `unassigned`.
        "router_subinterface_ipv4": (
            UNOBSERVABLE if not address
            else (VERIFIED if address == VOICE_GATEWAY else CONTRADICTED)
        ),
        "router_subinterface_state": (
            UNOBSERVABLE if not detail
            else (
                VERIFIED
                if status.casefold() == "up" and protocol.casefold() == "up"
                else CONTRADICTED
            )
        ),
        "router_subinterface_state_detail": detail,
    }


def _classify_dhcp_pool(observation) -> dict:
    """Map only the three dimensions the measured pool table exposes."""
    unread = {
        "dhcp_pool_existence": UNOBSERVABLE,
        "dhcp_pool_range": UNOBSERVABLE,
        "dhcp_pool_available_space": UNOBSERVABLE,
        "dhcp_pool_name": "",
        "dhcp_pool_range_start": "",
        "dhcp_pool_range_end": "",
        "dhcp_pool_total_addresses": None,
        "dhcp_pool_leased_addresses": None,
        "dhcp_pool_excluded_address_count": None,
        "dhcp_pool_available_addresses": None,
    }
    if observation is None or not (
        getattr(observation, "fresh_evidence", False)
        and getattr(observation, "output_complete", False)
        and getattr(observation, "identity_confirmed", False)
    ):
        return unread
    present = getattr(observation, "pool_present", None)
    if present is False:
        return {
            **unread,
            "dhcp_pool_existence": CONTRADICTED,
            "dhcp_pool_name": str(
                getattr(observation, "requested_pool_name", "") or ""
            ),
        }
    if present is not True:
        return unread

    range_covered = getattr(observation, "requested_range_covered", None)
    available = getattr(observation, "available_addresses", None)
    if isinstance(available, bool):
        available = None
    return {
        "dhcp_pool_existence": VERIFIED,
        "dhcp_pool_range": (
            VERIFIED if range_covered is True
            else CONTRADICTED if range_covered is False
            else UNOBSERVABLE
        ),
        "dhcp_pool_available_space": (
            VERIFIED if isinstance(available, int) and available > 0
            else CONTRADICTED if isinstance(available, int) and available == 0
            else UNOBSERVABLE
        ),
        "dhcp_pool_name": str(
            getattr(observation, "requested_pool_name", "") or ""
        ),
        "dhcp_pool_range_start": str(
            getattr(observation, "range_start", "") or ""
        ),
        "dhcp_pool_range_end": str(
            getattr(observation, "range_end", "") or ""
        ),
        "dhcp_pool_total_addresses": getattr(
            observation, "total_addresses", None,
        ),
        "dhcp_pool_leased_addresses": getattr(
            observation, "leased_addresses", None,
        ),
        "dhcp_pool_excluded_address_count": getattr(
            observation, "excluded_addresses", None,
        ),
        "dhcp_pool_available_addresses": available,
    }


def _classify_call_control(table) -> tuple[str, int | None]:
    """The one call-control surface PT 9.0.1 publishes, judged as a read.

    VERIFIED here says the table exists and was read whole -- the foundation
    answered.  It deliberately does NOT say a phone registered: that is a
    per-phone fact with its own field.  An empty row list is reported as a
    count, not promoted into "CME is absent": what an unregistered ephone block
    looks like on this build has not been measured.
    """
    if not isinstance(table, dict):
        return UNOBSERVABLE, None
    if not (
        table.get("executed")
        and table.get("fresh_output_observed")
        and table.get("output_complete")
    ):
        return UNOBSERVABLE, None
    rows = table.get("ephones")
    if not isinstance(rows, (list, tuple)):
        return UNOBSERVABLE, None
    return VERIFIED, len(rows)


#: The Type column saying edge, as a WORD.  A longer token that merely contains
#: those four letters is not this build announcing an edge port.
_EDGE_MARKER = re.compile(r"(?i)\bedge\b")


def _classify_edge_marker(
    instances, interface: str,
) -> tuple[tuple[str, ...], str]:
    """Did the port announce itself as an edge port, in ANY STP instance?

    Being an edge port is a property of the PORT, and `show spanning-tree`
    prints one row per VLAN instance.  So EVERY instance is searched and every
    row that names this interface is kept -- not the first.  Answering from the
    first row let a data-VLAN column reading `P2p` speak for a voice-VLAN column
    reading `P2p Edge` that was never looked at.

    VERIFIED needs the marker on at least one of those rows.  Its absence from
    all of them is UNOBSERVABLE and never CONTRADICTED: nobody has measured this
    build printing an edge marker at all, so a Type column without one cannot
    separate "PortFast is off" from "this IOS does not say".  Every raw column
    value is returned beside the verdict so the next reader can judge that.
    """
    if instances is None:
        return (), UNOBSERVABLE
    observed: list[str] = []
    for instance in instances:
        for row in getattr(instance, "interfaces", ()):
            if not same_interface_name(getattr(row, "interface", ""), interface):
                continue
            observed.append(str(getattr(row, "link_type", "") or ""))
    if not observed:
        return (), UNOBSERVABLE
    verified = any(_EDGE_MARKER.search(item) for item in observed)
    return tuple(observed), (VERIFIED if verified else UNOBSERVABLE)


def _classify_stp_row(instances, vlan_id: int, interface: str) -> str:
    """FORWARDING / BLOCKING / ABSENT / UNOBSERVABLE for one phone port.

    An instance that was never read is UNOBSERVABLE.  An instance that was read
    and simply has no row for this port is ABSENT.  Those are different facts,
    and collapsing them is exactly how CP-SCALE's missing VLAN20 rows would turn
    into an STP block that nobody measured.
    """
    if instances is None:
        return UNOBSERVABLE
    for instance in instances:
        if getattr(instance, "vlan_id", None) != vlan_id:
            continue
        for row in getattr(instance, "interfaces", ()):
            # IOS prints `Fa0/1` where the plan says `FastEthernet0/1`.  A raw
            # comparison turns every read row into ABSENT, and ABSENT is one of
            # the two facts this A/B turns on.
            if not same_interface_name(getattr(row, "interface", ""), interface):
                continue
            state = str(getattr(row, "state", "")).upper()
            if state.startswith("FWD") or state.startswith("FORW"):
                return FORWARDING
            if state.startswith("BLK") or state.startswith("BLOCK"):
                return BLOCKING
            return state or UNOBSERVABLE
        return ABSENT
    return ABSENT


class PositiveVoiceSliceQualifier:
    """Builds the disposable slice, reads the five dimensions, and cleans up."""

    def __init__(
        self,
        physical: VoicePhysicalRuntime,
        configuration: VoiceConfigurationRuntime,
        call_control: VoiceCallControlRuntime,
        endpoints: VoiceEndpointRuntime,
        mode: VoiceModeRuntime,
        *,
        token: str = "",
        phone_count: int = 2,
        control_plane: VoiceControlPlaneRuntime | None = None,
        edge_portfast: bool = False,
        phone_access_vlans: tuple[int, ...] | None = None,
        fwd_gated_fresh_dhcp: bool = False,
        gate_timeout_seconds: float = STP_FWD_GATE_TIMEOUT_SECONDS,
        gate_interval_seconds: float = STP_FWD_GATE_INTERVAL_SECONDS,
        gate_clock=monotonic,
        gate_sleeper=sleep,
    ) -> None:
        self._physical = physical
        self._configuration = configuration
        self._call_control = call_control
        self._endpoints = endpoints
        self._mode = mode
        self._token = token or secrets.token_hex(3)
        self._phone_count = phone_count
        self._control_plane = control_plane
        self._edge_portfast = bool(edge_portfast)
        # The paired access-VLAN causal control: one access VLAN per phone
        # port, in port order.  The default keeps every port on the data VLAN,
        # which is byte-for-byte the run-8 experiment.  A mapping may only use
        # the two VLANs this slice creates -- anything else would ride on a
        # VLAN that does not exist and turn the A/B into a different topology.
        if phone_access_vlans is None:
            self._phone_access_vlans = (DATA_VLAN_ID,) * phone_count
        else:
            if len(phone_access_vlans) != phone_count:
                raise ValueError(
                    "The paired experiment names one access VLAN per phone: "
                    f"got {len(phone_access_vlans)} for {phone_count} phones."
                )
            for vlan_id in phone_access_vlans:
                if vlan_id not in (DATA_VLAN_ID, VOICE_VLAN_ID):
                    raise ValueError(
                        f"Access VLAN {vlan_id} does not exist in this slice; "
                        f"only {DATA_VLAN_ID} and {VOICE_VLAN_ID} are created."
                    )
            self._phone_access_vlans = tuple(phone_access_vlans)
        # The FWD-gated fresh-DHCP experiment.  It is defined ON the paired
        # mapping -- the gate watches THE port whose access VLAN is the voice
        # VLAN -- and it changes exactly one lifecycle fact: when the phones
        # are asked to acquire.  PortFast beside it would be a second variable.
        self._fwd_gated = bool(fwd_gated_fresh_dhcp)
        if self._fwd_gated:
            if self._phone_access_vlans.count(VOICE_VLAN_ID) != 1:
                raise ValueError(
                    "The FWD-gated experiment needs the paired mapping: "
                    "exactly one phone port carries the voice VLAN as its "
                    "access VLAN, and that port is what the gate watches."
                )
            if self._edge_portfast:
                raise ValueError(
                    "one causal variable per run: the FWD gate and edge "
                    "PortFast cannot be combined"
                )
        self._gate_timeout_seconds = gate_timeout_seconds
        self._gate_interval_seconds = gate_interval_seconds
        self._gate_clock = gate_clock
        self._gate_sleeper = gate_sleeper
        # Derived once, next to the knobs that define it, so a result can name
        # its experiment without re-deriving it from the mapping later.
        if self._fwd_gated:
            self._experiment = EXPERIMENT_PAIRED_ACCESS_VLAN_FWD_GATED
        elif VOICE_VLAN_ID in self._phone_access_vlans:
            self._experiment = EXPERIMENT_PAIRED_ACCESS_VLAN
        else:
            self._experiment = EXPERIMENT_UNIFORM_BASELINE

    def _name(self, suffix: str) -> str:
        return f"{POSITIVE_VOICE_PREFIX}{self._token}_{suffix}"

    def qualify(
        self,
        router_model: str,
        switch_model: str,
        phone_model: str,
        *,
        require_empty_workspace: bool = True,
    ) -> PositiveVoiceSliceResult:
        errors: list[str] = []
        try:
            baseline = self._physical.observe_workspace()
        except Exception as exc:  # noqa: BLE001
            return PositiveVoiceSliceResult(
                router_model=router_model, switch_model=switch_model,
                phone_model=phone_model,
                errors=(f"Read-only workspace inventory failed: {exc}",),
            )
        if require_empty_workspace and not baseline.safe_for_disposable_mutation:
            return PositiveVoiceSliceResult(
                router_model=router_model, switch_model=switch_model,
                phone_model=phone_model, baseline_inventory=baseline,
                errors=(
                    "The workspace inventory is not a complete empty baseline "
                    f"(observed={baseline.observed}, "
                    f"semantic_devices={len(baseline.semantic_devices)}, "
                    f"links={len(baseline.links)}); the positive Voice slice "
                    "refuses to mutate a workspace it did not find empty.",
                ),
            )

        journal = _Journal()
        created: list[DevicePlan] = []
        owned_links: list[str] = []
        phones: tuple[PositiveVoicePhoneOutcome, ...] = ()
        binding_count: int | None = None
        realtime_before = realtime_after = False
        original_simulation: bool | None = None
        foundation = PositiveVoiceFoundation()
        stp_gate: StpForwardingGate | None = None
        acquisition_boundary = ""
        try:
            (
                original_simulation, phones, binding_count,
                realtime_before, realtime_after, foundation,
                stp_gate, acquisition_boundary, measured_errors,
            ) = self._measure(
                router_model, switch_model, phone_model,
                created, owned_links, journal,
            )
            errors.extend(measured_errors)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"positive_voice_raised: {type(exc).__name__}: {exc}")
        finally:
            realtime_restored, restore_errors = self._restore_mode(original_simulation)
            errors.extend(restore_errors)
            removed, cleanup_errors, final, restored = self._cleanup(created, baseline)
            errors.extend(cleanup_errors)

        # Derived from the milestone, never set beside it: a `portfast` field
        # and a journal that disagreed would be exactly the kind of two-sourced
        # claim this qualification refuses everywhere else.
        portfast = (
            PORTFAST_APPLIED
            if any(
                item.name == "WHEN_EDGE_PORTFAST_APPLIED" and item.observed
                for item in journal.entries
            )
            else PORTFAST_NOT_APPLIED
        )
        return PositiveVoiceSliceResult(
            router_model=router_model, switch_model=switch_model,
            phone_model=phone_model,
            router_name=self._name("R"), switch_name=self._name("SW"),
            phones=phones, lifecycle=journal.frozen(),
            foundation=foundation, portfast=portfast,
            portfast_readback=_worst(*(
                item.portfast_readback for item in phones
            )),
            voice_binding_count=binding_count,
            realtime_before=realtime_before, realtime_after=realtime_after,
            experiment=self._experiment,
            stp_gate=stp_gate,
            acquisition_started=not acquisition_boundary,
            acquisition_boundary=acquisition_boundary,
            baseline_inventory=baseline, final_inventory=final,
            workspace_restored=restored, realtime_restored=realtime_restored,
            owned_links=tuple(owned_links), removed=tuple(removed),
            errors=tuple(errors),
        )

    def _restore_mode(self, original: bool | None) -> tuple[bool, list[str]]:
        """Realtime is the authoritative window; leaving Simulation on is a leak."""
        if original is None:
            return True, []
        try:
            self._mode.set_simulation_mode(bool(original))
        except Exception as exc:  # noqa: BLE001
            return False, [f"mode_restore_failed: {exc}"]
        return True, []

    def _cleanup(self, created, baseline):
        removed: list[str] = []
        errors: list[str] = []
        for device in reversed(created):
            try:
                self._physical.remove_device(device)
                removed.append(device.name)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"cleanup_failed:{device.name}: {exc}")
        final = None
        restored = False
        try:
            final = self._physical.observe_workspace()
            restored = physical_workspace_restoration_matches(baseline, final)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"final_inventory_failed: {exc}")
        return removed, errors, final, restored

    # ------------------------------------------------------------------
    # Plan construction.  Every action is a typed production action; this
    # module adds no primitive of its own.
    # ------------------------------------------------------------------

    def _switch_interface(self, position: int) -> str:
        return f"FastEthernet0/{position}"

    def _configuration_actions(self, phone_ports: tuple[str, ...]) -> list:
        from ...domain.enterprise.models.configuration import (
            AddressRange,
            ConfigureAccessPort,
            ConfigureDhcpPool,
            ConfigureSubinterface,
            ConfigureTrunk,
            ConfigurationPhase,
            CreateVlan,
        )

        switch = self._name("SW")
        router = self._name("R")
        site = "voiceab"
        actions: list = [
            CreateVlan(
                id="voiceab/vlan/data", phase=ConfigurationPhase.L2_DEFINITIONS,
                device_id="voiceab/sw", device_name=switch, site_id=site,
                vlan_id=DATA_VLAN_ID, name="VOICEAB_DATA",
            ),
            CreateVlan(
                id="voiceab/vlan/voice", phase=ConfigurationPhase.L2_DEFINITIONS,
                device_id="voiceab/sw", device_name=switch, site_id=site,
                vlan_id=VOICE_VLAN_ID, name="VOICEAB_VOICE",
            ),
            ConfigureTrunk(
                id="voiceab/trunk/uplink", phase=ConfigurationPhase.L2_INTERFACES,
                device_id="voiceab/sw", device_name=switch, site_id=site,
                interface=SWITCH_UPLINK_INTERFACE,
                allowed_vlans=[DATA_VLAN_ID, VOICE_VLAN_ID],
                native_vlan_id=TRUNK_NATIVE_VLAN_ID,
            ),
        ]
        for index, interface in enumerate(phone_ports, start=1):
            actions.append(
                ConfigureAccessPort(
                    id=f"voiceab/access/{index}",
                    phase=ConfigurationPhase.L2_INTERFACES,
                    device_id="voiceab/sw", device_name=switch, site_id=site,
                    interface=interface,
                    data_vlan_id=self._phone_access_vlans[index - 1],
                    voice_vlan_id=VOICE_VLAN_ID,
                )
            )
        actions.extend([
            ConfigureSubinterface(
                id="voiceab/sub/data", phase=ConfigurationPhase.L3_INTERFACES,
                device_id="voiceab/r", device_name=router, site_id=site,
                parent_interface=ROUTER_UPLINK_INTERFACE, vlan_id=DATA_VLAN_ID,
                ipv4=DATA_GATEWAY, prefix=VOICE_PREFIX, netmask=VOICE_NETMASK,
                segment_id="voiceab/seg/data",
            ),
            ConfigureSubinterface(
                id="voiceab/sub/voice", phase=ConfigurationPhase.L3_INTERFACES,
                device_id="voiceab/r", device_name=router, site_id=site,
                parent_interface=ROUTER_UPLINK_INTERFACE, vlan_id=VOICE_VLAN_ID,
                ipv4=VOICE_GATEWAY, prefix=VOICE_PREFIX, netmask=VOICE_NETMASK,
                segment_id="voiceab/seg/voice",
            ),
            ConfigureDhcpPool(
                id="voiceab/pool/voice", phase=ConfigurationPhase.SERVICES,
                device_id="voiceab/r", device_name=router, site_id=site,
                pool_name=VOICE_POOL_NAME, segment_id="voiceab/seg/voice",
                network=VOICE_NETWORK, prefix=VOICE_PREFIX,
                netmask=VOICE_NETMASK, gateway=VOICE_GATEWAY,
                excluded_ranges=[AddressRange(start=VOICE_GATEWAY, end="10.93.0.9")],
                lease_start=VOICE_LEASE_START, lease_end=VOICE_LEASE_END,
            ),
        ])
        return actions

    def _voice_actions(self) -> list:
        from ...domain.enterprise.models.voice_plan import (
            ConfigureCallControlSource,
            BindPhoneToExtension,
            ConfigureVoiceDhcpOption,
            CreateExtension,
            EnableCallControl,
            GeneratePhoneConfigurationFiles,
            VoiceCapabilityDimension,
            VoicePhase,
        )

        router = self._name("R")
        common = {
            "call_control_id": CALL_CONTROL_ID,
            "host_device_id": "voiceab/r",
            "host_device_name": router,
            "host_model": self._router_model,
            "site_id": "voiceab",
        }
        actions: list = [
            # Option 150 is a DHCP-pool attribute, so it is named against the
            # pool the configuration stage already created.
            ConfigureVoiceDhcpOption(
                id="voiceab/option150", phase=VoicePhase.CALL_CONTROL,
                required_capability=VoiceCapabilityDimension.VOICE_DHCP_OPTIONS,
                pool_name=VOICE_POOL_NAME, tftp_address=VOICE_GATEWAY,
                source_configuration_action_id="voiceab/sub/voice", **common,
            ),
            ConfigureCallControlSource(
                id="voiceab/cme/source", phase=VoicePhase.CALL_CONTROL,
                required_capability=VoiceCapabilityDimension.CALL_CONTROL_CONFIG,
                source_address=VOICE_GATEWAY, signaling_port=2000,
                source_configuration_action_id="voiceab/sub/voice", **common,
            ),
            EnableCallControl(
                id="voiceab/cme/enable", phase=VoicePhase.CALL_CONTROL,
                required_capability=VoiceCapabilityDimension.CALL_CONTROL_CONFIG,
                max_phones=self._phone_count, max_extensions=self._phone_count,
                **common,
            ),
        ]
        for index, extension in enumerate(EXTENSIONS[: self._phone_count], start=1):
            actions.append(
                CreateExtension(
                    id=f"voiceab/cme/ext/{extension}", phase=VoicePhase.EXTENSIONS,
                    required_capability=(
                        VoiceCapabilityDimension.PHONE_EXTENSION_CONFIG
                    ),
                    extension=extension, directory_index=index, **common,
                )
            )
        for index, extension in enumerate(EXTENSIONS[: self._phone_count], start=1):
            actions.append(
                BindPhoneToExtension(
                    id=_bind_action_id(extension),
                    phase=VoicePhase.PHONE_BINDINGS,
                    required_capability=(
                        VoiceCapabilityDimension.PHONE_EXTENSION_CONFIG
                    ),
                    phone_id=f"voiceab/p{index}",
                    physical_device_name=self._name(f"P{index}"),
                    phone_model=self._phone_model, extension=extension,
                    directory_index=index, **common,
                )
            )
        actions.append(
            GeneratePhoneConfigurationFiles(
                id="voiceab/cme/cnf", phase=VoicePhase.PHONE_BOOTSTRAP,
                required_capability=VoiceCapabilityDimension.TFTP_PHONE_BOOTSTRAP,
                **common,
            )
        )
        return actions

    # ------------------------------------------------------------------
    # The measured pass.  Order here IS the lifecycle record.
    # ------------------------------------------------------------------

    def _measure(
        self, router_model: str, switch_model: str, phone_model: str,
        created, owned_links, journal: _Journal,
    ):
        self._router_model = router_model
        self._switch_model = switch_model
        self._phone_model = phone_model
        errors: list[str] = []

        router = DevicePlan(
            id="voiceab/r", name=self._name("R"), model=router_model,
            category="", x=9000, y=9000,
        )
        switch = DevicePlan(
            id="voiceab/sw", name=self._name("SW"), model=switch_model,
            category="", x=9000, y=9400,
        )
        phones = [
            DevicePlan(
                id=f"voiceab/p{index}", name=self._name(f"P{index}"),
                model=phone_model, category="", x=8800 + 300 * index, y=9800,
            )
            for index in range(1, self._phone_count + 1)
        ]

        original_simulation = self._read_mode(errors)
        empty: tuple[PositiveVoicePhoneOutcome, ...] = ()

        for device in (router, switch):
            if not self._create(device, created, errors):
                return (
                    original_simulation, empty, None, False, False,
                    PositiveVoiceFoundation(), None, "", errors,
                )
        journal.record("DEVICE_CREATE_ORDER", True, "router, switch, then phones")
        for device in phones:
            if not self._create(device, created, errors):
                return (
                    original_simulation, empty, None, False, False,
                    PositiveVoiceFoundation(), None, "", errors,
                )
        journal.record("WHEN_PHONE_EXISTS", True, ", ".join(p.name for p in phones))
        # PT publishes no phone power or boot state on this build.  This one is
        # an OBSERVATION milestone with nothing to observe on, which is exactly
        # what the UNOBSERVABLE status exists to say; writing a guess here, or
        # borrowing the create mutation's acceptance for it, is what it exists
        # to prevent.
        journal.record(
            "WHEN_PHONE_IS_POWERED", False, "no measured boot surface", OBSERVATION,
        )

        uplink = LinkPlan(
            device_a=router.name, port_a=ROUTER_UPLINK_INTERFACE,
            device_b=switch.name, port_b=SWITCH_UPLINK_INTERFACE, cable="straight",
        )
        phone_ports = tuple(
            self._switch_interface(index) for index in range(1, len(phones) + 1)
        )
        links = [uplink] + [
            LinkPlan(
                device_a=switch.name, port_a=port,
                device_b=phone.name, port_b=PHONE_LINK_PORT, cable="straight",
            )
            for port, phone in zip(phone_ports, phones)
        ]
        for link in links:
            if not self._link(link, owned_links, errors):
                return (
                    original_simulation, empty, None, False, False,
                    PositiveVoiceFoundation(), None, "", errors,
                )
        journal.record("LINK_CREATE_ORDER", True, "uplink first, then phone links")
        journal.record("WHEN_PHONE_IS_LINKED", True, ", ".join(phone_ports))

        applied, config_errors = self._apply(
            self._configuration.apply_actions,
            self._configuration_actions(phone_ports),
        )
        errors.extend(config_errors)
        journal.record(
            "WHEN_ACCESS_VLAN_APPLIED", applied,
            # The actual per-port intent, not a shared constant: run 9's paired
            # mapping proved a uniform "data vlan 931" here was false for the
            # intervention port the moment the experiment existed.
            ", ".join(
                f"{port}:{vlan}"
                for port, vlan in zip(phone_ports, self._phone_access_vlans)
            ),
        )
        journal.record("WHEN_VOICE_VLAN_APPLIED", applied, f"voice vlan {VOICE_VLAN_ID}")
        journal.record("WHEN_DHCP_POOL_EXISTS", applied, VOICE_POOL_NAME)
        journal.record("CONFIGURATION_APPLY_ORDER", applied, "L2, L3, then services")

        # Immediately after the L2 configuration and before anything else, which
        # is where a repaired canonical pipeline would emit it: the control
        # plane runs after the configuration stage, never before it.  Applying
        # it earlier would answer a question about ordering that nobody asked.
        self._apply_edge_portfast(phone_ports, journal, errors)

        voice_applied, voice_errors = self._apply(
            self._call_control.apply_actions, self._voice_actions(),
        )
        errors.extend(voice_errors)
        journal.record("WHEN_OPTION150_APPLIED", voice_applied, VOICE_GATEWAY)
        journal.record("WHEN_CME_ENABLED", voice_applied, "telephony-service")
        journal.record("WHEN_PHONE_BINDING_EXISTS", voice_applied, ", ".join(EXTENSIONS))
        journal.record("WHEN_CNF_FILES_GENERATED", voice_applied, "create cnf-files")

        # The typed endpoint runtime answers with a bool, and only True is its
        # acceptance.  In the FWD-gated experiment the arming moves BEHIND the
        # gate: the trigger under judgement must not fire before the port it
        # is judged on was observed forwarding.
        if not self._fwd_gated:
            self._arm_endpoints(phones, journal, errors)

        # Realtime is the authoritative window for addressing and registration.
        realtime_before = self._realtime(errors, "before")
        stp_before = self._read_stp(switch.name, errors)
        journal.record(
            "REALTIME_VERIFIED_BEFORE_WINDOW", realtime_before,
            evidence=OBSERVATION,
        )

        gate: StpForwardingGate | None = None
        boundary = ""
        pre_arm: dict[str, str] = {}
        arm_acceptance: dict[str, str] = {}
        post_arm: dict[str, str] = {}
        if self._fwd_gated:
            intervention = phone_ports[
                self._phone_access_vlans.index(VOICE_VLAN_ID)
            ]
            gate = await_stp_forwarding(
                self._configuration, switch.name, VOICE_VLAN_ID, intervention,
                timeout_seconds=self._gate_timeout_seconds,
                interval_seconds=self._gate_interval_seconds,
                clock=self._gate_clock, sleeper=self._gate_sleeper,
                errors=errors,
            )
            journal.record(
                "WHEN_INTERVENTION_STP_FWD_OBSERVED", gate.forwarding_observed,
                " -> ".join(gate.observed_states), OBSERVATION,
            )
            if not gate.forwarding_observed:
                boundary = ACQUISITION_NOT_STARTED_STP_PRECONDITION_UNMET
            else:
                for phone in phones:
                    pre_arm[phone.name] = self._read_endpoint_dhcp_flag(
                        phone.name, errors,
                    )
                journal.record(
                    "WHEN_ENDPOINT_DHCP_PRE_ARM_READ",
                    all(value != UNOBSERVABLE for value in pre_arm.values()),
                    ", ".join(f"{k}:{v}" for k, v in pre_arm.items()),
                    OBSERVATION,
                )
                # A fresh trigger is an OFF-to-ON transition that this run
                # itself performs.  A flag already ON -- or one that could not
                # be read -- makes the arming call's effect unprovable, and an
                # unprovable trigger is never judged.
                if any(value != NO for value in pre_arm.values()):
                    boundary = (
                        ACQUISITION_NOT_STARTED_FRESH_DHCP_TRIGGER_UNPROVEN
                    )
                else:
                    armed = self._arm_endpoints(
                        phones, journal, errors, arm_acceptance,
                    )
                    for phone in phones:
                        post_arm[phone.name] = self._read_endpoint_dhcp_flag(
                            phone.name, errors,
                        )
                    journal.record(
                        "WHEN_ENDPOINT_DHCP_POST_ARM_READ",
                        all(
                            value != UNOBSERVABLE
                            for value in post_arm.values()
                        ),
                        ", ".join(f"{k}:{v}" for k, v in post_arm.items()),
                        OBSERVATION,
                    )
                    transition_valid = (
                        armed is True
                        and all(value == YES for value in post_arm.values())
                    )
                    journal.record(
                        "WHEN_ENDPOINT_DHCP_FLAG_TRANSITION_VALID",
                        transition_valid,
                        "PRE NO + ARM_ACCEPTED + POST YES for every phone",
                        OBSERVATION,
                    )
                    if not transition_valid:
                        boundary = (
                            ACQUISITION_NOT_STARTED_FRESH_DHCP_TRIGGER_UNPROVEN
                        )

        if boundary:
            # Fail closed: the causal acquisition was not authorized, so no
            # window opens.  A partially accepted batch must not read as
            # phones that failed inside an experiment that never started.
            registrations: dict = {}
            journal.record("ACQUISITION_WINDOW_RUN", False, boundary, OBSERVATION)
        else:
            registrations = self._observe_registrations(phones, errors)
            journal.record(
                "ACQUISITION_WINDOW_RUN", True, "registration convergence",
                OBSERVATION,
            )

        stp_after = self._read_stp(switch.name, errors)
        binding_count = self._read_bindings(router.name, errors)
        foundation = self._read_foundation(switch.name, router.name, journal, errors)
        realtime_after = self._realtime(errors, "after")
        journal.record(
            "REALTIME_VERIFIED_AFTER_WINDOW", realtime_after, evidence=OBSERVATION,
        )

        outcomes = tuple(
            self._phone_outcome(
                phone, phone_ports[index],
                self._phone_access_vlans[index],
                EXTENSIONS[index] if index < len(EXTENSIONS) else "",
                switch.name, registrations.get(phone.name),
                stp_before, stp_after, errors,
                dhcp_pre_arm=pre_arm.get(phone.name, UNOBSERVABLE),
                arm_call_accepted=arm_acceptance.get(
                    phone.name, UNOBSERVABLE,
                ),
                dhcp_post_arm=post_arm.get(phone.name, UNOBSERVABLE),
            )
            for index, phone in enumerate(phones)
        )
        return (
            original_simulation, outcomes, binding_count,
            realtime_before, realtime_after, foundation, gate, boundary, errors,
        )

    def _arm_endpoints(
        self, phones, journal: _Journal, errors: list[str],
        acceptance: dict[str, str] | None = None,
    ) -> bool:
        """Ask every phone to acquire, through the typed endpoint runtime.

        The runtime answers with a bool, and only True is its acceptance.  An
        exception-only check would journal a milestone for a refusal it never
        looked at, and the milestone would then be evidence of nothing.  What
        it claims even so is acceptance, not that the phone is now soliciting:
        whether DHCP is on is read on its own surface.
        """
        armed = True
        for phone in phones:
            try:
                accepted = self._endpoints.configure_endpoint_dhcp(
                    phone.name, PHONE_ADDRESSING_INTERFACE,
                )
            except Exception as exc:  # noqa: BLE001
                errors.append(f"endpoint_dhcp_failed:{phone.name}: {exc}")
                if acceptance is not None:
                    acceptance[phone.name] = NO
                armed = False
                continue
            if accepted is not True:
                errors.append(f"endpoint_dhcp_not_accepted:{phone.name}")
                if acceptance is not None:
                    acceptance[phone.name] = NO
                armed = False
            elif acceptance is not None:
                acceptance[phone.name] = YES
        journal.record(
            "WHEN_ENDPOINT_DHCP_ARMED", armed,
            "typed endpoint runtime accepted every phone",
        )
        return armed

    def _read_endpoint_dhcp_flag(self, device_name: str, errors: list[str]) -> str:
        """The phone's own DHCP flag, on the SVI this plan addresses it on.

        Read through the SAME endpoint surface the outcome pass uses -- no new
        observer -- at a moment it was never read before.  None anywhere in
        the chain is an unread channel, and an unread channel is never NO.
        """
        try:
            observation = self._endpoints.read_endpoint_address(
                device_name, PHONE_ADDRESSING_INTERFACE,
            )
        except Exception as exc:  # noqa: BLE001
            errors.append(f"endpoint_dhcp_flag_unreadable:{device_name}: {exc}")
            return UNOBSERVABLE
        if observation is None:
            return UNOBSERVABLE
        flag = getattr(observation, "dhcp_enabled", None)
        if flag is None:
            return UNOBSERVABLE
        return YES if bool(flag) else NO

    @staticmethod
    def _optional_read(runtime, name: str, errors: list[str], label: str, *arguments):
        """Call a read-only surface the runtime MAY publish.

        A runtime without it has not failed -- there is nothing to record as an
        error, and every dimension behind it simply stays unread.  A surface
        that exists and raises IS an error, and still yields nothing.
        """
        reader = getattr(runtime, name, None)
        if reader is None:
            return None
        try:
            return reader(*arguments)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{label}_unreadable: {exc}")
            return None

    def _read_foundation(
        self, switch_name: str, router_name: str, journal: _Journal,
        errors: list[str],
    ) -> PositiveVoiceFoundation:
        """Read the foundation both sides of the A/B share.  Reads only.

        This runs AFTER the acquisition window, beside the STP and binding
        reads, for two reasons: the state it observes does not change during
        the window, and starting the window later would make the next LIVE a
        different experiment from the one it has to reproduce.
        """
        trunk = self._optional_read(
            self._configuration, "read_trunk", errors, "switch_trunk",
            switch_name, SWITCH_UPLINK_INTERFACE,
        )
        rows = self._optional_read(
            self._configuration, "read_interface_addresses", errors,
            "router_interfaces", router_name,
        )
        pool = self._optional_read(
            self._configuration, "read_dhcp_pool", errors, "dhcp_pool",
            router_name, VOICE_POOL_NAME, VOICE_LEASE_START, VOICE_LEASE_END,
        )
        table = self._optional_read(
            self._call_control, "inspect_call_control", errors,
            "call_control_table", router_name,
        )

        trunk_fields = _classify_trunk(trunk)
        router_fields = _classify_router_subinterface(rows)
        pool_fields = _classify_dhcp_pool(pool)
        call_control, ephone_rows = _classify_call_control(table)
        journal.record(
            "SWITCH_TRUNK_OBSERVED",
            trunk_fields["trunk_operational"] != UNOBSERVABLE,
            f"{switch_name} {SWITCH_UPLINK_INTERFACE}", OBSERVATION,
        )
        journal.record(
            "ROUTER_VOICE_SUBINTERFACE_OBSERVED",
            router_fields["router_subinterface_present"] != UNOBSERVABLE,
            ROUTER_VOICE_SUBINTERFACE, OBSERVATION,
        )
        journal.record(
            "DHCP_POOL_OBSERVED",
            pool_fields["dhcp_pool_existence"] != UNOBSERVABLE,
            VOICE_POOL_NAME, OBSERVATION,
        )
        journal.record(
            "CALL_CONTROL_TABLE_OBSERVED", call_control != UNOBSERVABLE,
            router_name, OBSERVATION,
        )
        return PositiveVoiceFoundation(
            call_control_table=call_control,
            call_control_ephone_rows=ephone_rows,
            **trunk_fields, **router_fields, **pool_fields,
        )

    def _apply_edge_portfast(
        self, phone_ports: tuple[str, ...], journal: _Journal, errors: list[str],
    ) -> None:
        """The intervention.  Nothing happens here in the baseline."""
        if not self._edge_portfast:
            return
        if self._control_plane is None:
            errors.append(
                "edge_portfast_requested_without_control_plane_runtime"
            )
            journal.record(
                "WHEN_EDGE_PORTFAST_APPLIED", False,
                "no typed control-plane runtime was supplied",
            )
            return
        applied, edge_errors = self._apply(
            self._control_plane.apply_actions,
            self._edge_stp_actions(phone_ports),
        )
        errors.extend(edge_errors)
        journal.record(
            "WHEN_EDGE_PORTFAST_APPLIED", applied,
            "portfast on, bpduguard off: " + ", ".join(phone_ports),
        )

    def _edge_stp_actions(self, phone_ports: tuple[str, ...]) -> list:
        """One typed edge action per phone-facing port.  No new primitive.

        No global `ConfigureSpanningTree` accompanies these.  The 3560 already
        runs PVST+ by default, so one would change a second variable -- mode
        and priority -- in an experiment whose whole value is that it changes
        one.  `depends_on` stays empty for the same kind of reason: this slice
        calls the typed runtime directly, exactly as it does for configuration
        and voice, and nothing here reorders an applicator that is not running.
        """
        from ...domain.enterprise.models.control_plane import (
            ConfigureStpEdgePort,
            ControlPlaneCapabilityDimension,
            ControlPlanePhase,
        )

        switch = self._name("SW")
        return [
            ConfigureStpEdgePort(
                id=f"voiceab/stp/edge/{index}",
                phase=ControlPlanePhase.L2_RESILIENCY,
                device_id="voiceab/sw", device_name=switch,
                model=self._switch_model, site_id="voiceab",
                required_capability=(
                    ControlPlaneCapabilityDimension.STP_PVST_CONFIG
                ),
                interface=interface,
                portfast=True,
                bpduguard=False,
                source_access_action_id=f"voiceab/access/{index}",
            )
            for index, interface in enumerate(phone_ports, start=1)
        ]

    def _read_mode(self, errors: list[str]) -> bool | None:
        try:
            state = self._mode.read_simulation_state()
        except Exception as exc:  # noqa: BLE001
            errors.append(f"simulation_state_unreadable: {exc}")
            return None
        return bool(getattr(state, "simulation_mode", False))

    def _realtime(self, errors: list[str], label: str) -> bool:
        """A pure read.  Realtime is verified, never inferred from not switching."""
        try:
            state = self._mode.read_simulation_state()
        except Exception as exc:  # noqa: BLE001
            errors.append(f"realtime_unreadable_{label}: {exc}")
            return False
        if not bool(getattr(state, "observed", True)):
            errors.append(f"realtime_unobserved_{label}")
            return False
        return not bool(getattr(state, "simulation_mode", False))

    def _create(self, device: DevicePlan, created, errors) -> bool:
        # Ownership is recorded BEFORE the mutation is invoked, not after it
        # returns.  The moment the call is in flight the backend effect is
        # unknown, and a device created by a call that then raised still has to
        # be cleaned up.  The reserved unique name and the verified empty
        # semantic baseline are what make this target this slice's to own.
        created.append(device)
        try:
            outcome = self._physical.ensure_device(device)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"device_create_raised:{device.name}: {exc}")
            return False
        if not _mutation_applied(outcome):
            message = getattr(outcome, "message", "")
            errors.append(f"device_not_created:{device.name}: {message}")
            return False
        return True

    def _link(self, link: LinkPlan, owned_links, errors) -> bool:
        # Owned before invoked, for the same reason as the device: a link whose
        # call raised may still exist on the backend, and an ownership journal
        # that only records the calls that returned is a journal that loses
        # exactly the objects nobody can account for.
        owned_links.append(
            f"{link.device_a}:{link.port_a}->{link.device_b}:{link.port_b}"
        )
        try:
            outcome = self._physical.ensure_link(link)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"link_raised:{link.device_a}->{link.device_b}: {exc}")
            return False
        if not _mutation_applied(outcome):
            message = getattr(outcome, "message", "")
            errors.append(f"link_failed:{link.device_a}->{link.device_b}: {message}")
            return False
        return True

    def _apply(self, runner, actions) -> tuple[bool, list[str]]:
        """Judge a typed batch by the field the runtime actually publishes.

        A batch that comes back short of one mutation per action is the same
        missing statement: the actions with no result were never judged, and
        calling the batch applied would be judging them by their absence.
        """
        try:
            results = runner(actions)
        except Exception as exc:  # noqa: BLE001
            return False, [f"apply_raised: {type(exc).__name__}: {exc}"]
        mutations = list(results or ())
        errors = []
        if len(mutations) != len(actions):
            errors.append(
                f"apply_incomplete: {len(mutations)} mutations for "
                f"{len(actions)} actions"
            )
        for item in mutations:
            if _mutation_applied(item):
                continue
            action_id = getattr(item, "action_id", "")
            message = getattr(item, "message", "")
            errors.append(f"action_failed:{action_id}: {message}")
        return not errors, errors

    def _read_stp(self, switch_name: str, errors: list[str]):
        """None means the table was never read; it never means no rows."""
        try:
            return self._configuration.read_spanning_tree(switch_name)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"stp_unreadable: {exc}")
            return None

    def _read_bindings(self, router_name: str, errors: list[str]) -> int | None:
        try:
            rows = self._configuration.read_dhcp_bindings(router_name)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"dhcp_bindings_unreadable: {exc}")
            return None
        if rows is None:
            return None
        prefix = VOICE_NETWORK.rsplit(".", 1)[0] + "."
        return sum(
            1 for row in rows
            if str(getattr(row, "ip_address", "") or "").startswith(prefix)
        )

    def _observe_registrations(self, phones, errors: list[str]) -> dict:
        """Ask the production registration runtime in its own contract.

        `observe_registrations` reads a `VoiceVerificationExpectation`, and it
        reads more of it than an id: `endpoint_device_name` is the phone whose
        own SVI the runtime interrogates for the address, independently of what
        the call control remembers.  An expectation that omits that field makes
        every phone report no address -- which is precisely the CP-SCALE
        signature this A/B exists to tell apart from a real one.
        """
        from ...domain.enterprise.models.voice_plan import (
            VoiceVerificationExpectation,
            VoiceVerificationKind,
        )

        expectations = []
        for index, phone in enumerate(phones, start=1):
            extension = (
                EXTENSIONS[index - 1] if index - 1 < len(EXTENSIONS) else ""
            )
            expectations.append(
                VoiceVerificationExpectation(
                    id=f"voiceab/reg/{index}",
                    kind=VoiceVerificationKind.PHONE_REGISTRATION,
                    phone_id=f"voiceab/p{index}",
                    extension=extension,
                    call_control_id=CALL_CONTROL_ID,
                    action_id=_bind_action_id(extension),
                    endpoint_device_name=phone.name,
                    endpoint_interface=PHONE_ADDRESSING_INTERFACE,
                )
            )
        try:
            observed = self._call_control.observe_registrations(expectations)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"registration_unobservable: {exc}")
            return {}
        by_name: dict = {}
        for expectation, item in zip(expectations, observed or ()):
            by_name[expectation.endpoint_device_name] = item
        return by_name

    def _phone_outcome(
        self, phone: DevicePlan, interface: str, expected_access_vlan: int,
        extension: str, switch_name: str, registration, stp_before, stp_after,
        errors: list[str],
        *,
        dhcp_pre_arm: str = UNOBSERVABLE,
        arm_call_accepted: str = UNOBSERVABLE,
        dhcp_post_arm: str = UNOBSERVABLE,
    ) -> PositiveVoicePhoneOutcome:
        data_status = voice_status = UNOBSERVABLE
        try:
            port = self._configuration.read_access_port(
                switch_name, interface, expected_access_vlan,
            )
        except Exception as exc:  # noqa: BLE001
            errors.append(f"access_port_unreadable:{interface}: {exc}")
            port = None
        if port is not None:
            data_status = _compare_vlan(
                getattr(port, "data_vlan_id", None), expected_access_vlan,
            )
            voice_status = _compare_vlan(
                getattr(port, "voice_vlan_id", None), VOICE_VLAN_ID,
            )

        ipv4 = ""
        device_ipv4 = ""
        svi_present = False
        address_channel = False
        dhcp_enabled = UNOBSERVABLE
        registered = UNOBSERVABLE
        if registration is not None:
            ipv4 = str(getattr(registration, "endpoint_ipv4", "") or "")
            device_ipv4 = str(getattr(registration, "device_ipv4", "") or "")
            svi_present = bool(
                getattr(registration, "endpoint_interface_present", False)
            )
            address_channel = bool(
                getattr(registration, "endpoint_address_channel", False)
            )
            flag = getattr(registration, "endpoint_dhcp_enabled", None)
            if flag is not None:
                dhcp_enabled = YES if bool(flag) else NO
            status = str(getattr(registration, "status", "") or "")
            direct = str(getattr(registration, "direct_readback", "") or "")
            if "VERIFIED" in status.upper() and "VERIFIED" in direct.upper():
                registered = REGISTERED
            elif status:
                registered = NOT_REGISTERED
        if not ipv4:
            # The registration surface carries the endpoint address, but a
            # separate endpoint read is what makes an absent one distinguishable
            # from an unread one.
            try:
                observation = self._endpoints.read_endpoint_address(
                    phone.name, PHONE_ADDRESSING_INTERFACE,
                )
            except Exception as exc:  # noqa: BLE001
                errors.append(f"endpoint_address_unreadable:{phone.name}: {exc}")
                observation = None
            if observation is not None:
                ipv4 = str(getattr(observation, "ipv4", "") or "")
                channel = getattr(observation, "address_channel", None)
                if channel is not None:
                    address_channel = bool(channel) or address_channel
                elif ipv4:
                    # An address proves there was a channel; an empty one
                    # proves nothing either way, so absence is never inferred.
                    address_channel = True
                if dhcp_enabled == UNOBSERVABLE:
                    flag = getattr(observation, "dhcp_enabled", None)
                    if flag is not None:
                        dhcp_enabled = YES if bool(flag) else NO

        link_types, portfast_readback = _classify_edge_marker(stp_after, interface)
        return PositiveVoicePhoneOutcome(
            phone_name=phone.name, extension=extension,
            switch_interface=interface,
            access_vlan_expected=expected_access_vlan,
            portfast_readback=portfast_readback, stp_link_types=link_types,
            data_vlan_readback=data_status, voice_vlan_readback=voice_status,
            dhcp_enabled=dhcp_enabled,
            dhcp_enabled_pre_arm=dhcp_pre_arm,
            arm_call_accepted=arm_call_accepted,
            dhcp_enabled_post_arm=dhcp_post_arm,
            ipv4=ipv4,
            voice_svi_present=svi_present, address_channel=address_channel,
            device_ipv4=device_ipv4, registration=registered,
            stp_row_before=_classify_stp_row(stp_before, VOICE_VLAN_ID, interface),
            stp_row_after=_classify_stp_row(stp_after, VOICE_VLAN_ID, interface),
        )


def _compare_vlan(observed, expected: int) -> str:
    """VERIFIED / CONTRADICTED / UNOBSERVABLE, with absence kept separate."""
    if observed is None:
        return UNOBSERVABLE
    try:
        return VERIFIED if int(observed) == expected else CONTRADICTED
    except (TypeError, ValueError):
        return UNOBSERVABLE
