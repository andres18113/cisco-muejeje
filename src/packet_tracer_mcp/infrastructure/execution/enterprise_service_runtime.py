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
                message="The post-read did not complete." + note,
            )

        postcondition = (
            PostconditionFact.SATISFIED if row["ok"] else PostconditionFact.UNSATISFIED
        )
        if not row["pre_read"]:
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
        if payload.get("blocked"):
            return self._observed(
                expectation,
                observation=ObservationFact.INCONCLUSIVE,
                method=method,
                claim_level=claim,
                cause="pager_active",
                message="Typed DNS ping was refused: the terminal pager was active.",
            )
        if not payload.get("started"):
            return self._observed(
                expectation,
                observation=ObservationFact.INCONCLUSIVE,
                method=method,
                claim_level=claim,
                cause="command_not_started",
                message="Typed DNS ping did not start.",
            )
        before = str(payload.get("before") or "")

        def inspect():
            return self._observe(
                f"var d=ipc.network().getDevice({client});"
                "var cp=d&&typeof d.getCommandPrompt==='function'?d.getCommandPrompt():null;"
                "reportResult(JSON.stringify({found:!!cp,output:cp?String(cp.getOutput()):''}));",
                3.0,
            )

        expected = str(expectation.expected.get("address") or "")
        observed = self._poll(
            inspect,
            lambda item: (
                item.kind is BridgeObservationKind.PAYLOAD
                and self._dns_window_complete(
                    self._fresh_command_window(
                        before,
                        str((item.payload or {}).get("output") or ""),
                        command,
                    ),
                    expected,
                    negative,
                )
            ),
            self._dns_timeout,
        )
        if observed.kind is not BridgeObservationKind.PAYLOAD:
            return self._observed(
                expectation,
                observation=self._transport_fact(observed),
                method=method,
                claim_level=claim,
                cause=observed.outcome.detail,
                message="The DNS command window could not be read.",
            )
        window = self._fresh_command_window(
            before,
            str((observed.payload or {}).get("output") or ""),
            command,
        )
        not_found = bool(_NOT_FOUND.search(window))
        resolved = "packets: sent" in window.casefold()
        if not window or not (not_found or resolved):
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
        matched = not_found if negative else (not not_found and expected in window)
        return self._observed(
            expectation,
            observation=(
                ObservationFact.OBSERVED if matched else ObservationFact.CONTRADICTED
            ),
            method=method,
            claim_level=claim,
            observed=(
                {"hostname": hostname, "resolved": False}
                if matched and negative
                else {"hostname": hostname, "address": expected}
                if matched
                else {}
            ),
            message=(
                "DNS negative control did not resolve."
                if matched and negative
                else "DNS resolved expected address."
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
    def _dns_window_complete(window: str, expected: str, negative: bool) -> bool:
        """Whether the window already carries a terminal line to read."""
        if _NOT_FOUND.search(window):
            return True
        if negative:
            return "packets: sent" in window.casefold()
        return expected in window and "packets: sent" in window.casefold()

    def _verify_http(self, expectation):
        """Fetch with an owned client and read only content it retrieved."""
        marker = str(expectation.expected.get("marker") or "")
        target = str(
            expectation.expected.get("hostname")
            or expectation.expected.get("address")
            or ""
        )
        scheme = str(expectation.expected.get("scheme") or "http").casefold()
        claim = "independent_client_observation"
        if scheme not in {"http", "https"}:
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
                "content_before:before,https_mode:https_mode}));"
            )
        else:
            start_js = (
                f"var d=ipc.network().getDevice({client});"
                + self._background_http_start(expectation.id, url)
                + "var before=content_before;"
                "reportResult(JSON.stringify({started:started,content_before:before}));"
            )
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
        before = str(payload.get("content_before") or "")
        if secure:
            mode = payload.get("https_mode")
            if not isinstance(mode, bool):
                # Absent is neither false nor true: the payload did not report
                # the mode, so nothing about the listener was observed.
                release = self._release_background_http(expectation.id, client)
                return self._observed(
                    expectation,
                    observation=ObservationFact.MALFORMED,
                    method=method,
                    claim_level=claim,
                    cause="https_mode_absent",
                    observed={"released": release},
                    message="The start payload did not report the client HTTPS mode.",
                )
            if not mode:
                release = self._release_background_http(expectation.id, client)
                return self._observed(
                    expectation,
                    observation=ObservationFact.CONTRADICTED,
                    method=method,
                    claim_level=claim,
                    cause="https_mode_not_confirmed",
                    observed={"released": release},
                    message="The client did not confirm HTTPS mode after setHttps.",
                )
        if not payload.get("started"):
            release = self._release_background_http(expectation.id, client)
            return self._observed(
                expectation,
                observation=ObservationFact.INCONCLUSIVE,
                method=method,
                claim_level=claim,
                cause="client_go_false",
                observed={"released": release},
                message="The client did not start the request.",
            )
        if marker and marker in before:
            release = self._release_background_http(expectation.id, client)
            return self._observed(
                expectation,
                observation=ObservationFact.INCONCLUSIVE,
                method=method,
                claim_level=claim,
                cause="marker_present_before_request",
                observed={"released": release},
                message=(
                    "The expected marker already existed before this request, so "
                    "no content can be attributed to it."
                ),
            )

        def inspect():
            return self._observe(self._background_http_inspect(expectation.id), 3.0)

        observed = self._poll(
            inspect,
            lambda item: (
                item.kind is BridgeObservationKind.PAYLOAD
                and bool(
                    (content := str((item.payload or {}).get("content") or ""))
                    and content != before
                    and (not marker or marker in content)
                )
            ),
            self._http_timeout,
        )
        if observed.kind is not BridgeObservationKind.PAYLOAD:
            release = self._release_background_http(expectation.id, client)
            return self._observed(
                expectation,
                observation=self._transport_fact(observed),
                method=method,
                claim_level=claim,
                cause=observed.outcome.detail,
                observed={"released": release},
                message="The client page content could not be read.",
            )
        content = str((observed.payload or {}).get("content") or "")
        release = self._release_background_http(expectation.id, client)
        if not content or content == before:
            return self._observed(
                expectation,
                observation=ObservationFact.INCONCLUSIVE,
                method=method,
                claim_level=claim,
                cause="no_response_within_deadline",
                observed={"released": release},
                message="No content change was observed before the deadline.",
            )
        if marker and marker not in content:
            return self._observed(
                expectation,
                observation=ObservationFact.CONTRADICTED,
                method=method,
                claim_level=claim,
                observed={"released": release},
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
                "released": release,
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
        """Create one owned client, record its page, and start the request."""
        key = json.dumps(expectation_id)
        return (
            'var m=d&&d.getProcess("HttpBackgroundClientManager");'
            "this.__mcpE6HttpClients=this.__mcpE6HttpClients||{};"
            f"var old=this.__mcpE6HttpClients[{key}];"
            "if(old&&old.manager&&old.client){old.manager.deleteClient(old.client);}"
            "var p=m&&m.createClient();var content_before=p?String(p.getLastPageContent()):'';"
            f"var started=!!(p&&p.go({url_json}));"
            f"if(started){{this.__mcpE6HttpClients[{key}]={{manager:m,client:p}};}}"
            "else if(m&&p){m.deleteClient(p);}"
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
            "var p=m&&m.createClient();var content_before=p?String(p.getLastPageContent()):'';"
            "if(p){p.setHttps(true);}var https_mode=p?!!p.isHttps():null;"
            f"var started=!!(p&&p.go({url_json}));"
            f"if(started){{this.__mcpE6HttpClients[{key}]={{manager:m,client:p}};}}"
            "else if(m&&p){m.deleteClient(p);}"
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

    def _release_background_http(self, expectation_id: str, client_json: str) -> str:
        """Release the owned client and report what the release established.

        Three outcomes, kept apart: `released` means the release ran and
        confirmed the slot is gone, `release_unverified` means it ran and did
        not confirm, `release_failed` means the release call itself did not
        come back. Reporting the last two as success is how an owned client
        would be leaked silently.
        """
        key = json.dumps(expectation_id)
        observation = self._observe(
            f"var d=ipc.network().getDevice({client_json});"
            "var bag=this.__mcpE6HttpClients||{};"
            f"var slot=bag[{key}];if(slot&&slot.manager&&slot.client){{"
            "slot.manager.deleteClient(slot.client);"
            f"delete bag[{key}];}}"
            "reportResult(JSON.stringify({released:!slot||!bag[" + key + "]}));",
            3.0,
        )
        if observation.kind is not BridgeObservationKind.PAYLOAD:
            return "release_failed"
        if (observation.payload or {}).get("released") is True:
            return "released"
        return "release_unverified"

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
