"""Adapter Packet Tracer para aplicar y observar ServicePlan E6.

Every fact this adapter reports comes from a typed read it actually performed.
The generated batch script brackets each setter with a pre-read and an
unconditional post-read, computes the postcondition and the transition from
the actual typed values inside the same evaluation, and reports digests only
as bounded diagnostics. Python derives no fact from a digest: equal hashes,
equal lengths and a true native return are never UNCHANGED, SATISFIED or
CLEAN. The decision that turns these observations into a product outcome
lives in the domain, not here.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import Enum, StrEnum
from ipaddress import ip_address
from time import monotonic, sleep

from ...domain.enterprise.models.configuration_runtime import (
    ActionExecutionStatus,
    ConfigurationFailureCode,
    RuntimeActionMutation,
    RuntimeConfigurationTarget,
)
from ...domain.enterprise.models.execution import (
    DispatchFact,
    FootprintFact,
    PostconditionFact,
    ResultFact,
    TransitionFact,
)
from ...domain.enterprise.models.service_plan import (
    AddDnsRecord,
    ConfigureNtpService,
    EnableDnsService,
    EnableHttpService,
    EnableHttpsService,
    EnableTftpService,
    PublishTftpFile,
    ServiceAction,
    ServiceEvidenceKind,
    ServiceType,
    ServiceVerificationExpectation,
    ServiceVerificationKind,
    SetHttpContent,
)
from ...domain.enterprise.models.service_runtime import (
    ObservationFact,
    RuntimeServiceVerification,
)
from .command_dispatch import PAGER_GUARD_JS
from .runtime_inventory import normalize_runtime_inventory
from .transport_outcome import BridgeDispatchOutcome, sanitized_detail

_HOSTNAME = re.compile(
    r"(?=^.{1,253}$)(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)*"
    r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$"
)

_NOT_FOUND = re.compile(r"could not find host|unknown host", re.I)

#: The two shapes in which a typed `ping` reports the address it resolved:
#: `Pinging <address> with ...` and `Ping statistics for <address>:`, plus the
#: bracketed hostname form `Pinging <host> [<address>] with ...`. These lines
#: are the ONLY resolution evidence. `expected in window` accepted any IP-like
#: occurrence anywhere -- the echoed command, a reply line, an unrelated line
#: -- and, being a substring test, accepted `192.0.2.10` inside a window that
#: resolved `192.0.2.100` (R3b).
_PING_TARGET = re.compile(
    r"^[ \t]*pinging[ \t]+(?:\S+[ \t]+\[(?P<bracketed>[^\]\s]+)\]|(?P<plain>[^\s\[]+))",
    re.I | re.M,
)
_PING_STATISTICS = re.compile(
    r"^[ \t]*ping statistics for[ \t]+(?P<address>[^\s:]+)[ \t]*:",
    re.I | re.M,
)

#: What the bounded finalization established about the background client a web
#: read may own. `released` is the only value that proves the owned client is
#: gone, and `nothing_owned` the only other resolved one -- it needs a
#: correlated start payload that reported no client was ever created. The rest
#: are unresolved ownership and are named in the row's limitations, because an
#: absent slot after an unobserved start is not evidence of a release (R1).
_RELEASE_RELEASED = "released"
_RELEASE_NOTHING_OWNED = "nothing_owned"
_RELEASE_UNVERIFIED = "release_unverified"
_RELEASE_FAILED = "release_failed"
_RELEASE_OWNERSHIP_UNKNOWN = "ownership_unknown"
_RESOLVED_RELEASE = frozenset({_RELEASE_RELEASED, _RELEASE_NOTHING_OWNED})

#: The process each service type is reached through.
_PROCESS = {
    ServiceType.DNS: "DnsServer",
    ServiceType.HTTP: "HttpServer",
    ServiceType.HTTPS: "HttpsServer",
    ServiceType.NTP: "NtpServer",
    ServiceType.TFTP: "TftpServer",
}

#: The digest helper and the bounded error reader, defined once per batch.
#:
#: FNV-1a 32 bit with the shift-add decomposition of the prime, not a
#: multiplication: `h*0x01000193` in JavaScript is a float64 product and loses
#: the low bits, which would make the digest depend on the engine. The five
#: shifted terms sum below 2^53, so `>>>0` converts them exactly.
#:
#: A digest is a bounded diagnostic and nothing else. It is deliberately a
#: 32-bit hash plus a length, which collides -- `yI76Uj5ZfPNL` and
#: `qx51K0WT5Lj1` are both `1bb90b62:12` -- and the harness exercises exactly
#: that pair, because a collision must not be able to produce a fact.
_SCRIPT_HELPERS = (
    "function __dg(v){if(typeof v==='boolean'){return v?'1':'0';}"
    "var s=String(v);var h=0x811c9dc5;for(var i=0;i<s.length;i++){"
    "h^=s.charCodeAt(i);h=(h+((h<<1)+(h<<4)+(h<<7)+(h<<8)+(h<<24)))>>>0;}"
    "return ('0000000'+h.toString(16)).slice(-8)+':'+s.length;}"
    "function __er(e){var s='';try{s=String(e&&e.message?e.message:e);}"
    "catch(x){s='error';}return s.length>200?s.substring(0,200):s;}"
)

#: The exact keys the row contract requires. An omitted key is invalid: it is
#: not null, and reading it as null would invent an observation.
_ROW_KEYS = (
    "id",
    "attempted",
    "skip_reason",
    "call_error",
    "call_result",
    "pre_read",
    "post_read",
    "ok",
    "changed",
    "pre",
    "post",
)

#: The only two reasons a row may report that no setter ran.
_SKIP_ALREADY_SATISFIED = "already_satisfied"
_SKIP_FAMILY_NOT_IMPLEMENTED = "family_not_implemented"

#: The observed scope of an attempted `AddDnsRecord` is membership of the one
#: wanted record, while the setter's footprint is the whole A-record table.
#: Widening the read is gate M-DNS-4, so until then the residue outside that
#: membership stays unobserved and is named here.
_DNS_PARTIAL_FOOTPRINT = "footprint_partial:dns_a_record_table"

#: Observation fact -> (status, fresh_evidence). NOT_ATTEMPTED and UNSPECIFIED
#: are absent on purpose: they carry the status the producer stated.
_OBSERVATION_STATUS = {
    ObservationFact.OBSERVED: (ActionExecutionStatus.VERIFIED, True),
    ObservationFact.CONTRADICTED: (ActionExecutionStatus.FAILED, True),
    ObservationFact.INCONCLUSIVE: (ActionExecutionStatus.UNKNOWN, False),
    ObservationFact.SUBJECT_NOT_FOUND: (ActionExecutionStatus.UNOBSERVABLE, False),
    ObservationFact.MALFORMED: (ActionExecutionStatus.UNOBSERVABLE, False),
    ObservationFact.ENGINE_ERROR: (ActionExecutionStatus.UNOBSERVABLE, False),
    ObservationFact.NOT_OBSERVED: (ActionExecutionStatus.UNKNOWN, False),
    ObservationFact.LOST: (ActionExecutionStatus.UNKNOWN, False),
    ObservationFact.ACCEPTANCE_UNKNOWN: (ActionExecutionStatus.UNKNOWN, False),
    ObservationFact.NOT_SUBMITTED: (ActionExecutionStatus.UNKNOWN, False),
    ObservationFact.REJECTED: (ActionExecutionStatus.UNKNOWN, False),
}


class BridgeObservationKind(StrEnum):
    """What one command dispatch produced, before any product reading.

    `{}` used to stand for all four of these at once, so a Packet Tracer
    exception, a non-JSON answer, a result that never arrived and a device
    that genuinely reported an empty object were the same value.
    """

    __str__ = Enum.__str__

    PAYLOAD = "payload"
    ENGINE_ERROR = "engine_error"
    MALFORMED = "malformed"
    UNOBSERVED = "unobserved"


@dataclass(frozen=True)
class BridgeObservation:
    """One dispatch, its typed transport facts, and its parsed payload."""

    kind: BridgeObservationKind
    payload: dict | None
    message: str
    outcome: BridgeDispatchOutcome


class ClientOwnership(StrEnum):
    """What one web read knows about the background client it may own.

    NONE is before any dispatch, so nothing can exist to release. UNKNOWN is
    the fail-closed value from the moment the start command is handed to the
    channel: the script may have created and tracked a client whatever came
    back, so the finalization must still look. OWNED and ABSENT are the two
    answers a correlated start payload gives, and only they make a missing
    slot mean something.
    """

    __str__ = Enum.__str__

    NONE = "none"
    UNKNOWN = "unknown"
    OWNED = "owned"
    ABSENT = "absent"


@dataclass
class ClientLease:
    """The mutable ownership a web read carries to its own finalization.

    It exists so that the reader's result path and its cleanup path are not
    the same return statement: whatever the reader returns, raises or times
    out, the lease still says what has to be released.
    """

    state: ClientOwnership = ClientOwnership.NONE


@dataclass(frozen=True)
class ReleaseOutcome:
    """What one bounded finalization attempt established, and why."""

    outcome: str
    cause: str = ""

    @property
    def resolved(self) -> bool:
        """Whether ownership is settled; `False` is a reportable residue."""
        return self.outcome in _RESOLVED_RELEASE


@dataclass(frozen=True)
class TextReading:
    """One reader payload validated before any part of it is used.

    `admissible` is the whole point: until the declared fields are present
    and exactly typed, `content` is not a reading of anything, and `fact`
    names which non-observation the payload actually is.
    """

    admissible: bool
    content: str = ""
    fact: ObservationFact = ObservationFact.MALFORMED
    cause: str = ""


def _typed_payload(payload: dict, spec: dict[str, type]) -> str:
    """Name the first declared field the payload does not actually carry.

    `spec` declares `bool` or `str` and they are checked as exact types. A
    permissive check is what let `{"found": false, "content": {...}}` become
    a page: truthiness accepted a numeric or non-empty-string flag as a
    boolean, and `str(...)` turned a JSON object into text that contained the
    expected marker (R3a). An absent key is reported as absent rather than
    defaulted, because a field the payload never carried establishes nothing
    about its subject.

    Returns the empty string when every declared field is present and typed.
    """
    for name, kind in spec.items():
        if name not in payload:
            return f"missing:{name}"
        value = payload[name]
        if kind is bool:
            if not isinstance(value, bool):
                return f"not_a_boolean:{name}"
        elif not isinstance(value, str):
            return f"not_a_string:{name}"
    return ""


def _text_reading(payload: dict, field_name: str, absent_cause: str) -> TextReading:
    """Validate one `{found, <field_name>}` reader payload, in stage order.

    `found` is READ, not assumed. A payload that reports its subject was not
    there says nothing about the subject's text, so it is a missing subject
    rather than an empty reading, and the text is only typed once the subject
    is known to exist.
    """
    shape = _typed_payload(payload, {"found": bool})
    if shape:
        return TextReading(
            False,
            fact=ObservationFact.MALFORMED,
            cause=f"inspect_shape:{shape}",
        )
    if not payload["found"]:
        return TextReading(
            False,
            fact=ObservationFact.SUBJECT_NOT_FOUND,
            cause=absent_cause,
        )
    shape = _typed_payload(payload, {field_name: str})
    if shape:
        return TextReading(
            False,
            fact=ObservationFact.MALFORMED,
            cause=f"inspect_shape:{shape}",
        )
    return TextReading(True, content=payload[field_name])


def _dns_resolution(window: str) -> tuple[str, str]:
    """Return the address the window reported, or why it cannot be read.

    Only the supported shapes are read, every candidate must parse as an
    address, and all candidates must agree. A window that reports no address,
    one that reports something unparsable, and one that reports two different
    addresses each decide nothing; the caller reports that as inconclusive
    instead of comparing substrings.
    """
    candidates = [
        match.group("bracketed") or match.group("plain")
        for match in _PING_TARGET.finditer(window)
    ]
    candidates.extend(
        match.group("address") for match in _PING_STATISTICS.finditer(window)
    )
    if not candidates:
        return "", "address_not_reported"
    parsed: set[str] = set()
    for candidate in candidates:
        try:
            parsed.add(str(ip_address(candidate)))
        except ValueError:
            return "", "address_not_parsable"
    if len(parsed) != 1:
        return "", "address_ambiguous"
    return parsed.pop(), ""


class PacketTracerEnterpriseServiceRuntime:
    """Usa procesos documentados de PT; no ofrece JS ni comandos arbitrarios."""

    def __init__(
        self,
        query_inventory: Callable[[], list[dict] | dict],
        send_and_wait: Callable[[str, float], str | None],
        *,
        dispatch_and_wait: Callable[[str, float], BridgeDispatchOutcome] | None = None,
        dns_timeout_seconds: float = 5.0,
        http_timeout_seconds: float = 8.0,
        convergence_interval_seconds: float = 0.25,
        clock: Callable[[], float] = monotonic,
        sleeper: Callable[[float], None] = sleep,
    ) -> None:
        """Bind the runtime to one inventory reader and one command channel.

        `dispatch_and_wait` is the channel that reports typed transport facts.
        When only the legacy `send_and_wait` is available its `None` is
        wrapped as ACCEPTANCE_UNKNOWN plus NOT_OBSERVED -- never
        NOT_SUBMITTED, because a callable that returns `None` cannot prove the
        payload stayed inside this process.
        """
        self._query_inventory = query_inventory
        self._send_and_wait = send_and_wait
        self._dispatch_and_wait = dispatch_and_wait
        self._dns_timeout = dns_timeout_seconds
        self._http_timeout = http_timeout_seconds
        self._interval = convergence_interval_seconds
        self._clock = clock
        self._sleep = sleeper

    def inventory(self) -> list[RuntimeConfigurationTarget]:
        """Return the runtime inventory, normalized to typed targets."""
        return normalize_runtime_inventory(self._query_inventory())

    # -- application ----------------------------------------------------

    def apply_actions(
        self,
        actions: Sequence[ServiceAction],
    ) -> list[RuntimeActionMutation]:
        """Apply one single-host batch and report the observed facts per action.

        The returned mutations carry observations and `applied` only. Status,
        disposition, failure code, residue, frontier and stickiness are the
        applicator's, through the one domain decision.
        """
        if not actions:
            return []
        host_names = {item.host_device_name for item in actions}
        if len(host_names) != 1:
            # A local contract error, not a transport fact: nothing was
            # dispatched, so the row stays a legacy definite failure.
            return [
                RuntimeActionMutation(
                    action_id=item.id,
                    applied=False,
                    failure_code=ConfigurationFailureCode.APPLICATION_FAILED,
                    message="A service runtime batch must target exactly one host.",
                )
                for item in actions
            ]
        host = json.dumps(next(iter(host_names)))
        lines = [
            f"var d=ipc.network().getDevice({host});var results=[];",
            _SCRIPT_HELPERS,
            "if(!d){reportResult(JSON.stringify({results:[]}));}else{",
        ]
        for action in actions:
            lines.extend(self._mutation_lines(action))
        lines.append("reportResult(JSON.stringify({results:results}));}")
        observation = self._observe("".join(lines), 10.0)
        return self._batch_mutations(actions, observation)

    def _batch_mutations(
        self,
        actions: Sequence[ServiceAction],
        observation: BridgeObservation,
    ) -> list[RuntimeActionMutation]:
        """Turn one batch observation into one typed mutation per action."""
        batch_id_for = {
            item.id: f"{item.host_device_name}:{int(item.phase)}" for item in actions
        }
        if observation.kind is not BridgeObservationKind.PAYLOAD:
            return [
                self._whole_batch_mutation(item, observation, batch_id_for[item.id])
                for item in actions
            ]

        payload = observation.payload or {}
        rows = payload.get("results")
        if not isinstance(rows, list):
            malformed = self._malformed_batch(observation, "results_not_a_list")
            return [
                self._whole_batch_mutation(item, malformed, batch_id_for[item.id])
                for item in actions
            ]
        identifiers = [
            str(row.get("id")) for row in rows if isinstance(row, dict) and "id" in row
        ]
        if len(identifiers) != len(set(identifiers)):
            malformed = self._malformed_batch(observation, "duplicate_row_ids")
            return [
                self._whole_batch_mutation(item, malformed, batch_id_for[item.id])
                for item in actions
            ]
        wanted = {item.id for item in actions}
        foreign = sorted(set(identifiers) - wanted)
        by_id = {
            str(row["id"]): row
            for row in rows
            if isinstance(row, dict) and "id" in row and str(row["id"]) in wanted
        }
        note = f" Foreign row ids ignored: {', '.join(foreign)}." if foreign else ""
        return [
            self._row_mutation(
                item,
                by_id.get(item.id),
                batch_id_for[item.id],
                note,
            )
            for item in actions
        ]

    @staticmethod
    def _malformed_batch(
        observation: BridgeObservation,
        check: str,
    ) -> BridgeObservation:
        """Re-state a correlated batch whose envelope shape is inadmissible."""
        return BridgeObservation(
            kind=BridgeObservationKind.MALFORMED,
            payload=None,
            message=f"Batch response was malformed: {check}.",
            outcome=BridgeDispatchOutcome(
                dispatch=observation.outcome.dispatch,
                result=ResultFact.MALFORMED,
                disposition=observation.outcome.disposition,
                detail=check,
            ),
        )

    @staticmethod
    def _whole_batch_mutation(
        action: ServiceAction,
        observation: BridgeObservation,
        batch_id: str,
    ) -> RuntimeActionMutation:
        """Report a batch-wide outcome identically for every action in it.

        NOT_SUBMITTED and REJECTED are answers about the channel, so nothing
        about the state was observed and the observation fields stay
        NOT_APPLICABLE (rows 1 and 2). Every other batch-wide outcome did
        reach, or may have reached, the engine, so the postcondition and the
        transition are UNOBSERVED (rows 3 to 6) -- unobserved, not
        unsatisfied.
        """
        outcome = observation.outcome
        applied = outcome.dispatch is DispatchFact.ACCEPTED
        if outcome.dispatch in {DispatchFact.NOT_SUBMITTED, DispatchFact.REJECTED}:
            postcondition = PostconditionFact.NOT_APPLICABLE
            transition = TransitionFact.NOT_APPLICABLE
        else:
            postcondition = PostconditionFact.UNOBSERVED
            transition = TransitionFact.UNOBSERVED
        return RuntimeActionMutation(
            action_id=action.id,
            applied=applied,
            operation=action.operation,
            batch_id=batch_id,
            dispatch=outcome.dispatch,
            result=outcome.result,
            postcondition=postcondition,
            transition=transition,
            footprint=FootprintFact.NOT_APPLICABLE,
            attempted=None,
            cause=sanitized_detail(outcome.detail),
            message=observation.message,
        )

    def _row_mutation(
        self,
        action: ServiceAction,
        row: dict | None,
        batch_id: str,
        note: str,
    ) -> RuntimeActionMutation:
        """Derive one action's facts from its reported row.

        A row that is absent or inadmissible is row 7, not row 15: this
        adapter holds the observed ACCEPTED, CORRELATED envelope, so channel
        acceptance IS proven for this batch and only the action's own outcome
        is unknown. The applicator, which holds no envelope, must not reach
        the same conclusion from a missing item.

        The row's `call_error` reaches `RuntimeActionMutation.call_error` on
        every admitted row, whatever `cause` the row needs for its canonical
        reason. The two fields are not alternatives.
        """
        if row is None:
            return self._invalid_row_mutation(action, batch_id, "row_missing", note)
        check = self._row_invalid_check(row)
        if check:
            return self._invalid_row_mutation(
                action,
                batch_id,
                f"row_invalid:{check}",
                note,
            )

        attempted = bool(row["attempted"])
        call_error = sanitized_detail(row["call_error"])
        if row["skip_reason"] == _SKIP_FAMILY_NOT_IMPLEMENTED:
            return RuntimeActionMutation(
                action_id=action.id,
                applied=True,
                operation=action.operation,
                batch_id=batch_id,
                dispatch=DispatchFact.ACCEPTED,
                result=ResultFact.CORRELATED,
                postcondition=PostconditionFact.UNOBSERVED,
                transition=TransitionFact.NOT_APPLICABLE,
                footprint=FootprintFact.NOT_APPLICABLE,
                attempted=False,
                message="The runtime declines this action family." + note,
            )

        footprint = self._footprint(action, attempted=attempted)
        if not row["post_read"]:
            return RuntimeActionMutation(
                action_id=action.id,
                applied=True,
                operation=action.operation,
                batch_id=batch_id,
                dispatch=DispatchFact.ACCEPTED,
                result=ResultFact.CORRELATED,
                postcondition=PostconditionFact.UNOBSERVED,
                transition=TransitionFact.UNOBSERVED,
                footprint=footprint,
                attempted=attempted,
                cause=call_error,
                call_error=call_error,
                message="The post-read did not complete." + note,
            )

        postcondition = (
            PostconditionFact.SATISFIED if row["ok"] else PostconditionFact.UNSATISFIED
        )
        if not row["pre_read"]:
            # The canonical reason is the table's `pre_read_failed`, so this
            # row states none of its own. The setter's own diagnostic is a
            # different meaning and travels in `call_error`; assigning it here
            # would have let a vendor message stand where the classification
            # belongs, and leaving it out entirely dropped it (R5).
            transition = TransitionFact.UNOBSERVED
            cause = ""
        else:
            transition = (
                TransitionFact.CHANGED if row["changed"] else TransitionFact.UNCHANGED
            )
            if footprint is FootprintFact.PARTIAL and attempted:
                cause = _DNS_PARTIAL_FOOTPRINT
            else:
                cause = call_error
        return RuntimeActionMutation(
            action_id=action.id,
            applied=True,
            operation=action.operation,
            batch_id=batch_id,
            dispatch=DispatchFact.ACCEPTED,
            result=ResultFact.CORRELATED,
            postcondition=postcondition,
            transition=transition,
            footprint=footprint,
            attempted=attempted,
            cause=cause,
            call_error=call_error,
            message=self._row_message(row, attempted=attempted) + note,
        )

    @staticmethod
    def _invalid_row_mutation(
        action: ServiceAction,
        batch_id: str,
        cause: str,
        note: str,
    ) -> RuntimeActionMutation:
        """Report row 7 for an action whose own row said nothing usable."""
        return RuntimeActionMutation(
            action_id=action.id,
            applied=True,
            operation=action.operation,
            batch_id=batch_id,
            dispatch=DispatchFact.ACCEPTED,
            result=ResultFact.CORRELATED,
            postcondition=PostconditionFact.UNOBSERVED,
            transition=TransitionFact.UNOBSERVED,
            footprint=FootprintFact.NOT_APPLICABLE,
            attempted=None,
            cause=cause,
            message=f"The batch response carried no admissible row: {cause}.{note}",
        )

    @staticmethod
    def _row_message(row: dict, *, attempted: bool) -> str:
        """Describe one admitted row without asserting anything from it."""
        if not attempted:
            return "The setter was not called: the pre-read already showed the state."
        if row["ok"]:
            return "The post-read showed the intended state."
        return "The post-read did not show the intended state."

    @staticmethod
    def _footprint(action: ServiceAction, *, attempted: bool) -> FootprintFact:
        """State whether the read covers everything the setter can change.

        A skipped add is COVERED because no call was made: the ABSENCE of the
        call proves no effect, and that is a stronger proof than any read. An
        attempted add is PARTIAL because a false/false membership cannot
        distinguish "nothing changed" from "a different record was written",
        and a false/true membership cannot say what happened to an existing
        record for the same name.
        """
        if not attempted:
            return FootprintFact.COVERED
        if isinstance(action, AddDnsRecord):
            return FootprintFact.PARTIAL
        return FootprintFact.COVERED

    @staticmethod
    def _row_invalid_check(row: dict) -> str:
        """Name the first contract check the row fails, or "" when admissible.

        Flags must be actual booleans. `isinstance(value, bool)` is the point:
        numeric `0` and `1` compare equal to False and True, so an
        equality-based membership test would admit a row whose flags are
        integers and treat an engine that reported `ok=1` as if it had
        reported a boolean.
        """
        for key in _ROW_KEYS:
            if key not in row:
                return f"absent_{key}"
        for key in ("attempted", "pre_read", "post_read"):
            if not isinstance(row[key], bool):
                return f"{key}_type"
        for key in ("ok", "changed", "call_result"):
            if row[key] is not None and not isinstance(row[key], bool):
                return f"{key}_type"
        for key in ("pre", "post"):
            if row[key] is not None and not isinstance(row[key], str):
                return f"{key}_type"
        for key in ("call_error", "skip_reason"):
            if not isinstance(row[key], str):
                return f"{key}_type"

        if not row["post_read"]:
            if row["ok"] is not None or row["changed"] is not None:
                return "post_read_false_requires_null"
        elif not isinstance(row["ok"], bool):
            return "post_read_requires_ok"
        if row["pre_read"] and row["post_read"]:
            if row["changed"] is None:
                return "complete_reads_require_changed"
        elif row["changed"] is not None:
            return "incomplete_reads_require_null_changed"

        if row["attempted"]:
            if row["skip_reason"]:
                return "attempted_requires_empty_skip_reason"
            return ""
        if row["skip_reason"] not in {
            _SKIP_ALREADY_SATISFIED,
            _SKIP_FAMILY_NOT_IMPLEMENTED,
        }:
            return "skip_reason_unknown"
        if row["call_result"] is not None:
            return "skipped_requires_no_call_result"
        if row["call_error"]:
            return "skipped_requires_no_call_error"
        if row["skip_reason"] == _SKIP_ALREADY_SATISFIED:
            if not row["pre_read"]:
                return "already_satisfied_requires_pre_read"
            # A skip is justified by the pre-read. If the post-read then says
            # the state is not there, the two readings contradict each other
            # and the row cannot be used to claim a satisfied no-op.
            if row["post_read"] and row["ok"] is not True:
                return "already_satisfied_contradicted"
        elif row["pre_read"] or row["post_read"]:
            return "declined_requires_no_reads"
        return ""

    @staticmethod
    def _mutation_lines(action: ServiceAction) -> list[str]:
        """Generate one action's pre-read, setter and unconditional post-read.

        Each of the three steps has its own try/catch, so a setter that throws
        does not hide a post-read that would have shown its effect, and a
        failed pre-read does not stop the post-read from running.
        """
        action_id = json.dumps(action.id)
        row = (
            "var r={id:"
            + action_id
            + ',attempted:false,skip_reason:"",call_error:"",call_result:null,'
            "pre_read:false,post_read:false,ok:null,changed:null,pre:null,post:null};"
        )
        if isinstance(action, PublishTftpFile):
            # A declined family: no process lookup, no call, no reads. The
            # baseline reported `ok=false` here and the outcome stays FAILED.
            return [
                row,
                'r.skip_reason="' + _SKIP_FAMILY_NOT_IMPLEMENTED + '";results.push(r);',
            ]

        process = json.dumps(_PROCESS[action.service_type])
        read, setter, ok_expression = PacketTracerEnterpriseServiceRuntime._family(
            action
        )
        lines = [
            row,
            f"var p=d.getProcess({process});var pv=null,qv=null;",
            f"try{{pv={read};r.pre_read=true;r.pre=__dg(pv);}}catch(e){{}}",
        ]
        if isinstance(action, AddDnsRecord):
            # Ensure-present: the pre-read already showing the wanted record is
            # what justifies not calling the add at all.
            lines.append(
                'if(r.pre_read&&pv===true){r.skip_reason="'
                + _SKIP_ALREADY_SATISFIED
                + '";}else{try{r.attempted=true;r.call_result='
                + setter
                + ";}catch(e){r.call_error=__er(e);}}"
            )
        else:
            lines.append(
                "try{r.attempted=true;" + setter + ";}catch(e){r.call_error=__er(e);}"
            )
        lines.append(f"try{{qv={read};r.post_read=true;r.post=__dg(qv);}}catch(e){{}}")
        lines.append(f"if(r.post_read){{r.ok=({ok_expression});}}")
        lines.append("if(r.pre_read&&r.post_read){r.changed=(pv!==qv);}")
        lines.append("results.push(r);")
        return lines

    @staticmethod
    def _family(action: ServiceAction) -> tuple[str, str, str]:
        """Return the typed read, the setter call, and the `ok` predicate.

        `ok` is computed from the actual typed post value `qv`, never from a
        digest and never from the setter's own return: an ensure-present call
        that returns true has not been read back, and a return value is not an
        observation of state.
        """
        if isinstance(action, EnableDnsService | EnableHttpService):
            return "!!p.isEnabled()", "p.setEnable(true)", "qv===true"
        if isinstance(action, EnableHttpsService):
            return "!!p.isHttpsEnabled()", "p.setHttpsEnable(true)", "qv===true"
        if isinstance(action, SetHttpContent):
            path = json.dumps(action.path)
            content = json.dumps(action.content)
            return (
                f"String(p.getPage({path}))",
                f"p.setPageContents({path},{content})",
                f"qv==={content}",
            )
        if isinstance(action, AddDnsRecord):
            hostname = json.dumps(action.hostname)
            address = json.dumps(action.address)
            return (
                f"!!p.getARecordWithAddress({hostname},{address})",
                f"!!p.addARecordToNameServerDb({hostname},{address})",
                "qv===true",
            )
        if isinstance(action, ConfigureNtpService | EnableTftpService):
            return "!!p.isEnabled()", "p.setEnabled(true)", "qv===true"
        raise ValueError(f"No registered mutation family for {type(action).__name__}.")

    # -- verification ---------------------------------------------------

    def verify(
        self,
        expectation: ServiceVerificationExpectation,
    ) -> RuntimeServiceVerification:
        """Observe one expectation and state the observation fact it supports.

        Any exception raised while observing is caught here and reported as
        UNKNOWN with `exception:<TypeName>`. A reader that crashed observed
        nothing, and an uncaught error at this boundary would be recorded by
        the applicator as a session failure of the whole plan.
        """
        try:
            return self._verify(expectation)
        except Exception as error:
            return RuntimeServiceVerification(
                expectation_id=expectation.id,
                status=ActionExecutionStatus.UNKNOWN,
                evidence_kind=expectation.evidence_kind,
                evidence_method="typed_client_operation",
                fresh_evidence=False,
                observation=ObservationFact.INCONCLUSIVE,
                cause=f"exception:{type(error).__name__}",
                message="The verification reader raised before observing anything.",
            )

    def _verify(
        self,
        expectation: ServiceVerificationExpectation,
    ) -> RuntimeServiceVerification:
        """Route one expectation to its reader."""
        if expectation.evidence_kind is ServiceEvidenceKind.DIRECT_STATE:
            return self._verify_direct(expectation)
        if expectation.kind in {
            ServiceVerificationKind.DNS_RESOLUTION,
            ServiceVerificationKind.DNS_NEGATIVE_CONTROL,
        }:
            return self._verify_dns(expectation)
        if expectation.kind in {
            ServiceVerificationKind.HTTP_FETCH,
            ServiceVerificationKind.HTTPS_FETCH,
            ServiceVerificationKind.HTTP_BY_HOSTNAME,
        }:
            return self._verify_http(expectation)
        return RuntimeServiceVerification(
            expectation_id=expectation.id,
            status=ActionExecutionStatus.UNOBSERVABLE,
            evidence_kind=expectation.evidence_kind,
            evidence_method="packet_tracer_client_observation_unavailable",
            fresh_evidence=False,
            observation=ObservationFact.NOT_ATTEMPTED,
            cause="no_registered_client_proof",
            message=(
                "Packet Tracer exposes no registered independent client proof "
                "for this service."
            ),
        )

    def _observed(
        self,
        expectation: ServiceVerificationExpectation,
        *,
        observation: ObservationFact,
        method: str,
        claim_level: str = "",
        cause: str = "",
        message: str = "",
        observed: dict[str, str | int | bool] | None = None,
        limitations: Sequence[str] = (),
    ) -> RuntimeServiceVerification:
        """Build one verification row from its observation fact.

        The status comes from the fact, not from a second interpretation of the
        same reading, which is what let a lost result and a contradicted read
        share one status.
        """
        status, fresh = _OBSERVATION_STATUS[observation]
        return RuntimeServiceVerification(
            expectation_id=expectation.id,
            status=status,
            evidence_kind=expectation.evidence_kind,
            evidence_method=method,
            fresh_evidence=fresh,
            observed=dict(observed or {}),
            observation=observation,
            cause=sanitized_detail(cause),
            claim_level=claim_level,
            limitations=list(limitations),
            message=message,
        )

    @staticmethod
    def _transport_fact(observation: BridgeObservation) -> ObservationFact:
        """Name which way a read failed to deliver a correlated answer."""
        if observation.kind is BridgeObservationKind.ENGINE_ERROR:
            return ObservationFact.ENGINE_ERROR
        if observation.kind is BridgeObservationKind.MALFORMED:
            return ObservationFact.MALFORMED
        dispatch = observation.outcome.dispatch
        if dispatch is DispatchFact.NOT_SUBMITTED:
            return ObservationFact.NOT_SUBMITTED
        if dispatch is DispatchFact.REJECTED:
            return ObservationFact.REJECTED
        if dispatch is DispatchFact.ACCEPTANCE_UNKNOWN:
            return ObservationFact.ACCEPTANCE_UNKNOWN
        if observation.outcome.result is ResultFact.LOST:
            return ObservationFact.LOST
        return ObservationFact.NOT_OBSERVED

    def _verify_direct(self, expectation):
        """Read the service's own getters back and compare typed values."""
        service_type = ServiceType(str(expectation.expected.get("service_type")))
        process = _PROCESS[service_type]
        host = json.dumps(expectation.host_device_name)
        lines = [
            f"var d=ipc.network().getDevice({host});var p=d&&d.getProcess({json.dumps(process)});",
            "var out={found:!!p,enabled:false};if(p){",
        ]
        if service_type is ServiceType.HTTPS:
            lines.append("out.enabled=!!p.isHttpsEnabled();")
        else:
            lines.append("out.enabled=!!p.isEnabled();")
        if service_type is ServiceType.DNS:
            records = str(expectation.expected.get("records_json") or "{}")
            lines.append(
                "out.records={};var wanted=JSON.parse(" + json.dumps(records) + ");"
                "for(var k in wanted){if(p.getARecordWithAddress(k,wanted[k])){"
                "out.records[k]=wanted[k];}}"
            )
        elif service_type in {ServiceType.HTTP, ServiceType.HTTPS}:
            lines.append("out.content=String(p.getPage('index.html'));")
        lines.append("}reportResult(JSON.stringify(out));")
        observation = self._observe("".join(lines), 5.0)
        method = "structured_service_getters"
        claim = "direct_service_state"
        if observation.kind is not BridgeObservationKind.PAYLOAD:
            return self._observed(
                expectation,
                observation=self._transport_fact(observation),
                method=method,
                claim_level=claim,
                cause=observation.outcome.detail,
                message="The direct read-back did not deliver a correlated answer.",
            )

        payload = observation.payload or {}
        found = payload.get("found")
        enabled = payload.get("enabled")
        if not isinstance(found, bool) or not isinstance(enabled, bool):
            return self._observed(
                expectation,
                observation=ObservationFact.MALFORMED,
                method=method,
                claim_level=claim,
                cause="typed_shape_missing",
                message="The direct read-back payload is not the typed shape.",
            )
        if not found:
            return self._observed(
                expectation,
                observation=ObservationFact.SUBJECT_NOT_FOUND,
                method=method,
                claim_level=claim,
                cause="process_not_found",
                message="The service process was not present on the device.",
            )

        matches = enabled
        if service_type is ServiceType.DNS:
            records = payload.get("records")
            if not isinstance(records, dict):
                return self._observed(
                    expectation,
                    observation=ObservationFact.MALFORMED,
                    method=method,
                    claim_level=claim,
                    cause="records_not_an_object",
                    message="The direct read-back payload is not the typed shape.",
                )
            wanted = json.loads(str(expectation.expected.get("records_json") or "{}"))
            matches = matches and records == wanted
        elif service_type in {ServiceType.HTTP, ServiceType.HTTPS}:
            content = payload.get("content")
            if not isinstance(content, str):
                return self._observed(
                    expectation,
                    observation=ObservationFact.MALFORMED,
                    method=method,
                    claim_level=claim,
                    cause="content_not_a_string",
                    message="The direct read-back payload is not the typed shape.",
                )
            marker = str(expectation.expected.get("marker") or "")
            matches = matches and (not marker or marker in content)
        return self._observed(
            expectation,
            observation=(
                ObservationFact.OBSERVED if matches else ObservationFact.CONTRADICTED
            ),
            method=method,
            claim_level=claim,
            observed={"enabled": enabled},
            message=(
                "Structured service state matched."
                if matches
                else "Structured service state differed."
            ),
        )

    def _verify_dns(self, expectation):
        """Type one `ping <hostname>` and read only the window it opened."""
        negative = expectation.kind is ServiceVerificationKind.DNS_NEGATIVE_CONTROL
        method = (
            "typed_pc_ping_hostname_negative_control"
            if negative
            else "typed_pc_ping_hostname_fresh_output"
        )
        claim = "independent_client_observation"
        hostname = str(expectation.expected.get("hostname") or "")
        if not _HOSTNAME.fullmatch(hostname):
            # An admission error, not an observation: nothing was attempted,
            # and the baseline definite failure is preserved.
            return RuntimeServiceVerification(
                expectation_id=expectation.id,
                status=ActionExecutionStatus.FAILED,
                evidence_kind=expectation.evidence_kind,
                evidence_method="typed_client_operation",
                fresh_evidence=False,
                observation=ObservationFact.NOT_ATTEMPTED,
                cause="invalid_hostname",
                claim_level=claim,
                message="DNS verification hostname is invalid.",
            )
        expected = ""
        if not negative:
            # The positive expectation is compared to a parsed address, so an
            # expectation that is not an address cannot be compared at all.
            # The substring test hid this: an empty expected address was
            # contained in every window and passed (R3b).
            try:
                expected = str(
                    ip_address(str(expectation.expected.get("address") or ""))
                )
            except ValueError:
                return RuntimeServiceVerification(
                    expectation_id=expectation.id,
                    status=ActionExecutionStatus.FAILED,
                    evidence_kind=expectation.evidence_kind,
                    evidence_method="typed_client_operation",
                    fresh_evidence=False,
                    observation=ObservationFact.NOT_ATTEMPTED,
                    cause="invalid_expected_address",
                    claim_level=claim,
                    message="DNS verification expected address is invalid.",
                )
        client = json.dumps(expectation.client_device_name)
        command = "ping " + hostname
        command_json = json.dumps(command)
        start = self._observe(
            f"var d=ipc.network().getDevice({client});"
            "var cp=d&&typeof d.getCommandPrompt==='function'?d.getCommandPrompt():null;"
            "var before=cp&&typeof cp.getOutput==='function'?String(cp.getOutput()):'';"
            + PAGER_GUARD_JS
            +
            # Misma frontera que el resto: tipear sobre un pager activo se come
            # el primer caracter del comando.
            "var started=false;var blocked=false;"
            "if(__pager){blocked=true;}"
            "else if(cp&&typeof cp.enterCommand==='function'){"
            f"cp.enterCommand({command_json});started=true;}}"
            "reportResult(JSON.stringify({started:started,blocked:blocked,before:before}));",
            5.0,
        )
        if start.kind is not BridgeObservationKind.PAYLOAD:
            return self._observed(
                expectation,
                observation=self._transport_fact(start),
                method=method,
                claim_level=claim,
                cause=start.outcome.detail,
                message="The typed DNS ping did not deliver a correlated answer.",
            )
        payload = start.payload or {}
        shape = _typed_payload(
            payload,
            {"started": bool, "blocked": bool, "before": str},
        )
        if shape:
            return self._observed(
                expectation,
                observation=ObservationFact.MALFORMED,
                method=method,
                claim_level=claim,
                cause=f"start_shape:{shape}",
                message="The typed DNS ping start payload is not the typed shape.",
            )
        if payload["blocked"]:
            return self._observed(
                expectation,
                observation=ObservationFact.INCONCLUSIVE,
                method=method,
                claim_level=claim,
                cause="pager_active",
                message="Typed DNS ping was refused: the terminal pager was active.",
            )
        if not payload["started"]:
            return self._observed(
                expectation,
                observation=ObservationFact.INCONCLUSIVE,
                method=method,
                claim_level=claim,
                cause="command_not_started",
                message="Typed DNS ping did not start.",
            )
        before = payload["before"]

        def inspect():
            return self._observe(
                f"var d=ipc.network().getDevice({client});"
                "var cp=d&&typeof d.getCommandPrompt==='function'?d.getCommandPrompt():null;"
                "reportResult(JSON.stringify({found:!!cp,output:cp?String(cp.getOutput()):''}));",
                3.0,
            )

        def complete(item: BridgeObservation) -> bool:
            """Whether this reading already carries a terminal window."""
            if item.kind is not BridgeObservationKind.PAYLOAD:
                return False
            reading = _text_reading(
                item.payload or {}, "output", "command_prompt_absent"
            )
            if not reading.admissible:
                return False
            return self._dns_window_complete(
                self._fresh_command_window(before, reading.content, command)
            )

        observed = self._poll(inspect, complete, self._dns_timeout)
        if observed.kind is not BridgeObservationKind.PAYLOAD:
            return self._observed(
                expectation,
                observation=self._transport_fact(observed),
                method=method,
                claim_level=claim,
                cause=observed.outcome.detail,
                message="The DNS command window could not be read.",
            )
        reading = _text_reading(
            observed.payload or {}, "output", "command_prompt_absent"
        )
        if not reading.admissible:
            return self._observed(
                expectation,
                observation=reading.fact,
                method=method,
                claim_level=claim,
                cause=reading.cause,
                message="The DNS command window read did not observe its subject.",
            )
        window = self._fresh_command_window(before, reading.content, command)
        if not self._dns_window_complete(window):
            # Nothing terminal arrived in this command's own window. An
            # incomplete window decides neither direction.
            return self._observed(
                expectation,
                observation=ObservationFact.INCONCLUSIVE,
                method=method,
                claim_level=claim,
                cause="incomplete_window",
                message="The DNS command window was still incomplete at the deadline.",
            )
        not_found = bool(_NOT_FOUND.search(window))
        if negative:
            return self._observed(
                expectation,
                observation=(
                    ObservationFact.OBSERVED
                    if not_found
                    else ObservationFact.CONTRADICTED
                ),
                method=method,
                claim_level=claim,
                observed={"hostname": hostname, "resolved": False} if not_found else {},
                message=(
                    "DNS negative control did not resolve."
                    if not_found
                    else "Fresh DNS command output contradicted the expectation."
                ),
            )
        if not_found:
            return self._observed(
                expectation,
                observation=ObservationFact.CONTRADICTED,
                method=method,
                claim_level=claim,
                cause="host_not_found",
                message="Fresh DNS command output contradicted the expectation.",
            )
        resolved, reason = _dns_resolution(window)
        if not resolved:
            # The window is terminal but does not report a single parsed
            # address, so it supports no comparison in either direction.
            return self._observed(
                expectation,
                observation=ObservationFact.INCONCLUSIVE,
                method=method,
                claim_level=claim,
                cause=reason,
                message="The DNS command window reported no readable address.",
            )
        matched = resolved == expected
        return self._observed(
            expectation,
            observation=(
                ObservationFact.OBSERVED if matched else ObservationFact.CONTRADICTED
            ),
            method=method,
            claim_level=claim,
            observed={"hostname": hostname, "address": resolved},
            message=(
                "DNS resolved expected address."
                if matched
                else "Fresh DNS command output contradicted the expectation."
            ),
        )

    @staticmethod
    def _fresh_command_window(before: str, after: str, command: str) -> str:
        """Return only the output this command added to the terminal."""
        if after.startswith(before) and len(after) > len(before):
            return after[len(before) :]
        index = after.casefold().rfind(command.casefold())
        return after[index:] if index >= 0 and after[index:] != before[index:] else ""

    @staticmethod
    def _dns_window_complete(window: str) -> bool:
        """Whether the window already carries a terminal line to read.

        Completeness is a property of the OUTPUT, not of the expectation. The
        positive case used to require the expected address as a substring
        before it would stop polling, so a complete window that resolved a
        DIFFERENT address never satisfied the predicate and was then read at
        the deadline as an incomplete window instead of as the fresh
        contradiction it is (R3b).
        """
        if not window:
            return False
        return bool(_NOT_FOUND.search(window) or "packets: sent" in window.casefold())

    def _verify_http(self, expectation):
        """Fetch with an owned client and finalize that client on every exit.

        The reader and the finalization are deliberately separate paths. The
        fetch decides one primary fact and records in the lease what it may
        own; this method then releases that ownership exactly once, whatever
        the fetch returned or raised, and attaches the cleanup outcome
        without touching the primary fact. Before that split, five of the
        reader's exits released nothing at all -- a start that delivered no
        correlated answer returned immediately, and an exception anywhere in
        the polling escaped to `verify` -- so a client that had already been
        created stayed alive and untracked (R1).
        """
        scheme = str(expectation.expected.get("scheme") or "http").casefold()
        claim = "independent_client_observation"
        if scheme not in {"http", "https"}:
            # An admission error: nothing is dispatched, so nothing is owned.
            return RuntimeServiceVerification(
                expectation_id=expectation.id,
                status=ActionExecutionStatus.FAILED,
                evidence_kind=expectation.evidence_kind,
                evidence_method="typed_client_operation",
                fresh_evidence=False,
                observation=ObservationFact.NOT_ATTEMPTED,
                cause="scheme_not_registered",
                claim_level=claim,
                message="Web verification scheme is not registered.",
            )
        lease = ClientLease()
        try:
            row = self._web_fetch(expectation, scheme, lease)
        except Exception as error:
            # Caught HERE, not in `verify`: a reader that raised observed
            # nothing, and the client it may already own still has to be
            # released before this row leaves the reader.
            row = self._observed(
                expectation,
                observation=ObservationFact.INCONCLUSIVE,
                method=f"{scheme}_client_fresh_content",
                claim_level=claim,
                cause=f"exception:{type(error).__name__}",
                message="The web reader raised before completing its observation.",
            )
        return self._with_release(row, self._finalize_client(expectation, lease))

    def _web_fetch(self, expectation, scheme: str, lease: ClientLease):
        """Observe one web fetch, recording ownership in `lease` as it moves.

        Every stage validates the shape it is about to read before it reads
        it. `started` must be an actual boolean, page text must be actual
        text, and the inspection's own `found` flag decides whether there is
        a page at all: coercing those made `{"found": false, "content":
        {"unexpected": "AUDIT_MARKER"}}` a matching page (R3a).
        """
        marker = str(expectation.expected.get("marker") or "")
        target = str(
            expectation.expected.get("hostname")
            or expectation.expected.get("address")
            or ""
        )
        claim = "independent_client_observation"
        method = f"{scheme}_client_fresh_content"
        secure = scheme == "https"
        client = json.dumps(expectation.client_device_name)
        url = json.dumps(scheme + "://" + target + "/")
        if secure:
            start_js = (
                f"var d=ipc.network().getDevice({client});"
                + self._background_https_start(expectation.id, url)
                + "var before=content_before;"
                "reportResult(JSON.stringify({started:started,"
                "content_before:before,https_mode:https_mode,owned:owned}));"
            )
        else:
            start_js = (
                f"var d=ipc.network().getDevice({client});"
                + self._background_http_start(expectation.id, url)
                + "var before=content_before;"
                "reportResult(JSON.stringify({started:started,"
                "content_before:before,owned:owned}));"
            )
        # Set BEFORE the dispatch: from here on the script may have created
        # and tracked a client whatever the channel reports back, so the
        # finalization must look rather than assume.
        lease.state = ClientOwnership.UNKNOWN
        start = self._observe(start_js, 5.0)
        if start.kind is not BridgeObservationKind.PAYLOAD:
            return self._observed(
                expectation,
                observation=self._transport_fact(start),
                method=method,
                claim_level=claim,
                cause=start.outcome.detail,
                message="The client request did not deliver a correlated answer.",
            )
        payload = start.payload or {}
        owned = payload.get("owned")
        if isinstance(owned, bool):
            # The one field that reports ownership decides the lease, even if
            # the rest of the payload turns out to be inadmissible.
            lease.state = ClientOwnership.OWNED if owned else ClientOwnership.ABSENT
        else:
            return self._observed(
                expectation,
                observation=ObservationFact.MALFORMED,
                method=method,
                claim_level=claim,
                cause=f"start_shape:{_typed_payload(payload, {'owned': bool})}",
                message="The start payload did not report client ownership.",
            )
        if not owned:
            # No client exists, so nothing about the server was observed and
            # there is no page to attribute anything to.
            return self._observed(
                expectation,
                observation=ObservationFact.SUBJECT_NOT_FOUND,
                method=method,
                claim_level=claim,
                cause="client_not_created",
                message="The device did not provide a background HTTP client.",
            )
        shape = _typed_payload(payload, {"content_before": str, "started": bool})
        if shape:
            return self._observed(
                expectation,
                observation=ObservationFact.MALFORMED,
                method=method,
                claim_level=claim,
                cause=f"start_shape:{shape}",
                message="The start payload is not the typed shape.",
            )
        if secure:
            mode = payload.get("https_mode")
            if not isinstance(mode, bool):
                # Absent is neither false nor true: the payload did not report
                # the mode, so nothing about the listener was observed.
                return self._observed(
                    expectation,
                    observation=ObservationFact.MALFORMED,
                    method=method,
                    claim_level=claim,
                    cause="https_mode_absent",
                    message="The start payload did not report the client HTTPS mode.",
                )
            if not mode:
                return self._observed(
                    expectation,
                    observation=ObservationFact.CONTRADICTED,
                    method=method,
                    claim_level=claim,
                    cause="https_mode_not_confirmed",
                    message="The client did not confirm HTTPS mode after setHttps.",
                )
        before = payload["content_before"]
        if not payload["started"]:
            return self._observed(
                expectation,
                observation=ObservationFact.INCONCLUSIVE,
                method=method,
                claim_level=claim,
                cause="client_go_false",
                message="The client did not start the request.",
            )
        if marker and marker in before:
            return self._observed(
                expectation,
                observation=ObservationFact.INCONCLUSIVE,
                method=method,
                claim_level=claim,
                cause="marker_present_before_request",
                message=(
                    "The expected marker already existed before this request, so "
                    "no content can be attributed to it."
                ),
            )

        def inspect():
            return self._observe(self._background_http_inspect(expectation.id), 3.0)

        def fresh(item: BridgeObservation) -> bool:
            """Whether this reading is an admissible, fresh, matching page."""
            if item.kind is not BridgeObservationKind.PAYLOAD:
                return False
            reading = _text_reading(
                item.payload or {}, "content", "owned_client_absent"
            )
            return bool(
                reading.admissible
                and reading.content
                and reading.content != before
                and (not marker or marker in reading.content)
            )

        observed = self._poll(inspect, fresh, self._http_timeout)
        if observed.kind is not BridgeObservationKind.PAYLOAD:
            return self._observed(
                expectation,
                observation=self._transport_fact(observed),
                method=method,
                claim_level=claim,
                cause=observed.outcome.detail,
                message="The client page content could not be read.",
            )
        reading = _text_reading(
            observed.payload or {}, "content", "owned_client_absent"
        )
        if not reading.admissible:
            return self._observed(
                expectation,
                observation=reading.fact,
                method=method,
                claim_level=claim,
                cause=reading.cause,
                message="The client page read did not observe its subject.",
            )
        content = reading.content
        if not content or content == before:
            return self._observed(
                expectation,
                observation=ObservationFact.INCONCLUSIVE,
                method=method,
                claim_level=claim,
                cause="no_response_within_deadline",
                message="No content change was observed before the deadline.",
            )
        if marker and marker not in content:
            return self._observed(
                expectation,
                observation=ObservationFact.CONTRADICTED,
                method=method,
                claim_level=claim,
                message=f"Fresh {scheme.upper()} content contradicted the expectation.",
            )
        row = self._observed(
            expectation,
            observation=ObservationFact.OBSERVED,
            method=method,
            claim_level=claim,
            observed={
                "marker": marker,
                "target": target,
                "scheme": scheme,
            },
            message=f"Fresh {scheme.upper()} content matched the expectation.",
            limitations=["no_https_marker"] if secure and not marker else [],
        )
        if secure and not marker:
            # The content changed and the client reported HTTPS mode, but with
            # no marker nothing ties the page to the HTTPS listener rather than
            # to any other reachable page. The observation stands; the claim
            # does not (R-HTTPS-03).
            return row.model_copy(
                update={
                    "status": ActionExecutionStatus.PARTIAL,
                    "message": (
                        "Fresh HTTPS content was observed, but with no marker it "
                        "cannot be attributed to the HTTPS listener."
                    ),
                },
            )
        return row

    @staticmethod
    def _background_http_start(expectation_id: str, url_json: str) -> str:
        """Create one owned client, track it at once, and start the request.

        The tracking assignment is the FIRST thing after `createClient()`,
        before the initial page read and before `go()`. It used to happen
        only after `go()` returned true, so any throw in between -- and a
        `go()` that returned false -- left a live client that no slot named.
        A later release then found no slot and reported success while the
        client was still there, which is the ownership hole R1 names. The
        stale slot is dropped only once the previous client has actually been
        deleted, so a client that could not be deleted stays named by its
        slot instead of being forgotten.
        """
        key = json.dumps(expectation_id)
        return (
            'var m=d&&d.getProcess("HttpBackgroundClientManager");'
            "this.__mcpE6HttpClients=this.__mcpE6HttpClients||{};"
            f"var old=this.__mcpE6HttpClients[{key}];"
            "if(old&&old.manager&&old.client){old.manager.deleteClient(old.client);}"
            f"delete this.__mcpE6HttpClients[{key}];"
            "var p=m&&m.createClient();"
            f"if(m&&p){{this.__mcpE6HttpClients[{key}]={{manager:m,client:p}};}}"
            "var owned=!!(m&&p);"
            "var content_before=p?String(p.getLastPageContent()):'';"
            f"var started=!!(p&&p.go({url_json}));"
        )

    @staticmethod
    def _background_https_start(expectation_id: str, url_json: str) -> str:
        """Start the request as HTTP does, plus an affirmative mode read.

        `HttpClient::setHttps(bool)` and `isHttps()` are documented members
        inherited by `HttpBackgroundClient` (`[CISCO]`
        `help/default/IpcAPI/class_http_client.html`). Setting the mode before
        `go()` and reading it back in the same payload is what makes "this
        client was in HTTPS mode" an observation instead of an assumption
        drawn from the URL scheme.
        """
        key = json.dumps(expectation_id)
        return (
            'var m=d&&d.getProcess("HttpBackgroundClientManager");'
            "this.__mcpE6HttpClients=this.__mcpE6HttpClients||{};"
            f"var old=this.__mcpE6HttpClients[{key}];"
            "if(old&&old.manager&&old.client){old.manager.deleteClient(old.client);}"
            f"delete this.__mcpE6HttpClients[{key}];"
            "var p=m&&m.createClient();"
            f"if(m&&p){{this.__mcpE6HttpClients[{key}]={{manager:m,client:p}};}}"
            "var owned=!!(m&&p);"
            "var content_before=p?String(p.getLastPageContent()):'';"
            "if(p){p.setHttps(true);}var https_mode=p?!!p.isHttps():null;"
            f"var started=!!(p&&p.go({url_json}));"
        )

    @staticmethod
    def _background_http_inspect(expectation_id: str) -> str:
        """Read the page content of the client owned by this expectation."""
        key = json.dumps(expectation_id)
        return (
            "var bag=this.__mcpE6HttpClients||{};"
            f"var slot=bag[{key}];var p=slot&&slot.client;"
            "reportResult(JSON.stringify({found:!!p,content:p?String(p.getLastPageContent()):''}));"
        )

    @staticmethod
    def _background_http_release(expectation_id: str, client_json: str) -> str:
        """Delete the client this expectation owns and report what it saw.

        It reports what it FOUND and what it DID, not whether a slot happens
        to be absent. `released:!slot||!bag[key]` was true whenever the slot
        was missing, so an untracked live client and a successful deletion
        produced the same answer. The deletion is guarded so a throwing
        `deleteClient` still reports, and the slot is dropped only when the
        deletion actually completed: a client that could not be deleted must
        stay named.
        """
        key = json.dumps(expectation_id)
        return (
            f"var d=ipc.network().getDevice({client_json});"
            "var bag=this.__mcpE6HttpClients||{};"
            f"var slot=bag[{key}];"
            "var found=!!(slot&&slot.manager&&slot.client);"
            "var deleted=false;var error='';"
            "if(found){try{slot.manager.deleteClient(slot.client);deleted=true;}"
            "catch(e){try{error=String(e&&e.message?e.message:e).substring(0,200);}"
            "catch(x){error='release_error';}}}"
            f"if(deleted){{delete bag[{key}];}}"
            "reportResult(JSON.stringify({found:found,deleted:deleted,"
            f"present:!!bag[{key}],error:error}}));"
        )

    def _finalize_client(self, expectation, lease: ClientLease) -> ReleaseOutcome:
        """Release whatever this read owns, exactly once, and say what held.

        Bounded on purpose: one dispatch, no redispatch of the start, no
        channel switch and no second attempt. What it cannot establish it
        reports as unresolved ownership rather than as a release, because a
        command that may still execute late can leave a client this process
        will never see.
        """
        if lease.state is ClientOwnership.NONE:
            return ReleaseOutcome(_RELEASE_NOTHING_OWNED, "no_client_requested")
        if lease.state is ClientOwnership.ABSENT:
            return ReleaseOutcome(_RELEASE_NOTHING_OWNED, "client_not_created")
        client = json.dumps(expectation.client_device_name)
        try:
            observation = self._observe(
                self._background_http_release(expectation.id, client),
                3.0,
            )
        except Exception as error:
            # A cleanup that raised replaces no primary fact: it is recorded
            # as its own failed cleanup.
            return ReleaseOutcome(
                _RELEASE_FAILED,
                f"exception:{type(error).__name__}",
            )
        if observation.kind is not BridgeObservationKind.PAYLOAD:
            return ReleaseOutcome(
                _RELEASE_FAILED,
                sanitized_detail(observation.outcome.detail)
                or "release_not_correlated",
            )
        payload = observation.payload or {}
        shape = _typed_payload(
            payload,
            {"found": bool, "deleted": bool, "present": bool},
        )
        if shape:
            return ReleaseOutcome(_RELEASE_UNVERIFIED, f"release_shape:{shape}")
        if payload["deleted"] and not payload["present"]:
            return ReleaseOutcome(_RELEASE_RELEASED)
        if payload["found"]:
            return ReleaseOutcome(
                _RELEASE_UNVERIFIED,
                sanitized_detail(payload.get("error")) or "delete_not_confirmed",
            )
        if lease.state is ClientOwnership.OWNED:
            # The start reported a tracked client and the slot is gone
            # without this release removing it. Something else took it, and
            # that is not proof the client was deleted.
            return ReleaseOutcome(_RELEASE_UNVERIFIED, "owned_slot_absent")
        return ReleaseOutcome(
            _RELEASE_OWNERSHIP_UNKNOWN,
            "start_outcome_unobserved",
        )

    @staticmethod
    def _with_release(row: RuntimeServiceVerification, release: ReleaseOutcome):
        """Attach the finalization outcome without touching the primary fact.

        The two are separate records. A failed cleanup never overwrites the
        observation, its status, its cause or its freshness, and an
        unresolved ownership never disappears just because the read itself
        succeeded.
        """
        observed = dict(row.observed)
        observed["released"] = release.outcome
        limitations = list(row.limitations)
        if not release.resolved:
            detail = f":{release.cause}" if release.cause else ""
            limitations.append(f"client_ownership_unresolved:{release.outcome}{detail}")
        return row.model_copy(
            update={"observed": observed, "limitations": limitations},
        )

    def _poll(self, inspect, predicate, timeout):
        """Poll one reader until its predicate holds or the deadline passes."""
        deadline = self._clock() + timeout
        while True:
            last = inspect()
            if predicate(last) or self._clock() >= deadline:
                return last
            self._sleep(self._interval)

    # -- transport ------------------------------------------------------

    def _observe(self, js: str, timeout: float) -> BridgeObservation:
        """Dispatch one command and classify what came back.

        The four outcomes are separate because they authorize different
        things. A Packet Tracer exception and a non-JSON answer both mean the
        read could not observe its subject; a result that never arrived means
        the transport did not deliver one, which is not evidence about the
        subject at all. Collapsing them into `{}` was what made a failed read
        indistinguishable from a device that reported nothing.
        """
        if self._dispatch_and_wait is not None:
            outcome = self._dispatch_and_wait(js, timeout)
        else:
            raw = self._send_and_wait(js, timeout)
            outcome = BridgeDispatchOutcome(
                dispatch=(
                    DispatchFact.ACCEPTED
                    if raw is not None
                    else DispatchFact.ACCEPTANCE_UNKNOWN
                ),
                result=(
                    ResultFact.CORRELATED
                    if raw is not None
                    else ResultFact.NOT_OBSERVED
                ),
                body=raw,
                detail="" if raw is not None else "legacy_send_and_wait_returned_none",
            )
        if outcome.result is not ResultFact.CORRELATED:
            return BridgeObservation(
                kind=BridgeObservationKind.UNOBSERVED,
                payload=None,
                message="No correlated result was observed for this command.",
                outcome=outcome,
            )
        body = outcome.body
        if body is None or body.startswith(("ERROR:", "PT_ERROR:")):
            return BridgeObservation(
                kind=BridgeObservationKind.ENGINE_ERROR,
                payload=None,
                message="Packet Tracer reported an error while evaluating the command.",
                outcome=BridgeDispatchOutcome(
                    dispatch=outcome.dispatch,
                    result=ResultFact.ENGINE_ERROR,
                    disposition=outcome.disposition,
                    detail=sanitized_detail(body or "engine_error"),
                ),
            )
        try:
            value = json.loads(body)
        except (json.JSONDecodeError, TypeError, ValueError):
            value = None
        if not isinstance(value, dict):
            return BridgeObservation(
                kind=BridgeObservationKind.MALFORMED,
                payload=None,
                message="The correlated result was not a JSON object.",
                outcome=BridgeDispatchOutcome(
                    dispatch=outcome.dispatch,
                    result=ResultFact.MALFORMED,
                    disposition=outcome.disposition,
                    detail="not_a_json_object",
                ),
            )
        return BridgeObservation(
            kind=BridgeObservationKind.PAYLOAD,
            payload=value,
            message="",
            outcome=outcome,
        )
