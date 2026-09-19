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
import threading
from collections.abc import Callable, Sequence
from contextlib import nullcontext
from dataclasses import dataclass
from enum import Enum, StrEnum
from ipaddress import ip_address, ip_network
from time import monotonic, sleep

from ...application.ports.secret_resolver import SecretResolver, SecretUnavailable
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
    SECRET_BEARING_ACTIONS,
    AcquireDhcpLease,
    AddDnsRecord,
    ConfigureEmailClient,
    ConfigureNtpService,
    ConfigureServerDhcpPool,
    EnableDnsService,
    EnableHttpService,
    EnableHttpsService,
    EnablePop3Service,
    EnableServerDhcp,
    EnableSmtpService,
    EnableTftpService,
    EnsureEmailAccount,
    PublishTftpFile,
    SendMailMessage,
    ServiceAction,
    ServiceEvidenceKind,
    ServiceType,
    ServiceVerificationExpectation,
    ServiceVerificationKind,
    SetHttpContent,
    mail_message_text,
)
from ...domain.enterprise.models.service_runtime import (
    ObservationFact,
    RuntimeServiceVerification,
)
from .command_dispatch import PAGER_GUARD_JS
from .runtime_inventory import normalize_runtime_inventory
from .secret_resolver import EvidenceSanitizer
from .transport_outcome import BridgeDispatchOutcome

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
    ServiceType.SMTP: "SmtpServer",
    ServiceType.POP3: "Pop3Server",
    ServiceType.DHCP: "DhcpServer",
}

#: The mail families. Their batches and their reads run one at a time per
#: process behind `_MAIL_LOCK` (R-OBS-04): the applicator already dispatches
#: one batch at a time within an invocation, and this closes the gap between
#: two invocations in one MCP process. Across processes only the engine claim
#: remains.
_MAIL_ACTIONS = (
    EnableSmtpService,
    EnablePop3Service,
    EnsureEmailAccount,
    ConfigureEmailClient,
    SendMailMessage,
    EnableServerDhcp,
    ConfigureServerDhcpPool,
    AcquireDhcpLease,
)
_MAIL_LOCK = threading.RLock()

#: The production claim global and the per-client subject key (R-EVT-06/07).
_CLAIMS = "this.__mcpE6Claims"
_CLAIM_PREFIX = "email_client:"
_DHCP_CLAIM_PREFIX = "dhcp_client:"

#: One read cannot enumerate more rows than this even when a pool declares more.
DHCP_LEASE_SCAN_LIMIT = 256
_MAC_TEXT = re.compile(
    r"^(?:[0-9A-Fa-f]{4}\.){2}[0-9A-Fa-f]{4}$|"
    r"^(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}$"
)

#: The bound on one mailbox scan, newest first. A mailbox holding more mail
#: than this can prove presence but never absence.
MAILBOX_SCAN_LIMIT = 100

#: Why a mail row reports that no setter ran, beyond the two shared reasons.
#:
#: The last two exist because two different readings used to collapse into
#: "nothing is there". `getEmailUser(name)` returning an object whose
#: `getUser()` is a different name is an inconsistent identity, not an absent
#: account; an own claim key holding something that is not a readable claim is
#: unknown ownership, not a free slot. Neither admits an effect.
_SKIP_PRECONDITION_UNOBSERVED = "precondition_unobserved"
_SKIP_SUBJECT_CLAIMED = "subject_claimed"
_SKIP_OWN_CLAIM_REPLAYED = "own_claim_replayed"
_SKIP_ACCOUNT_IDENTITY_MISMATCH = "account_identity_mismatch"
_SKIP_SUBJECT_CLAIM_UNREADABLE = "subject_claim_unreadable"
_SKIP_POOL_CONFLICT = "pool_conflict"
_SKIP_DHCP_MODE_NOT_ENABLED = "dhcp_mode_not_enabled"
_REFUSALS = frozenset(
    {
        _SKIP_PRECONDITION_UNOBSERVED,
        _SKIP_SUBJECT_CLAIMED,
        _SKIP_ACCOUNT_IDENTITY_MISMATCH,
        _SKIP_SUBJECT_CLAIM_UNREADABLE,
        _SKIP_POOL_CONFLICT,
        _SKIP_DHCP_MODE_NOT_ENABLED,
    }
)

#: The event-dependent kinds R-EVT-05's fallback leaves without an observer.
_GATED_EVENT_KINDS = frozenset(
    {
        ServiceVerificationKind.SMTP_SEND,
        ServiceVerificationKind.POP3_RETRIEVE,
        ServiceVerificationKind.EMAIL_END_TO_END,
    }
)
_GATED_EVENT_CAUSE = "event_observation_gated:r_evt_05_fallback"

#: What a mailbox-presence row never establishes, stated on every such row.
_MAIL_DELIVERY_LIMITATIONS = (
    "not_a_mailsent_success_event",
    "not_pop3_retrieval_evidence",
    "dispatch_outcome_reported_separately",
)

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
#:
#: `__er` returns a bounded copy of whatever the engine said. `__ec` returns
#: one of eight constants instead, and a batch that resolved a credential uses
#: it for every row: a 200-character crop of an external message can leave a
#: confidential prefix behind, and no redactor downstream can put the rest of
#: the value back to recognize it. A category is worth less than a message and
#: is the only thing such a script may safely return (R-SEC-01).
_ERROR_NAMES = (
    "Error",
    "EvalError",
    "RangeError",
    "ReferenceError",
    "SyntaxError",
    "TypeError",
    "URIError",
)
_ERROR_TEXT_HELPER = (
    "function __er(e){var s='';try{s=String(e&&e.message?e.message:e);}"
    "catch(x){s='error';}return s.length>200?s.substring(0,200):s;}"
)
_ERROR_CATEGORY_HELPER = (
    "function __ec(e){var n='';try{n=String(e&&e.name?e.name:'');}catch(x){n='';}"
    f"var k={json.dumps(list(_ERROR_NAMES), separators=(',', ':'))};"
    "for(var i=0;i<k.length;i++){if(n===k[i]){return 'engine_error:'+k[i];}}"
    "return 'engine_error:other';}"
)
_SCRIPT_HELPERS = (
    "function __dg(v){if(typeof v==='boolean'){return v?'1':'0';}"
    "var s=String(v);var h=0x811c9dc5;for(var i=0;i<s.length;i++){"
    "h^=s.charCodeAt(i);h=(h+((h<<1)+(h<<4)+(h<<7)+(h<<8)+(h<<24)))>>>0;}"
    "return ('0000000'+h.toString(16)).slice(-8)+':'+s.length;}"
    + _ERROR_TEXT_HELPER
    + _ERROR_CATEGORY_HELPER
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

#: Every family whose attempted setter writes more than its read observes,
#: with the unobserved scope it names. A mail credential is written and never
#: read back, so existence and field equality never prove it.
_PARTIAL_FOOTPRINTS: dict[type, str] = {
    AddDnsRecord: _DNS_PARTIAL_FOOTPRINT,
    EnsureEmailAccount: "footprint_partial:email_account_credential",
    ConfigureEmailClient: "footprint_partial:email_client_password",
    ConfigureServerDhcpPool: "footprint_partial:dhcp_pool_lease_state",
}

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


class DnsWindowKind(StrEnum):
    """What one terminal `ping` window is, before any expectation is applied.

    The window is read ONCE and the reading is shared by both claim
    directions. The negative control used to return before the address was
    ever parsed, so an unreadable window was inconclusive for a positive
    expectation and fresh negative evidence for a negative one, and a window
    carrying both a not-found line and a successful resolution was whichever
    signal happened to be tested first (V2).
    """

    __str__ = Enum.__str__

    NOT_FOUND = "not_found"
    RESOLVED = "resolved"
    AMBIGUOUS = "ambiguous"


@dataclass(frozen=True)
class DnsWindowReading:
    """One terminal window classified, with what it reported."""

    kind: DnsWindowKind
    address: str = ""
    reason: str = ""


def _dns_window_reading(window: str) -> DnsWindowReading:
    """Classify one terminal window as an observation, or as neither.

    AMBIGUOUS covers every window no supported shape reads as one thing:
    mutually conflicting signals, a resolution with no readable address, an
    unparsable address, and two addresses that disagree. None of them may
    produce a verdict in either direction, and an unsupported output dialect
    stays unqualified rather than being guessed at.
    """
    not_found = bool(_NOT_FOUND.search(window))
    statistics = "packets: sent" in window.casefold()
    address, reason = _dns_resolution(window)
    resolution_line = bool(address) or reason != "address_not_reported"
    if not_found and (statistics or resolution_line):
        return DnsWindowReading(
            DnsWindowKind.AMBIGUOUS,
            reason="mixed_not_found_and_resolution",
        )
    if not_found:
        return DnsWindowReading(DnsWindowKind.NOT_FOUND)
    if statistics and address:
        return DnsWindowReading(DnsWindowKind.RESOLVED, address=address)
    return DnsWindowReading(
        DnsWindowKind.AMBIGUOUS,
        reason=reason or "no_terminal_line",
    )


def mailbox_scan_incoherence(payload: dict) -> str:
    """Name the first relation one mailbox scan breaks, or "" when coherent.

    `payload` must already carry every counter of the scan's typed shape;
    the caller establishes that first, and this rule raises `KeyError` rather
    than reading a missing key as a zero, which is the mistake it exists to
    prevent.

    The relations are the bounded scanner's own, read off the script
    `_verify_smtp_delivered` generates: it reads `count` once, walks the
    mailbox newest first while `scanned < MAILBOX_SCAN_LIMIT`, increments
    exactly one of `matches`/`mismatched` per subject hit, sets `truncated`
    from what it did not reach, and touches nothing at all when the recipient
    account is absent. Nothing here is an assumption about how a `Mail` field
    is spelled or typed; that stays unqualified until Q2 measures it.

    A payload that breaks one of them is not a mailbox that held nothing. It
    is an answer this reader cannot use, so it establishes neither presence
    nor absence and the caller reports MALFORMED.
    """
    counters = ("count", "scanned", "matches", "mismatched")
    if any(payload[name] < 0 for name in counters):
        return "negative_counter"
    if not payload["found_user"]:
        # The script never enters the scan, so every counter is its default.
        if any(payload[name] for name in counters) or payload["truncated"]:
            return "absent_subject_carries_counters"
        return ""
    if payload["scanned"] > MAILBOX_SCAN_LIMIT:
        return "scan_exceeds_bound"
    if payload["scanned"] != min(payload["count"], MAILBOX_SCAN_LIMIT):
        return "scan_not_the_bounded_walk"
    if payload["matches"] + payload["mismatched"] > payload["scanned"]:
        return "match_total_exceeds_scanned"
    if payload["truncated"] is not (payload["count"] > payload["scanned"]):
        return "truncation_contradicts_counts"
    return ""


def _no_client_contradiction(payload: dict, *, secure: bool) -> str:
    """Name the field that refutes a start payload's claim of no client.

    Derived from what the builder can emit, not from taste. `owned` is
    `!!(m&&p)`, and `p` is `m&&m.createClient()`, so no client means `p` is
    falsy, which forces `content_before` to `''`, `started` to `false` and
    `https_mode` to `null`. A payload that denies the client while reporting
    any of those is not a coherent observation of absence, and absence is the
    one answer that lets the reader skip its cleanup entirely (V1).

    Returns the empty string when the no-client tuple is coherent.
    """
    if payload["started"]:
        return "started_without_client"
    if payload["content_before"]:
        return "content_without_client"
    if secure and isinstance(payload.get("https_mode"), bool):
        return "https_mode_without_client"
    return ""


def _release_contradiction(payload: dict) -> str:
    """Name what refutes a release payload, field types being satisfied.

    `deleted` is only ever set inside `if(found)`, after `deleteClient`
    returned and before the `catch` that fills `error`, and the slot is
    dropped in the same evaluation. So a deletion cannot coexist with a
    missing slot, a surviving slot, or an error, and a slot that was found and
    not deleted cannot have vanished. Each of those combinations came back
    with correct field TYPES and still described nothing that could have
    happened; `deleted && !present` alone was read as success (V1).

    Returns the empty string when the tuple is one the script can produce.
    """
    if payload["deleted"]:
        if not payload["found"]:
            return "deleted_without_slot"
        if payload["present"]:
            return "deleted_but_present"
        if payload["error"]:
            return "deleted_with_error"
    elif payload["found"] and not payload["present"]:
        return "not_deleted_but_absent"
    return ""


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
        mail_timeout_seconds: float = 8.0,
        convergence_interval_seconds: float = 0.25,
        clock: Callable[[], float] = monotonic,
        sleeper: Callable[[float], None] = sleep,
        secret_resolver: SecretResolver | None = None,
    ) -> None:
        """Bind the runtime to one inventory reader and one command channel.

        `dispatch_and_wait` is the channel that reports typed transport facts.
        When only the legacy `send_and_wait` is available its `None` is
        wrapped as ACCEPTANCE_UNKNOWN plus NOT_OBSERVED -- never
        NOT_SUBMITTED, because a callable that returns `None` cannot prove the
        payload stayed inside this process.

        `secret_resolver` is the one source of credential values. Without it a
        secret-bearing action is refused before any script exists. One runtime
        serves one invocation, so its `EvidenceSanitizer` holds exactly the
        values this invocation resolved and nothing else.
        """
        self._sanitizer = EvidenceSanitizer()
        self._query_inventory = query_inventory
        self._send_and_wait = send_and_wait
        self._dispatch_and_wait = dispatch_and_wait
        self._dns_timeout = dns_timeout_seconds
        self._http_timeout = http_timeout_seconds
        self._mail_timeout = mail_timeout_seconds
        self._secret_resolver = secret_resolver
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
        serialized = any(isinstance(item, _MAIL_ACTIONS) for item in actions)
        with _MAIL_LOCK if serialized else nullcontext():
            return self._apply_batch(actions, next(iter(host_names)))

    def _apply_batch(
        self,
        actions: Sequence[ServiceAction],
        host_name: str,
    ) -> list[RuntimeActionMutation]:
        """Build, dispatch and read one batch; refuse what cannot be built.

        A secret-bearing action whose reference does not resolve, and a send
        with no bound nonce, are refused before any script exists, so their
        rows are NOT_SUBMITTED: the payload provably never left this process.

        Redaction is the invocation's, not this batch's: every string of every
        returned row passes the runtime's `EvidenceSanitizer`, which holds
        every value resolved so far, so a value this batch never used cannot
        leave through a row of it either.
        """
        secrets: dict[str, str] = {}
        refused: dict[str, RuntimeActionMutation] = {}
        for action in actions:
            if isinstance(action, SendMailMessage) and not action.nonce:
                refused[action.id] = self._not_submitted(
                    action, "message_nonce_unbound"
                )
                continue
            if not isinstance(action, SECRET_BEARING_ACTIONS):
                continue
            try:
                secrets[action.secret_ref] = self._secret(action.secret_ref)
            except SecretUnavailable as error:
                refused[action.id] = self._not_submitted(
                    action, f"secret_unresolved:{error.reason}"
                )
        ready = [item for item in actions if item.id not in refused]
        rows: dict[str, RuntimeActionMutation] = dict(refused)
        if ready:
            host = json.dumps(host_name)
            lines = [
                f"var d=ipc.network().getDevice({host});var results=[];",
                _SCRIPT_HELPERS,
                "if(!d){reportResult(JSON.stringify({results:[]}));}else{",
            ]
            for action in ready:
                lines.extend(
                    self._mutation_lines(
                        action,
                        secrets,
                        category_errors=self._sanitizer.holds_values,
                    )
                )
            lines.append("reportResult(JSON.stringify({results:results}));}")
            observation = self._observe("".join(lines), 10.0)
            rows.update(
                {
                    item.action_id: item
                    for item in self._batch_mutations(ready, observation)
                }
            )
        ordered = [rows[item.id] for item in actions]
        if not self._sanitizer.holds_values:
            return ordered
        return [
            row.model_copy(
                update={
                    field: self._sanitizer.redact(getattr(row, field))
                    for field in ("message", "cause", "call_error")
                }
            )
            for row in ordered
        ]

    def _secret(self, secret_ref: str) -> str:
        """Resolve one reference through the bound resolver, or refuse.

        Every value this invocation reveals is remembered by the sanitizer at
        the moment it is revealed, so no later diagnostic of this runtime --
        of this batch, of the next one, or of a verification read -- can
        return it.
        """
        if self._secret_resolver is None:
            raise SecretUnavailable(secret_ref, "no_resolver")
        value = self._secret_resolver.resolve(secret_ref).reveal()
        self._sanitizer.remember(value)
        return value

    def _safe(self, value: object) -> str:
        """Return one bounded diagnostic that crossed the secret boundary."""
        return self._sanitizer.safe(value)

    @staticmethod
    def _not_submitted(action: ServiceAction, cause: str) -> RuntimeActionMutation:
        """Report an action refused before its script existed (row 1)."""
        return RuntimeActionMutation(
            action_id=action.id,
            applied=False,
            operation=action.operation,
            dispatch=DispatchFact.NOT_SUBMITTED,
            result=ResultFact.NOT_APPLICABLE,
            postcondition=PostconditionFact.NOT_APPLICABLE,
            transition=TransitionFact.NOT_APPLICABLE,
            footprint=FootprintFact.NOT_APPLICABLE,
            attempted=None,
            cause=cause,
            message="The action was refused before any script was dispatched.",
        )

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

    def _whole_batch_mutation(
        self,
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
            cause=self._safe(outcome.detail),
            message=self._sanitizer.redact(observation.message),
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
        check = self._row_invalid_check(row, self._allowed_skips(action))
        if check:
            return self._invalid_row_mutation(
                action,
                batch_id,
                f"row_invalid:{check}",
                note,
            )

        attempted = bool(row["attempted"])
        call_error = self._safe(row["call_error"])
        skip = row["skip_reason"]
        if skip in _REFUSALS:
            # Row 21: the engine refused before any setter. Nothing was
            # called, so nothing was changed and nothing is in doubt.
            return RuntimeActionMutation(
                action_id=action.id,
                applied=True,
                operation=action.operation,
                batch_id=batch_id,
                dispatch=DispatchFact.ACCEPTED,
                result=ResultFact.CORRELATED,
                postcondition=PostconditionFact.UNOBSERVED,
                transition=TransitionFact.NOT_APPLICABLE,
                footprint=FootprintFact.COVERED,
                attempted=False,
                cause=skip,
                message=f"The engine refused before any setter: {skip}." + note,
            )
        if isinstance(action, SendMailMessage | AcquireDhcpLease):
            # Row 22: the execute-once call returns before its outcome exists,
            # and no qualified observer is admitted. A
            # replay that met this operation's own claim cannot say whether
            # the earlier evaluation sent, so it states nothing (`None`).
            replayed = skip == _SKIP_OWN_CLAIM_REPLAYED
            is_dhcp = isinstance(action, AcquireDhcpLease)
            return RuntimeActionMutation(
                action_id=action.id,
                applied=True,
                operation=action.operation,
                batch_id=batch_id,
                dispatch=DispatchFact.ACCEPTED,
                result=ResultFact.CORRELATED,
                postcondition=PostconditionFact.UNOBSERVED,
                transition=TransitionFact.NOT_APPLICABLE,
                footprint=FootprintFact.PARTIAL,
                attempted=None if replayed else True,
                cause=(
                    _SKIP_OWN_CLAIM_REPLAYED if replayed else "no_qualified_observation"
                ),
                call_error=call_error,
                message=(
                    "An earlier evaluation of this operation holds its claim."
                    if replayed
                    else (
                        "DHCP acquisition was started once under its claim."
                        if is_dhcp
                        else "The message was dispatched once under its claim."
                    )
                )
                + note,
            )
        if skip == _SKIP_FAMILY_NOT_IMPLEMENTED:
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
                cause = _PARTIAL_FOOTPRINTS[type(action)]
            elif isinstance(action, EnsureEmailAccount) and not attempted:
                # R-SEC-05: an existing account was left untouched, and its
                # existence says nothing about the credential it holds.
                cause = "account_preexisting:credential_unverified"
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
        if isinstance(action, tuple(_PARTIAL_FOOTPRINTS)):
            return FootprintFact.PARTIAL
        return FootprintFact.COVERED

    @staticmethod
    def _allowed_skips(action: ServiceAction) -> frozenset[str]:
        """Return the only skip reasons this family's script can report.

        A reason a family never generates is not an answer from that family:
        a DNS row that says `subject_claimed` is an invalid row, not a refusal.
        """
        if isinstance(action, EnsureEmailAccount):
            return frozenset(
                {
                    _SKIP_ALREADY_SATISFIED,
                    _SKIP_PRECONDITION_UNOBSERVED,
                    _SKIP_ACCOUNT_IDENTITY_MISMATCH,
                }
            )
        if isinstance(action, ConfigureEmailClient):
            return frozenset({_SKIP_SUBJECT_CLAIMED})
        if isinstance(action, SendMailMessage):
            return frozenset(
                {
                    _SKIP_SUBJECT_CLAIMED,
                    _SKIP_OWN_CLAIM_REPLAYED,
                    _SKIP_PRECONDITION_UNOBSERVED,
                    _SKIP_SUBJECT_CLAIM_UNREADABLE,
                }
            )
        if isinstance(action, AcquireDhcpLease):
            return frozenset(
                {
                    _SKIP_SUBJECT_CLAIMED,
                    _SKIP_OWN_CLAIM_REPLAYED,
                    _SKIP_PRECONDITION_UNOBSERVED,
                    _SKIP_SUBJECT_CLAIM_UNREADABLE,
                    _SKIP_DHCP_MODE_NOT_ENABLED,
                }
            )
        if isinstance(action, EnableServerDhcp):
            return frozenset({_SKIP_PRECONDITION_UNOBSERVED})
        if isinstance(action, ConfigureServerDhcpPool):
            return frozenset(
                {
                    _SKIP_ALREADY_SATISFIED,
                    _SKIP_PRECONDITION_UNOBSERVED,
                    _SKIP_POOL_CONFLICT,
                }
            )
        return frozenset({_SKIP_ALREADY_SATISFIED, _SKIP_FAMILY_NOT_IMPLEMENTED})

    @staticmethod
    def _row_invalid_check(
        row: dict,
        allowed_skips: frozenset[str] = frozenset(
            {_SKIP_ALREADY_SATISFIED, _SKIP_FAMILY_NOT_IMPLEMENTED}
        ),
    ) -> str:
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
        if row["skip_reason"] not in allowed_skips:
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
        elif row["skip_reason"] in {
            _SKIP_ACCOUNT_IDENTITY_MISMATCH,
            _SKIP_POOL_CONFLICT,
            _SKIP_DHCP_MODE_NOT_ENABLED,
        }:
            # Unlike the other refusals, this one IS a completed pre-read: it
            # reports what the lookup returned. A row that claims it without
            # having read anything has invented the contradiction.
            if not row["pre_read"]:
                return "refusal_requires_pre_read"
        elif row["pre_read"] or row["post_read"]:
            return "declined_requires_no_reads"
        return ""

    @staticmethod
    def _mutation_lines(
        action: ServiceAction,
        secrets: dict[str, str] | None = None,
        *,
        category_errors: bool = False,
    ) -> list[str]:
        """Generate one action's pre-read, setter and unconditional post-read.

        Each of the three steps has its own try/catch, so a setter that throws
        does not hide a post-read that would have shown its effect, and a
        failed pre-read does not stop the post-read from running. `secrets`
        holds this batch's resolved values by reference; a value reaches the
        script only through `json.dumps`.

        A batch that resolved anything reads its caught errors with `__ec`,
        which returns a category, instead of `__er`, which returns a bounded
        copy of the engine's own text. The choice is the batch's, not the
        action's: the credential is in the evaluation, so no row of it may
        carry external text that a later redactor might no longer recognize.
        """
        action_id = json.dumps(action.id)
        row = (
            "var r={id:"
            + action_id
            + ',attempted:false,skip_reason:"",call_error:"",call_result:null,'
            "pre_read:false,post_read:false,ok:null,changed:null,pre:null,post:null};"
        )
        reader = "__ec" if category_errors else "__er"
        runtime = PacketTracerEnterpriseServiceRuntime
        if isinstance(action, EnsureEmailAccount):
            return runtime._account_lines(row, action, secrets or {}, reader)
        if isinstance(action, ConfigureEmailClient):
            return runtime._client_lines(row, action, secrets or {}, reader)
        if isinstance(action, SendMailMessage):
            return runtime._send_lines(row, action, secrets or {}, reader)
        if isinstance(action, EnableServerDhcp):
            return runtime._enable_server_dhcp_lines(row, action, reader)
        if isinstance(action, ConfigureServerDhcpPool):
            return runtime._server_dhcp_pool_lines(row, action, reader)
        if isinstance(action, AcquireDhcpLease):
            return runtime._acquire_dhcp_lines(row, action, reader)
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
                + f";}}catch(e){{r.call_error={reader}(e);}}}}"
            )
        else:
            lines.append(
                "try{r.attempted=true;"
                + setter
                + f";}}catch(e){{r.call_error={reader}(e);}}"
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
        if isinstance(action, EnableDnsService | EnableHttpService | EnablePop3Service):
            return "!!p.isEnabled()", "p.setEnable(true)", "qv===true"
        if isinstance(action, EnableSmtpService):
            # One typed read covers both setters, so the footprint is covered:
            # the flag and the domain are compared together as one value.
            domain = json.dumps(action.domain_name)
            wanted = json.dumps(
                json.dumps([True, action.domain_name], separators=(",", ":"))
            )
            return (
                "JSON.stringify([!!p.isEnabled(),String(p.getServerDomainName())])",
                f"p.setServerDomainName({domain});p.setEnable(true)",
                f"qv==={wanted}",
            )
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

    @staticmethod
    def _account_lines(
        row: str, action: EnsureEmailAccount, secrets: dict[str, str], reader: str
    ) -> list[str]:
        """Ensure one server account exists without ever changing one.

        `__ex` classifies the lookup into three readings instead of one
        boolean: `absent` when `getEmailUser(name)` returned nothing,
        `present` when it returned a user whose `getUser()` is that name, and
        `mismatch` when it returned a user whose `getUser()` is a different
        name. A getter that throws is a fourth outcome -- no reading at all --
        because the pre-read never completes.

        Only `absent` authorizes `addUser`. `present` is the documented no-op,
        and its password is never read, compared or changed (R-SEC-05).
        `mismatch` and an unobserved pre-read both refuse: an inconsistent
        identity is the engine contradicting itself about this name, and
        neither it nor a failed getter is evidence that the account is free to
        create. Folding `mismatch` into `absent` is what let an add run
        against a name the server had already answered for.
        """
        name = json.dumps(action.username)
        password = json.dumps(secrets[action.secret_ref])
        return [
            row,
            'var p=d.getProcess("EmailServer");var pv=null,qv=null;',
            f"var __ex=function(){{var u=p.getEmailUser({name});"
            "if(u===null||u===undefined){return 'absent';}"
            f"return String(u.getUser())==={name}?'present':'mismatch';}};",
            "try{pv=__ex();r.pre_read=true;r.pre=__dg(pv);}catch(e){}",
            'if(!r.pre_read){r.skip_reason="' + _SKIP_PRECONDITION_UNOBSERVED + '";}'
            "else if(pv==='present'){r.skip_reason=\"" + _SKIP_ALREADY_SATISFIED + '";}'
            "else if(pv!=='absent'){r.skip_reason=\""
            + _SKIP_ACCOUNT_IDENTITY_MISMATCH
            + '";}'
            f"else{{try{{r.attempted=true;r.call_result=!!p.addUser({name},{password});}}"
            f"catch(e){{r.call_error={reader}(e);}}}}",
            'if(r.skip_reason!=="' + _SKIP_PRECONDITION_UNOBSERVED + '"){'
            "try{qv=__ex();r.post_read=true;r.post=__dg(qv);}catch(e){}}",
            "if(r.post_read){r.ok=(qv==='present');}",
            "if(r.pre_read&&r.post_read){r.changed=(pv!==qv);}",
            "results.push(r);",
        ]

    @staticmethod
    def _client_lines(
        row: str, action: ConfigureEmailClient, secrets: dict[str, str], reader: str
    ) -> list[str]:
        """Configure one client's mail user and read every field but the password.

        Refused with no call while any claim is held on this client, so an
        `EmailClient` is never reconfigured while an operation on it is
        unresolved (R-OBS-04). The password is written and never read back,
        which is why the footprint is partial.
        """
        key = json.dumps(_CLAIM_PREFIX + action.host_device_name)
        fields = [
            action.display_name,
            action.username,
            action.mail_id,
            action.smtp_server,
            action.pop3_server,
        ]
        wanted = json.dumps(json.dumps(fields, separators=(",", ":")))
        name, user, mail_id, smtp, pop3 = (json.dumps(item) for item in fields)
        password = json.dumps(secrets[action.secret_ref])
        return [
            row,
            f"var __c={_CLAIMS}||{{}};",
            f"if(Object.prototype.hasOwnProperty.call(__c,{key})){{"
            'r.skip_reason="' + _SKIP_SUBJECT_CLAIMED + '";}else{',
            'var p=d.getProcess("EmailClient");var pv=null,qv=null;',
            "var __rd=function(){var u=p.getEmailUser();return JSON.stringify(["
            "String(u.getName()),String(u.getUser()),String(u.getMailId()),"
            "String(u.getSmtpServer()),String(u.getPop3Server())]);};",
            "try{pv=__rd();r.pre_read=true;r.pre=__dg(pv);}catch(e){}",
            "try{r.attempted=true;var u=p.getEmailUser();"
            f"u.setName({name});u.setUser({user});u.setMailId({mail_id});"
            f"u.setSmtpServer({smtp});u.setPop3Server({pop3});u.setPassword({password});"
            f"}}catch(e){{r.call_error={reader}(e);}}",
            "try{qv=__rd();r.post_read=true;r.post=__dg(qv);}catch(e){}",
            f"if(r.post_read){{r.ok=(qv==={wanted});}}",
            "if(r.pre_read&&r.post_read){r.changed=(pv!==qv);}",
            "}",
            "results.push(r);",
        ]

    @staticmethod
    def _send_lines(
        row: str, action: SendMailMessage, secrets: dict[str, str], reader: str
    ) -> list[str]:
        """Dispatch one message at most once, under a pre-effect claim.

        The prerequisite is the ABSENCE of an own key on the claim object,
        which is what `hasOwnProperty` answers. Reading the stored value for
        truth instead made every falsey entry -- `null`, `false`, `0`, `""` --
        look like a free slot, so a present, unreadable claim was overwritten
        and a message went out under it.

        A present key is therefore classified, never emptied. A readable claim
        (`op_id` and `nonce` both strings) refuses as `own_claim_replayed`
        when it is this operation's claim for this run's nonce and as
        `subject_claimed` otherwise; anything else under the key is unknown
        ownership and refuses as `subject_claim_unreadable`. None of the three
        writes, adopts, resets or sends.

        With no own key the claim is written `in_progress` BEFORE `sendMail`,
        and becomes `completed` when the call returns or `unknown` when it
        throws. No claim is ever cleared here: under the event fallback no
        send is ever observed to have resolved, so the claim stays as the
        quarantine of the subject for the Packet Tracer session
        (R-EVT-06/07). This bounds duplicates only within one evaluation; it
        is not exactly-once, and the Python lock proves nothing about the
        engine.
        """
        key = json.dumps(_CLAIM_PREFIX + action.host_device_name)
        operation = json.dumps(action.id)
        reference = json.dumps(action.message_ref)
        nonce = json.dumps(action.nonce)
        text = json.dumps(mail_message_text(action.nonce))
        sender = json.dumps(action.sender_mail_id)
        recipient = json.dumps(action.recipient_mail_id)
        server = json.dumps(action.smtp_server)
        password = json.dumps(secrets[action.secret_ref])
        return [
            row,
            f"var __c={_CLAIMS}={_CLAIMS}||{{}};"
            f"var __present=Object.prototype.hasOwnProperty.call(__c,{key});"
            f"var __held=__present?__c[{key}]:null;"
            "var __readable=!!__held&&typeof __held==='object'"
            "&&typeof __held.op_id==='string'&&typeof __held.nonce==='string';",
            'if(__present&&!__readable){r.skip_reason="'
            + _SKIP_SUBJECT_CLAIM_UNREADABLE
            + '";}',
            f"else if(__present){{r.skip_reason=(__held.op_id==={operation}"
            f"&&__held.nonce==={nonce})?"
            '"' + _SKIP_OWN_CLAIM_REPLAYED + '":"' + _SKIP_SUBJECT_CLAIMED + '";}else{',
            'var __s=null;try{var __p=d.getProcess("EmailClient");'
            "__s=__p?__p.getSmtpClient():null;}catch(e){__s=null;}",
            'if(!__s){r.skip_reason="' + _SKIP_PRECONDITION_UNOBSERVED + '";}else{',
            "this.__mcpE6Seq=(this.__mcpE6Seq||0)+1;",
            f'__c[{key}]={{state:"in_progress",op_id:{operation},'
            f"message_ref:{reference},nonce:{nonce},seq:this.__mcpE6Seq}};",
            "try{r.attempted=true;"
            f"r.call_result=!!__s.sendMail({sender},{recipient},{text},{text},"
            f"{password},{server});"
            f'__c[{key}].state="completed";}}catch(e){{__c[{key}].state="unknown";'
            f"r.call_error={reader}(e);}}",
            "}}",
            "results.push(r);",
        ]

    @staticmethod
    def _enable_server_dhcp_lines(
        row: str,
        action: EnableServerDhcp,
        reader: str,
    ) -> list[str]:
        """Bracket the exact interface's documented DHCP enable flag."""
        interface = json.dumps(action.interface)
        return [
            row,
            'var m=d.getProcess("DhcpServer");var p=null;var pv=null,qv=null;',
            f"try{{p=m&&m.getDhcpServerProcessByPortName({interface});}}catch(e){{p=null;}}",
            f'if(!p){{r.skip_reason="{_SKIP_PRECONDITION_UNOBSERVED}";}}else{{',
            "try{pv=!!p.isEnable();r.pre_read=true;r.pre=__dg(pv);}catch(e){}",
            'if(!r.pre_read){r.skip_reason="precondition_unobserved";}else{',
            f"try{{r.attempted=true;p.setEnable(true);}}catch(e){{r.call_error={reader}(e);}}",
            "try{qv=!!p.isEnable();r.post_read=true;r.post=__dg(qv);}catch(e){}",
            "if(r.post_read){r.ok=qv===true;}if(r.pre_read&&r.post_read){r.changed=pv!==qv;}",
            "}}results.push(r);",
        ]

    @staticmethod
    def _server_dhcp_pool_lines(
        row: str,
        action: ConfigureServerDhcpPool,
        reader: str,
    ) -> list[str]:
        """Ensure one named pool without deleting or overwriting conflicts."""
        interface = json.dumps(action.interface)
        pool_name = json.dumps(action.pool_name)
        wanted_ranges = [
            item.model_dump(mode="json") for item in action.excluded_ranges
        ]
        wanted = {
            "name": action.pool_name,
            "network": action.network,
            "mask": action.netmask,
            "gateway": action.gateway,
            "dns": action.dns_server,
            "start": action.lease_start,
            "end": action.lease_end,
            "max": action.max_users,
            "exclusions": wanted_ranges,
        }
        wanted_json = json.dumps(wanted, sort_keys=True, separators=(",", ":"))
        wanted_js = json.dumps(wanted_json)
        ranges_js = json.dumps(wanted_ranges, separators=(",", ":"))
        setters = (
            f"pool.setNetworkMask({json.dumps(action.network)},{json.dumps(action.netmask)});"
            f"pool.setDefaultRouter({json.dumps(action.gateway)});"
            + (
                f"pool.setDnsServerIp({json.dumps(action.dns_server)});"
                if action.dns_server
                else ""
            )
            + f"pool.setStartIp({json.dumps(action.lease_start)});"
            f"pool.setEndIp({json.dumps(action.lease_end)});"
            f"pool.setMaxUsers({action.max_users});"
        )
        return [
            row,
            'var m=d.getProcess("DhcpServer");var p=null;var pv=null,qv=null;',
            f"var __want=JSON.parse({wanted_js});var __ranges={ranges_js};",
            "function __xs(){var out=[];var n=p.getExcludedAddressCount();"
            "if(typeof n!=='number'||n<0||Math.floor(n)!==n){throw new Error('excluded_count');}"
            "for(var i=0;i<n;i++){var x=p.getExcludedAddressAt(i);"
            "if(!x){throw new Error('excluded_row');}"
            "out.push({start:String(x.first),end:String(x.second)});}return out;}",
            f"function __rd(){{var pool=p.getPool({pool_name});var xs=__xs();"
            "if(!pool){return JSON.stringify({exists:false,exclusions:xs});}"
            "return JSON.stringify({exists:true,name:String(pool.getDhcpPoolName()),"
            "network:String(pool.getNetworkAddress()),mask:String(pool.getSubnetMask()),"
            "gateway:String(pool.getDefaultRouter()),dns:String(pool.getDnsServerIp()),"
            "start:String(pool.getStartIp()),end:String(pool.getEndIp()),"
            "max:pool.getMaxUsers(),exclusions:xs});}",
            "function __base(v){return v.exists===true&&v.name===__want.name&&"
            "v.network===__want.network&&v.mask===__want.mask&&"
            "v.gateway===__want.gateway&&v.dns===__want.dns&&"
            "v.start===__want.start&&v.end===__want.end&&v.max===__want.max;}",
            "function __has(xs,w){for(var i=0;i<xs.length;i++){"
            "if(xs[i].start===w.start&&xs[i].end===w.end){return true;}}return false;}",
            "function __ok(v){if(!__base(v)){return false;}"
            "for(var i=0;i<__want.exclusions.length;i++){"
            "if(!__has(v.exclusions,__want.exclusions[i])){return false;}}return true;}",
            f"try{{p=m&&m.getDhcpServerProcessByPortName({interface});}}catch(e){{p=null;}}",
            f'if(!p){{r.skip_reason="{_SKIP_PRECONDITION_UNOBSERVED}";}}else{{',
            "try{pv=__rd();r.pre_read=true;r.pre=__dg(pv);}catch(e){}",
            f'if(!r.pre_read){{r.skip_reason="{_SKIP_PRECONDITION_UNOBSERVED}";}}else{{',
            "var pre=JSON.parse(pv);if(pre.exists&&!__base(pre)){"
            f'r.skip_reason="{_SKIP_POOL_CONFLICT}";}}else if(__ok(pre)){{'
            f'r.skip_reason="{_SKIP_ALREADY_SATISFIED}";}}else{{',
            "try{r.attempted=true;var pool=null;if(!pre.exists){"
            f"p.addPool({pool_name});pool=p.getPool({pool_name});"
            "if(!pool){throw new Error('pool_missing_after_add');}"
            f"}}else{{pool=p.getPool({pool_name});}}"
            "for(var i=0;i<__ranges.length;i++){if(!__has(pre.exclusions,__ranges[i])){"
            "p.addExcludedAddress(__ranges[i].start,__ranges[i].end);}}"
            "if(!pre.exists){" + setters + "}"
            f"}}catch(e){{r.call_error={reader}(e);}}}}"
            "try{qv=__rd();r.post_read=true;r.post=__dg(qv);}catch(e){}"
            "if(r.post_read){r.ok=__ok(JSON.parse(qv));}"
            "if(r.pre_read&&r.post_read){r.changed=pv!==qv;}",
            "}}results.push(r);",
        ]

    @staticmethod
    def _acquire_dhcp_lines(
        row: str,
        action: AcquireDhcpLease,
        reader: str,
    ) -> list[str]:
        """Call documented void `dhcpRun(port)` once under a subject claim."""
        action_id = json.dumps(action.id)
        interface = json.dumps(action.interface)
        key = json.dumps(
            f"{_DHCP_CLAIM_PREFIX}{action.host_device_id}:{action.interface}"
        )
        return [
            row,
            f"var __key={key},__aid={action_id},__if={interface};",
            f"var __c={_CLAIMS}={_CLAIMS}||{{}};",
            "var __has=Object.prototype.hasOwnProperty.call(__c,__key);",
            "if(__has){var __v=__c[__key];if(!__v||typeof __v!=='object'||"
            "typeof __v.op_id!=='string'||typeof __v.interface!=='string'){"
            f'r.skip_reason="{_SKIP_SUBJECT_CLAIM_UNREADABLE}";}}'
            "else if(__v.op_id===__aid&&__v.interface===__if){"
            f'r.skip_reason="{_SKIP_OWN_CLAIM_REPLAYED}";}}else{{'
            f'r.skip_reason="{_SKIP_SUBJECT_CLAIMED}";}}}}else{{',
            "var port=null;for(var i=0;i<d.getPortCount();i++){var q=d.getPortAt(i);"
            "if(q&&typeof q.getName==='function'&&String(q.getName())===__if){port=q;break;}}",
            'var p=d.getProcess("DhcpClient");var mode=null;'
            "try{mode=port&&typeof port.isDhcpClientOn==='function'?!!port.isDhcpClientOn():null;}catch(e){mode=null;}",
            f'if(mode===false){{r.pre_read=true;r.pre=__dg(mode);r.skip_reason="{_SKIP_DHCP_MODE_NOT_ENABLED}";}}'
            f'else if(mode!==true||!p){{r.skip_reason="{_SKIP_PRECONDITION_UNOBSERVED}";}}else{{',
            "r.pre_read=true;r.pre=__dg(mode);"
            "__c[__key]={state:'in_progress',op_id:__aid,interface:__if};",
            f"try{{r.attempted=true;p.dhcpRun(__if);__c[__key].state='completed';}}"
            f"catch(e){{__c[__key].state='unknown';r.call_error={reader}(e);}}",
            "}}results.push(r);",
        ]

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
        if expectation.kind in _GATED_EVENT_KINDS:
            return self._gated_event_row(expectation)
        if expectation.kind is ServiceVerificationKind.EMAIL_CLIENT_STATE:
            with _MAIL_LOCK:
                return self._verify_email_client(expectation)
        if expectation.kind is ServiceVerificationKind.SMTP_DELIVERED:
            with _MAIL_LOCK:
                return self._verify_smtp_delivered(expectation)
        if expectation.kind is ServiceVerificationKind.DHCP_SERVER_STATE:
            with _MAIL_LOCK:
                return self._verify_dhcp_server_state(expectation)
        if expectation.kind is ServiceVerificationKind.DHCP_LEASE:
            with _MAIL_LOCK:
                return self._verify_dhcp_lease(expectation)
        if expectation.kind is ServiceVerificationKind.DHCP_LEASE_ATTRIBUTED:
            with _MAIL_LOCK:
                return self._verify_dhcp_lease_attributed(expectation)
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

        This is also the one funnel every read exit passes, so it is where the
        invocation's secret boundary sits for them. `_apply_batch` redacts its
        own rows, but a verification resolves nothing and used to hand
        `observation.outcome.detail` straight through: a value resolved
        earlier in the same invocation could come back in an engine error the
        reader merely bounded (R-SEC-01).
        """
        status, fresh = _OBSERVATION_STATUS[observation]
        redact = self._sanitizer.redact
        return RuntimeServiceVerification(
            expectation_id=expectation.id,
            status=status,
            evidence_kind=expectation.evidence_kind,
            evidence_method=method,
            fresh_evidence=fresh,
            observed={
                key: redact(value) if isinstance(value, str) else value
                for key, value in (observed or {}).items()
            },
            observation=observation,
            cause=self._safe(cause),
            claim_level=claim_level,
            limitations=[redact(item) for item in limitations],
            message=redact(message),
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

    def _verify_dhcp_server_state(self, expectation):
        """Read exact stored DHCP fields without claiming lease-state cleanliness."""
        expected = expectation.expected
        host = json.dumps(expectation.host_device_name)
        interface = json.dumps(str(expected.get("interface") or ""))
        pool_name = json.dumps(str(expected.get("pool_name") or ""))
        reader = "__ec" if self._sanitizer.holds_values else "__er"
        helper = (
            _ERROR_CATEGORY_HELPER
            if self._sanitizer.holds_values
            else _ERROR_TEXT_HELPER
        )
        script = (
            helper + f"try{{var d=ipc.network().getDevice({host});"
            'var m=d&&d.getProcess("DhcpServer");'
            f"var p=m&&m.getDhcpServerProcessByPortName({interface});"
            f"var q=p&&p.getPool({pool_name});var xs=[];"
            "if(p){var n=p.getExcludedAddressCount();for(var i=0;i<n;i++){"
            "var x=p.getExcludedAddressAt(i);xs.push({start:String(x.first),end:String(x.second)});}}"
            "var out={found:!!d,process_found:!!p,pool_found:!!q,"
            f"interface:{interface},pool_name:q?String(q.getDhcpPoolName()):'',"
            "enabled:p?!!p.isEnable():null,network:q?String(q.getNetworkAddress()):'',"
            "mask:q?String(q.getSubnetMask()):'',gateway:q?String(q.getDefaultRouter()):'',"
            "dns:q?String(q.getDnsServerIp()):'',start:q?String(q.getStartIp()):'',"
            "end:q?String(q.getEndIp()):'',max:q?q.getMaxUsers():null,exclusions:xs,error:''};"
            "reportResult(JSON.stringify(out));}catch(e){reportResult(JSON.stringify({"
            f"found:false,process_found:false,pool_found:false,interface:{interface},"
            f"pool_name:'',enabled:null,network:'',mask:'',gateway:'',dns:'',start:'',end:'',max:null,exclusions:[],error:{reader}(e)}}));}}"
        )
        observation = self._observe(script, 5.0)
        if observation.kind is not BridgeObservationKind.PAYLOAD:
            return self._observed(
                expectation,
                observation=self._transport_fact(observation),
                method="dhcp_server_configuration_readback",
                cause=observation.outcome.detail or observation.message,
            )
        payload = observation.payload or {}
        scalar_types = {
            "found": bool,
            "process_found": bool,
            "pool_found": bool,
            "interface": str,
            "pool_name": str,
            "network": str,
            "mask": str,
            "gateway": str,
            "dns": str,
            "start": str,
            "end": str,
            "error": str,
        }
        shape = _typed_payload(payload, scalar_types)
        if (
            shape
            or payload.get("enabled") is not True
            or isinstance(payload.get("max"), bool)
            or not isinstance(payload.get("max"), int)
            or not isinstance(payload.get("exclusions"), list)
        ):
            return self._observed(
                expectation,
                observation=ObservationFact.MALFORMED,
                method="dhcp_server_configuration_readback",
                cause=f"dhcp_server_shape:{shape or 'typed_fields'}",
            )
        if payload["error"]:
            return self._observed(
                expectation,
                observation=ObservationFact.ENGINE_ERROR,
                method="dhcp_server_configuration_readback",
                cause=payload["error"],
            )
        if not payload["found"] or not payload["process_found"]:
            return self._observed(
                expectation,
                observation=ObservationFact.SUBJECT_NOT_FOUND,
                method="dhcp_server_configuration_readback",
                cause="dhcp_server_process_not_found",
            )
        if not payload["pool_found"]:
            return self._observed(
                expectation,
                observation=ObservationFact.CONTRADICTED,
                method="dhcp_server_configuration_readback",
                cause="dhcp_pool_not_found",
            )
        ranges = payload["exclusions"]
        if any(
            not isinstance(item, dict)
            or set(item) != {"start", "end"}
            or not all(isinstance(item[key], str) for key in ("start", "end"))
            for item in ranges
        ):
            return self._observed(
                expectation,
                observation=ObservationFact.MALFORMED,
                method="dhcp_server_configuration_readback",
                cause="dhcp_exclusion_shape",
            )
        try:
            wanted_ranges = json.loads(
                str(expected.get("excluded_ranges_json") or "[]")
            )
        except json.JSONDecodeError:
            wanted_ranges = None
        if not isinstance(wanted_ranges, list):
            return self._observed(
                expectation,
                observation=ObservationFact.MALFORMED,
                method="dhcp_server_configuration_readback",
                cause="dhcp_expected_exclusions_invalid",
            )
        matches = (
            payload["interface"] == expected.get("interface")
            and payload["pool_name"] == expected.get("pool_name")
            and payload["network"] == expected.get("network")
            and payload["mask"] == expected.get("netmask")
            and payload["gateway"] == expected.get("gateway")
            and payload["dns"] == expected.get("dns_server")
            and payload["start"] == expected.get("lease_start")
            and payload["end"] == expected.get("lease_end")
            and payload["max"] == expected.get("max_users")
            and all(item in ranges for item in wanted_ranges)
        )
        return self._observed(
            expectation,
            observation=(
                ObservationFact.OBSERVED if matches else ObservationFact.CONTRADICTED
            ),
            method="dhcp_server_configuration_readback",
            claim_level="stored_dhcp_configuration" if matches else "",
            cause="" if matches else "dhcp_server_state_mismatch",
            observed={
                "interface": payload["interface"],
                "pool_name": payload["pool_name"],
                "excluded_range_count": len(ranges),
            },
            limitations=("lease_allocation_state_unobserved",),
        )

    def _verify_dhcp_lease(self, expectation):
        """Read mode/address/lease-time without attributing acquisition."""
        if expectation.expected.get("configure_only") is True:
            return RuntimeServiceVerification(
                expectation_id=expectation.id,
                status=ActionExecutionStatus.UNKNOWN,
                evidence_kind=expectation.evidence_kind,
                evidence_method="dhcp_client_readback",
                fresh_evidence=False,
                observation=ObservationFact.NOT_ATTEMPTED,
                claim_level="acquisition_not_attempted",
                cause="configure_only",
                message="No explicit DHCP acquisition was requested.",
            )
        host = json.dumps(expectation.client_device_name)
        interface = json.dumps(str(expectation.expected.get("interface") or ""))
        reader = "__ec" if self._sanitizer.holds_values else "__er"
        helper = (
            _ERROR_CATEGORY_HELPER
            if self._sanitizer.holds_values
            else _ERROR_TEXT_HELPER
        )
        script = (
            helper
            + f"try{{var d=ipc.network().getDevice({host});var want={interface};var p=null;"
            "if(d){for(var i=0;i<d.getPortCount();i++){var c=d.getPortAt(i);"
            "if(c&&typeof c.getName==='function'&&String(c.getName())===want){p=c;break;}}}"
            "var modeable=!!p&&typeof p.isDhcpClientOn==='function';"
            "var addressable=!!p&&typeof p.getIpAddress==='function'&&typeof p.getSubnetMask==='function';"
            "var macable=!!p&&typeof p.getMacAddress==='function';"
            'var cp=d&&d.getProcess("DhcpClient");var data=cp&&cp.getDataOfPort(want);'
            "reportResult(JSON.stringify({found:!!d,port_found:!!p,interface:want,"
            "mode_channel:modeable,address_channel:addressable,mac_channel:macable,"
            "dhcp_mode:modeable?!!p.isDhcpClientOn():null,"
            "ipv4:addressable?String(p.getIpAddress()):'',"
            "netmask:addressable?String(p.getSubnetMask()):'',"
            "mac:macable?String(p.getMacAddress()):'',"
            "lease_time:data?String(data.getLeaseTimeStr()):'',error:''}));}catch(e){"
            "reportResult(JSON.stringify({found:false,port_found:false,"
            f"interface:{interface},mode_channel:false,address_channel:false,mac_channel:false,"
            f"dhcp_mode:null,ipv4:'',netmask:'',mac:'',lease_time:'',error:{reader}(e)}}));}}"
        )
        observation = self._observe(script, self._mail_timeout)
        if observation.kind is not BridgeObservationKind.PAYLOAD:
            return self._observed(
                expectation,
                observation=self._transport_fact(observation),
                method="dhcp_client_readback",
                cause=observation.outcome.detail or observation.message,
            )
        payload = observation.payload or {}
        shape = _typed_payload(
            payload,
            {
                "found": bool,
                "port_found": bool,
                "interface": str,
                "mode_channel": bool,
                "address_channel": bool,
                "mac_channel": bool,
                "ipv4": str,
                "netmask": str,
                "mac": str,
                "lease_time": str,
                "error": str,
            },
        )
        if shape or payload.get("dhcp_mode") not in {True, False, None}:
            return self._observed(
                expectation,
                observation=ObservationFact.MALFORMED,
                method="dhcp_client_readback",
                cause=f"dhcp_client_shape:{shape or 'dhcp_mode'}",
            )
        if payload["error"]:
            return self._observed(
                expectation,
                observation=ObservationFact.ENGINE_ERROR,
                method="dhcp_client_readback",
                cause=payload["error"],
            )
        if (
            not payload["found"]
            or not payload["port_found"]
            or payload["interface"] != expectation.expected.get("interface")
            or not payload["mode_channel"]
            or not payload["address_channel"]
        ):
            return self._observed(
                expectation,
                observation=ObservationFact.SUBJECT_NOT_FOUND,
                method="dhcp_client_readback",
                cause="dhcp_client_subject_unreadable",
            )
        observed = {
            "interface": payload["interface"],
            "dhcp_mode": bool(payload["dhcp_mode"]),
            "ipv4": payload["ipv4"],
            "netmask": payload["netmask"],
            "lease_time": payload["lease_time"],
        }
        if payload["dhcp_mode"] is not True:
            return self._observed(
                expectation,
                observation=ObservationFact.CONTRADICTED,
                method="dhcp_client_readback",
                cause="dhcp_mode_disabled",
                observed=observed,
            )
        if not payload["ipv4"] and not payload["netmask"]:
            return self._observed(
                expectation,
                observation=ObservationFact.INCONCLUSIVE,
                method="dhcp_client_readback",
                cause="acquisition_not_observed",
                observed=observed,
            )
        if not payload["ipv4"] or not payload["netmask"]:
            return self._observed(
                expectation,
                observation=ObservationFact.MALFORMED,
                method="dhcp_client_readback",
                cause="address_mask_incomplete",
                observed=observed,
            )
        try:
            address = ip_address(payload["ipv4"])
            network = ip_network(
                f"{expectation.expected.get('network')}/{expectation.expected.get('prefix')}",
                strict=True,
            )
        except ValueError:
            return self._observed(
                expectation,
                observation=ObservationFact.MALFORMED,
                method="dhcp_client_readback",
                cause="address_not_parsable",
                observed=observed,
            )
        compatible = (
            address in network
            and address not in {network.network_address, network.broadcast_address}
            and payload["netmask"] == expectation.expected.get("netmask")
        )
        return self._observed(
            expectation,
            observation=(
                ObservationFact.INCONCLUSIVE
                if compatible
                else ObservationFact.CONTRADICTED
            ),
            method="dhcp_client_readback",
            claim_level="fresh_address_readback" if compatible else "",
            cause="acquisition_unattributed" if compatible else "foreign_lease",
            observed=observed,
            limitations=("lease_time_causality_unqualified",),
        )

    def _verify_dhcp_lease_attributed(self, expectation):
        """Bound a positive intended-pool row without inventing scan completion."""
        expected = expectation.expected
        server = json.dumps(expectation.host_device_name)
        client = json.dumps(expectation.client_device_name)
        client_interface = json.dumps(str(expected.get("interface") or ""))
        server_interface = json.dumps(
            str(expected.get("server_interface") or expected.get("interface") or "")
        )
        pool_name = json.dumps(str(expected.get("pool_name") or ""))
        declared = int(expected.get("max_users") or 0)
        bound = min(max(declared, 0), DHCP_LEASE_SCAN_LIMIT)
        reader = "__ec" if self._sanitizer.holds_values else "__er"
        helper = (
            _ERROR_CATEGORY_HELPER
            if self._sanitizer.holds_values
            else _ERROR_TEXT_HELPER
        )
        script = (
            helper
            + f"try{{var cd=ipc.network().getDevice({client});var want={client_interface};var cp=null;"
            "if(cd){for(var i=0;i<cd.getPortCount();i++){var c=cd.getPortAt(i);"
            "if(c&&typeof c.getName==='function'&&String(c.getName())===want){cp=c;break;}}}"
            f"var sd=ipc.network().getDevice({server});var sm=sd&&sd.getProcess('DhcpServer');"
            f"var sp=sm&&sm.getDhcpServerProcessByPortName({server_interface});"
            f"var pool=sp&&sp.getPool({pool_name});var rows=[];var repeated=false;"
            "var seen={};var scan_error='';if(pool){for(var j=0;j<"
            + str(bound)
            + ";j++){try{var r=pool.getLeaseAt(j);if(!r){break;}"
            "var row={ipAddress:String(r.ipAddress),macAddress:String(r.macAddress),"
            "leaseTime:r.leaseTime,port:String(r.port)};var key=JSON.stringify(row);"
            "if(seen[key]){repeated=true;break;}seen[key]=true;rows.push(row);"
            f"}}catch(e){{scan_error={reader}(e);break;}}}}"
            "}reportResult(JSON.stringify({client_found:!!cd,port_found:!!cp,"
            "interface:want,ipv4:cp?String(cp.getIpAddress()):'',"
            "netmask:cp?String(cp.getSubnetMask()):'',mac:cp?String(cp.getMacAddress()):'',"
            f"server_found:!!sd,process_found:!!sp,pool_found:!!pool,pool_name:pool?String(pool.getDhcpPoolName()):'',"
            "rows:rows,repeated:repeated,scan_error:scan_error,error:''}));}catch(e){"
            "reportResult(JSON.stringify({client_found:false,port_found:false,"
            f"interface:{client_interface},ipv4:'',netmask:'',mac:'',server_found:false,"
            f"process_found:false,pool_found:false,pool_name:'',rows:[],repeated:false,scan_error:'',error:{reader}(e)}}));}}"
        )
        observation = self._observe(script, 5.0)
        if observation.kind is not BridgeObservationKind.PAYLOAD:
            return self._observed(
                expectation,
                observation=self._transport_fact(observation),
                method="dhcp_intended_pool_lease_scan",
                cause=observation.outcome.detail or observation.message,
            )
        payload = observation.payload or {}
        shape = _typed_payload(
            payload,
            {
                "client_found": bool,
                "port_found": bool,
                "interface": str,
                "ipv4": str,
                "netmask": str,
                "mac": str,
                "server_found": bool,
                "process_found": bool,
                "pool_found": bool,
                "pool_name": str,
                "repeated": bool,
                "scan_error": str,
                "error": str,
            },
        )
        rows = payload.get("rows")
        if shape or not isinstance(rows, list):
            return self._observed(
                expectation,
                observation=ObservationFact.MALFORMED,
                method="dhcp_intended_pool_lease_scan",
                cause=f"lease_scan_shape:{shape or 'rows'}",
            )
        for row in rows:
            if (
                not isinstance(row, dict)
                or set(row) != {"ipAddress", "macAddress", "leaseTime", "port"}
                or not all(
                    isinstance(row[key], str)
                    for key in ("ipAddress", "macAddress", "port")
                )
                or isinstance(row["leaseTime"], bool)
                or not isinstance(row["leaseTime"], (int, float))
            ):
                return self._observed(
                    expectation,
                    observation=ObservationFact.MALFORMED,
                    method="dhcp_intended_pool_lease_scan",
                    cause="lease_row_shape",
                )
        if payload["error"] or payload["scan_error"]:
            return self._observed(
                expectation,
                observation=ObservationFact.ENGINE_ERROR,
                method="dhcp_intended_pool_lease_scan",
                cause=payload["error"] or payload["scan_error"],
            )
        if not (
            payload["client_found"]
            and payload["port_found"]
            and payload["server_found"]
            and payload["process_found"]
            and payload["pool_found"]
            and payload["interface"] == expected.get("interface")
            and payload["pool_name"] == expected.get("pool_name")
        ):
            return self._observed(
                expectation,
                observation=ObservationFact.SUBJECT_NOT_FOUND,
                method="dhcp_intended_pool_lease_scan",
                cause="lease_scan_subject_not_found",
            )
        same_ip = [row for row in rows if row["ipAddress"] == payload["ipv4"]]
        exact = [row for row in same_ip if row["macAddress"] == payload["mac"]]
        observed = {
            "interface": payload["interface"],
            "ipv4": payload["ipv4"],
            "mac": payload["mac"],
            "rows_scanned": len(rows),
            "scan_limit": bound,
            "truncated": declared > bound,
            "repeated": payload["repeated"],
        }
        if exact:
            return self._observed(
                expectation,
                observation=ObservationFact.OBSERVED,
                method="dhcp_intended_pool_lease_scan",
                claim_level="attributed_to_intended_server",
                observed=observed,
                limitations=("not_acquisition_in_this_run", "not_sole_authority"),
            )
        if (
            same_ip
            and _MAC_TEXT.fullmatch(payload["mac"])
            and any(_MAC_TEXT.fullmatch(row["macAddress"]) for row in same_ip)
        ):
            return self._observed(
                expectation,
                observation=ObservationFact.CONTRADICTED,
                method="dhcp_intended_pool_lease_scan",
                cause="foreign_lease_row",
                observed=observed,
            )
        limitations = ["lease_table_end_condition_unqualified"]
        if payload["repeated"]:
            limitations.append("lease_row_repeated")
        if declared > bound:
            limitations.append("lease_scan_truncated")
        return self._observed(
            expectation,
            observation=ObservationFact.INCONCLUSIVE,
            method="dhcp_intended_pool_lease_scan",
            cause="lease_table_incomplete",
            observed=observed,
            limitations=limitations,
        )

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
        elif service_type is ServiceType.SMTP:
            # Existence per planned account, each in its own try: a getter
            # that throws leaves that account unread (null), never absent.
            accounts = str(expectation.expected.get("accounts_json") or "[]")
            lines.append(
                "out.domain=String(p.getServerDomainName());"
                'var es=d.getProcess("EmailServer");out.accounts={};'
                "var wanted=JSON.parse(" + json.dumps(accounts) + ");"
                "for(var i=0;i<wanted.length;i++){var n=wanted[i];"
                "try{var u=es.getEmailUser(n);out.accounts[n]=!!u&&String(u.getUser())===n;}"
                "catch(e){out.accounts[n]=null;}}"
            )
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
        elif service_type is ServiceType.SMTP:
            return self._smtp_state(expectation, payload, enabled, method, claim)
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

    def _smtp_state(self, expectation, payload, enabled, method, claim):
        """Judge the SMTP flag, domain and account existence together.

        Existence never proves a credential, so every row says so. An account
        whose getter threw is unread: the reading is inconclusive rather than
        a contradiction, because a getter failure is not an absent account.
        """
        domain = payload.get("domain")
        accounts = payload.get("accounts")
        limitations = ["credential_claim:unverified"]
        if not isinstance(domain, str) or not isinstance(accounts, dict):
            return self._observed(
                expectation,
                observation=ObservationFact.MALFORMED,
                method=method,
                claim_level=claim,
                cause="typed_shape_missing",
                message="The direct read-back payload is not the typed shape.",
            )
        wanted = json.loads(str(expectation.expected.get("accounts_json") or "[]"))
        values = [accounts.get(name, "absent") for name in wanted]
        if any(value is not None and not isinstance(value, bool) for value in values):
            return self._observed(
                expectation,
                observation=ObservationFact.MALFORMED,
                method=method,
                claim_level=claim,
                cause="account_shape",
                message="The account read-back is not the typed shape.",
            )
        if any(value is None for value in values):
            return self._observed(
                expectation,
                observation=ObservationFact.INCONCLUSIVE,
                method=method,
                claim_level=claim,
                cause="account_unreadable",
                limitations=limitations,
                message="An account could not be read, which is not an absence.",
            )
        matches = (
            enabled
            and domain == str(expectation.expected.get("domain_name") or "")
            and all(values)
        )
        return self._observed(
            expectation,
            observation=(
                ObservationFact.OBSERVED if matches else ObservationFact.CONTRADICTED
            ),
            method=method,
            claim_level=claim,
            observed={"enabled": enabled},
            limitations=limitations,
            message=(
                "Structured service state matched."
                if matches
                else "Structured service state differed."
            ),
        )

    def _verify_email_client(self, expectation):
        """Read one client's mail user back, every field except the password."""
        client = json.dumps(expectation.client_device_name)
        observation = self._observe(
            f"var d=ipc.network().getDevice({client});"
            'var p=d?d.getProcess("EmailClient"):null;var out={found:!!p};'
            "if(p){var u=p.getEmailUser();out.fields=[String(u.getName()),"
            "String(u.getUser()),String(u.getMailId()),String(u.getSmtpServer()),"
            "String(u.getPop3Server())];}reportResult(JSON.stringify(out));",
            5.0,
        )
        method = "structured_email_client_getters"
        claim = "direct_client_state"
        limitations = ["password_not_read"]
        if observation.kind is not BridgeObservationKind.PAYLOAD:
            return self._observed(
                expectation,
                observation=self._transport_fact(observation),
                method=method,
                claim_level=claim,
                cause=observation.outcome.detail,
                message="The client read-back did not deliver a correlated answer.",
            )
        payload = observation.payload or {}
        if payload.get("found") is not True:
            return self._observed(
                expectation,
                observation=(
                    ObservationFact.SUBJECT_NOT_FOUND
                    if payload.get("found") is False
                    else ObservationFact.MALFORMED
                ),
                method=method,
                claim_level=claim,
                cause="email_client_not_found",
                message="The client has no readable email process.",
            )
        fields = payload.get("fields")
        if not isinstance(fields, list) or not all(
            isinstance(item, str) for item in fields
        ):
            return self._observed(
                expectation,
                observation=ObservationFact.MALFORMED,
                method=method,
                claim_level=claim,
                cause="typed_shape_missing",
                message="The client read-back payload is not the typed shape.",
            )
        wanted = [
            str(expectation.expected.get(name) or "")
            for name in ("name", "user", "mail_id", "smtp_server", "pop3_server")
        ]
        matches = fields == wanted
        return self._observed(
            expectation,
            observation=(
                ObservationFact.OBSERVED if matches else ObservationFact.CONTRADICTED
            ),
            method=method,
            claim_level=claim,
            limitations=limitations,
            message=(
                "The client's mail fields matched."
                if matches
                else "The client's mail fields differed."
            ),
        )

    def _verify_smtp_delivered(self, expectation):
        """Scan the recipient's server mailbox for this pair's message, read-only.

        Presence and only presence: not the sender's `mailSent`, not a POP3
        retrieval, and never a change to the send row. The scan is bounded,
        newest first, and returns counts and flags -- another message's text
        never leaves the engine. Absence within the deadline is unknown, never
        a failure, and a truncated scan cannot prove absence at all.
        """
        method = "server_mailbox_scan"
        claim = "server_mailbox_presence"
        nonce = str(expectation.expected.get("nonce") or "")
        if not nonce:
            return self._observed(
                expectation,
                observation=ObservationFact.MALFORMED,
                method=method,
                claim_level=claim,
                cause="message_nonce_unbound",
                message="The row carries no bound message nonce.",
            )
        host = json.dumps(expectation.host_device_name)
        user = json.dumps(str(expectation.expected.get("recipient_username") or ""))
        text = json.dumps(mail_message_text(nonce))
        sender = json.dumps(str(expectation.expected.get("sender_mail_id") or ""))
        recipient = json.dumps(str(expectation.expected.get("recipient_mail_id") or ""))
        script = (
            f"var d=ipc.network().getDevice({host});"
            'var es=d?d.getProcess("EmailServer"):null;'
            "var out={found_user:false,count:0,scanned:0,truncated:false,"
            "matches:0,mismatched:0};"
            f"if(es){{var u=es.getEmailUser({user});"
            f"if(u&&String(u.getUser())==={user}){{out.found_user=true;"
            "var ms=u.getMailBox().getMails();var n=ms?ms.length:0;out.count=n;"
            f"for(var i=n-1;i>=0&&out.scanned<{MAILBOX_SCAN_LIMIT};i--){{"
            f"var m=ms[i];out.scanned++;if(String(m.subject)==={text}){{"
            f"if(String(m.from)==={sender}&&String(m.rcpt)==={recipient}"
            f"&&String(m.content).indexOf({text})>=0){{out.matches++;}}"
            "else{out.mismatched++;}}}out.truncated=n>out.scanned;}}"
            "reportResult(JSON.stringify(out));"
        )
        spec = {
            "found_user": bool,
            "truncated": bool,
            "count": int,
            "scanned": int,
            "matches": int,
            "mismatched": int,
        }

        def admissible(item: BridgeObservation) -> dict | None:
            if item.kind is not BridgeObservationKind.PAYLOAD:
                return None
            payload = item.payload or {}
            for name, kind in spec.items():
                value = payload.get(name)
                if isinstance(value, bool) is not (kind is bool) or not isinstance(
                    value, kind
                ):
                    return None
            return payload

        def settled(item: BridgeObservation) -> bool:
            payload = admissible(item)
            if payload is None or mailbox_scan_incoherence(payload):
                # An answer whose counters contradict the scan is not an
                # answer. Ending the wait on one would let an unusable
                # payload stand where a real reading was still coming.
                return False
            return bool(
                not payload["found_user"] or payload["matches"] or payload["mismatched"]
            )

        observation = self._poll(
            lambda: self._observe(script, 3.0), settled, self._mail_timeout
        )
        if observation.kind is not BridgeObservationKind.PAYLOAD:
            return self._observed(
                expectation,
                observation=self._transport_fact(observation),
                method=method,
                claim_level=claim,
                cause=observation.outcome.detail,
                message="The mailbox scan did not deliver a correlated answer.",
            )
        payload = admissible(observation)
        if payload is None:
            return self._observed(
                expectation,
                observation=ObservationFact.MALFORMED,
                method=method,
                claim_level=claim,
                cause="typed_shape_missing",
                message="The mailbox scan payload is not the typed shape.",
            )
        broken = mailbox_scan_incoherence(payload)
        if broken:
            # The fields are the right types and still describe a scan that
            # cannot have happened -- a match among zero examined messages,
            # say. Type-checking alone admitted that as presence.
            return self._observed(
                expectation,
                observation=ObservationFact.MALFORMED,
                method=method,
                claim_level=claim,
                cause=f"mailbox_scan_incoherent:{broken}",
                message="The mailbox scan counters contradict the scan itself.",
            )
        observed = {
            "scanned": payload["scanned"],
            "matches": payload["matches"],
            "truncated": payload["truncated"],
        }
        if not payload["found_user"]:
            return self._observed(
                expectation,
                observation=ObservationFact.SUBJECT_NOT_FOUND,
                method=method,
                claim_level=claim,
                cause="recipient_account_not_found",
                message="The recipient account was not present on the server.",
            )
        if payload["mismatched"]:
            return self._observed(
                expectation,
                observation=ObservationFact.CONTRADICTED,
                method=method,
                claim_level=claim,
                cause="nonce_message_fields_mismatch",
                observed=observed,
                limitations=list(_MAIL_DELIVERY_LIMITATIONS),
                message="A message carrying this pair's nonce has other fields.",
            )
        if payload["matches"]:
            count = payload["matches"]
            row = self._observed(
                expectation,
                observation=ObservationFact.OBSERVED,
                method=method,
                claim_level=claim,
                observed=observed,
                limitations=[
                    *_MAIL_DELIVERY_LIMITATIONS,
                    "supporting_evidence_only",
                    *([f"nonce_message_count:{count}"] if count > 1 else []),
                ],
                message="The pair's message is present in the recipient's mailbox.",
            )
            # The reading is an observation; the claim is not verification of
            # the mail service. VERIFIED would roll up into service usability
            # while the send's own outcome stays unobserved and no retrieval
            # exists, which is the false success R-EVT-05's fallback forbids
            # (the same shape as R-HTTPS-03's unattributable page).
            return row.model_copy(update={"status": ActionExecutionStatus.PARTIAL})
        return self._observed(
            expectation,
            observation=ObservationFact.INCONCLUSIVE,
            method=method,
            claim_level=claim,
            cause=(
                "mailbox_scan_truncated"
                if payload["truncated"]
                else "message_not_observed_within_deadline"
            ),
            observed=observed,
            limitations=list(_MAIL_DELIVERY_LIMITATIONS),
            message="The pair's message was not observed in the scanned mailbox.",
        )

    @staticmethod
    def _gated_event_row(expectation):
        """Report an event-dependent row that no observer may serve (R-EVT-05).

        Nothing is dispatched: no `registerEvent`, no `getMailIpc`. The row is
        a typed blocked result, never a success and never a failure.
        """
        return RuntimeServiceVerification(
            expectation_id=expectation.id,
            status=ActionExecutionStatus.UNOBSERVABLE,
            evidence_kind=expectation.evidence_kind,
            evidence_method="event_observation_not_admitted",
            fresh_evidence=False,
            observation=ObservationFact.NOT_ATTEMPTED,
            cause=_GATED_EVENT_CAUSE,
            message=(
                "Event-dependent verification is gated: no safe zero-event "
                "release is established, so no observer is registered."
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
        # The window is read once, before either expectation is applied, so
        # the admissibility policy cannot differ between the two directions.
        reading = _dns_window_reading(window)
        if reading.kind is DnsWindowKind.AMBIGUOUS:
            return self._observed(
                expectation,
                observation=ObservationFact.INCONCLUSIVE,
                method=method,
                claim_level=claim,
                cause=reading.reason,
                message="The DNS command window is not a readable observation.",
            )
        if reading.kind is DnsWindowKind.NOT_FOUND:
            return self._observed(
                expectation,
                observation=(
                    ObservationFact.OBSERVED
                    if negative
                    else ObservationFact.CONTRADICTED
                ),
                method=method,
                claim_level=claim,
                cause="" if negative else "host_not_found",
                observed={"hostname": hostname, "resolved": False} if negative else {},
                message=(
                    "DNS negative control did not resolve."
                    if negative
                    else "Fresh DNS command output contradicted the expectation."
                ),
            )
        matched = not negative and reading.address == expected
        return self._observed(
            expectation,
            observation=(
                ObservationFact.OBSERVED if matched else ObservationFact.CONTRADICTED
            ),
            method=method,
            claim_level=claim,
            observed={"hostname": hostname, "address": reading.address},
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
        if not isinstance(owned, bool):
            return self._observed(
                expectation,
                observation=ObservationFact.MALFORMED,
                method=method,
                claim_level=claim,
                cause=f"start_shape:{_typed_payload(payload, {'owned': bool})}",
                message="The start payload did not report client ownership.",
            )
        # A reported client settles the lease at once. A DENIED client does
        # not: absence is the only answer that lets the finalization skip its
        # one bounded attempt, so it is granted below and only from a payload
        # that is coherent about it. Until then the obligation stands (V1).
        lease.state = ClientOwnership.OWNED if owned else ClientOwnership.UNKNOWN
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
        if not owned:
            contradiction = _no_client_contradiction(payload, secure=secure)
            if contradiction:
                return self._observed(
                    expectation,
                    observation=ObservationFact.MALFORMED,
                    method=method,
                    claim_level=claim,
                    cause=f"start_inconsistent:{contradiction}",
                    message=(
                        "The start payload denied a client it also reported "
                        "working with."
                    ),
                )
            # No client exists, so nothing about the server was observed and
            # there is no page to attribute anything to.
            lease.state = ClientOwnership.ABSENT
            return self._observed(
                expectation,
                observation=ObservationFact.SUBJECT_NOT_FOUND,
                method=method,
                claim_level=claim,
                cause="client_not_created",
                message="The device did not provide a background HTTP client.",
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
    def _background_http_release(
        expectation_id: str,
        client_json: str,
        *,
        category_errors: bool = False,
    ) -> str:
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
        error_helper = _ERROR_CATEGORY_HELPER if category_errors else _ERROR_TEXT_HELPER
        error_reader = "__ec" if category_errors else "__er"
        return (
            error_helper + f"var d=ipc.network().getDevice({client_json});"
            "var bag=this.__mcpE6HttpClients||{};"
            f"var slot=bag[{key}];"
            "var found=!!(slot&&slot.manager&&slot.client);"
            "var deleted=false;var error='';"
            "if(found){try{slot.manager.deleteClient(slot.client);deleted=true;}"
            f"catch(e){{error={error_reader}(e);}}}}"
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
                self._background_http_release(
                    expectation.id,
                    client,
                    category_errors=self._sanitizer.holds_values,
                ),
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
            # `_with_release` carries this cause into the row's limitations
            # without passing `_observed`, so the boundary is crossed here.
            return ReleaseOutcome(
                _RELEASE_FAILED,
                self._safe(observation.outcome.detail) or "release_not_correlated",
            )
        payload = observation.payload or {}
        shape = _typed_payload(
            payload,
            {"found": bool, "deleted": bool, "present": bool, "error": str},
        )
        if shape:
            return ReleaseOutcome(_RELEASE_UNVERIFIED, f"release_shape:{shape}")
        contradiction = _release_contradiction(payload)
        if contradiction:
            # Correct types describing an impossible evaluation. It proves
            # nothing, least of all a deletion.
            return ReleaseOutcome(
                _RELEASE_UNVERIFIED,
                f"release_inconsistent:{contradiction}",
            )
        if payload["deleted"]:
            return ReleaseOutcome(_RELEASE_RELEASED)
        if payload["found"]:
            return ReleaseOutcome(
                _RELEASE_UNVERIFIED,
                self._safe(payload["error"]) or "delete_not_confirmed",
            )
        if payload["present"]:
            # The slot survives without a manager or a client, so there is
            # something owned here that this release could not act on.
            return ReleaseOutcome(_RELEASE_UNVERIFIED, "slot_not_usable")
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
                    # The engine's own text, and the one place a resolved
                    # value can come back from the evaluation. It crosses the
                    # secret boundary here, before anything folds or crops it.
                    detail=self._safe(body or "engine_error"),
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
