"""The cold-HTTP acceptance envelope: its grant, its frozen proposal and its record.

One acceptance attempt governs one invocation of the unchanged product use case
over an operator-owned disposable deployment: one access switch, one Server-PT
and two static PC-PT clients on one VLAN, HTTP by server address only. The
envelope adds nothing to what the product does. It decides whether the product
may be invoked at all, binds the exact closure the product compiled to what an
operator granted, bounds the invocation, and keeps the evidence.

Everything here is a pure rule over values. A grant is kept raw until it is
parsed, so a malformed field is named instead of rejected by a parser the rule
never sees. Every rule fails closed: an absent or unobservable value refuses.
"""

from __future__ import annotations

import ipaddress
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import Enum, StrEnum
from typing import Any

from pydantic import BaseModel, Field

from ....shared.utils import safe_name_component
from .service_entry import EffectClosureAction, ServiceEffectClosure
from .service_qualification import (
    DiagnosticLifecycleObservation,
    OperationEntry,
    QualificationRefusal,
    RefusalKind,
    is_exact_packet_tracer_build,
    is_full_sha,
)

#: The only channel this envelope binds. The proposal measured the file
#: channel, and a grant naming any other refuses before a transport exists.
ACCEPTANCE_CHANNEL = "file"
GRANT_SCHEMA_VERSION = 1
ENVELOPE_SCHEMA_VERSION = 1
MARKER_PREFIX = "COLD_HTTP_"
MAX_DETAIL = 240
#: A raw terminal answer kept as evidence is bounded, never parsed for more.
MAX_ANSWER_CHARS = 2048
_HEX_TOKEN = re.compile(r"[0-9a-f]{32}")
_SHA256 = re.compile(r"[0-9a-f]{64}")


def _bounded(value: object, limit: int = MAX_DETAIL) -> str:
    """Reduce one value to a bounded single-line diagnostic."""
    return " ".join(str(value or "").split())[:limit]


@dataclass(frozen=True)
class ColdHttpProposal:
    """The operation and time ceiling a grant must name exactly.

    `max_operations` counts Script Engine dispatches at the one effective
    boundary, refused calls excluded. `reserve_operations` and
    `reserve_seconds` are protected for the owned client releases and the
    local finalization; ordinary work never reaches them.
    """

    max_operations: int
    max_seconds: int
    reserve_operations: int
    reserve_seconds: int


#: The frozen ceiling the grant must name. It is not raised here; the
#: executable worst case below fits under it, and the difference is margin,
#: never permission for another action.
COLD_HTTP_PROPOSAL = ColdHttpProposal(
    max_operations=1015,
    max_seconds=420,
    reserve_operations=2,
    reserve_seconds=40,
)
#: The worst case recomputed from the executed nested code, dispatch by
#: dispatch. It corrects the proposal's breakdown in two places: E6 applies in
#: two phase batches before its direct read (3, not 2), and a 30-second
#: readiness window sampled every second cannot start a 31st sample (30 x 6
#: calls + 1 auxiliary read = 181, not 187). The total is 1,010, of which two
#: are the protected releases.
COLD_HTTP_ARITHMETIC: tuple[tuple[str, int], ...] = (
    ("admission_environment_inventory_drift_reads", 5),
    ("e5_ios_boot_wait_90s_at_0_25s", 361),
    ("e5_two_ios_phase_batches_and_one_endpoint_batch", 3),
    ("e5_vlan_21_access_port_3_endpoint_3x121_readback", 387),
    ("readiness_30_samples_x6_calls_plus_auxiliary", 181),
    ("e6_two_phase_batches_and_direct_read", 3),
    ("clients_2_x_start_33_inspections_release", 70),
    ("envelope_bridge_overhead", 0),
)


class AcceptanceSubject(StrEnum):
    """Which admission value an acceptance refusal is about."""

    __str__ = Enum.__str__

    GRANT = "grant"
    AUTHORIZATION_ID = "authorization_id"
    ATTEMPT = "attempt"
    SOURCE = "source"
    BUILD = "build"
    CHANNEL = "channel"
    DEPLOYMENT = "deployment"
    MANIFEST = "manifest"
    SELECTION = "selection"
    MARKER = "marker"
    URL = "url"
    INTENT = "intent"
    BUDGET = "budget"
    PROCESS = "process"
    MAILBOX = "mailbox"
    ISOLATION = "isolation"
    REPOSITORY = "repository"
    CAMPAIGN = "campaign"
    HISTORY = "history"
    ENVELOPE = "envelope"
    LABORATORY = "laboratory"


class AcceptanceRefusal(BaseModel):
    """One typed reason this attempt may not proceed."""

    kind: RefusalKind
    subject: AcceptanceSubject
    detail: str = ""


def acceptance_refusal(
    kind: RefusalKind, subject: AcceptanceSubject, detail: str = ""
) -> AcceptanceRefusal:
    """Build one refusal with a bounded detail."""
    return AcceptanceRefusal(kind=kind, subject=subject, detail=_bounded(detail))


@dataclass(frozen=True)
class GrantedEndpoint:
    """One granted endpoint, named by its deployed runtime identity."""

    name: str
    interface: str
    ipv4: str
    switch_port: str


@dataclass(frozen=True)
class ColdHttpGrant:
    """An operator's exact, single-attempt authorization, as parsed."""

    authorization_id: str
    attempt_id: str
    sha: str
    tree: str
    build: str
    channel: str
    deployment_id: str
    manifest_hash: str
    physical_topology_hash: str
    intent_sha256: str
    switch: str
    switch_model: str
    vlan_id: int
    prefix_length: int
    #: The segment gateway every static endpoint is configured with. It is an
    #: effect of the E5 closure, so it is granted, never inferred.
    gateway: str
    server: GrantedEndpoint
    clients: tuple[GrantedEndpoint, ...]
    marker: str
    url: str
    max_operations: int
    max_seconds: int
    reserve_operations: int
    reserve_seconds: int
    process_id: int
    process_path: str
    process_incarnation: str
    exclusive_disposable_lab: bool
    local_fence_limitation_accepted: bool

    @property
    def run_label(self) -> str:
        """Return the display label the product run carries for this attempt."""
        return f"cold-http-acceptance:{self.attempt_id}"

    @property
    def netmask(self) -> str:
        """Return the dotted mask of the granted prefix."""
        return str(ipaddress.IPv4Network(f"0.0.0.0/{self.prefix_length}").netmask)

    @property
    def endpoints(self) -> tuple[GrantedEndpoint, ...]:
        """Return the server followed by the clients, in granted order."""
        return (self.server, *self.clients)


class _Reader:
    """Read one raw grant field by field, naming each defect it finds."""

    def __init__(self, raw: Mapping[str, Any]) -> None:
        self.raw = raw
        self.found: list[AcceptanceRefusal] = []

    def refuse(self, kind: RefusalKind, subject: AcceptanceSubject, detail: str):
        self.found.append(acceptance_refusal(kind, subject, detail))

    def text(self, source: Mapping[str, Any], key: str, subject) -> str:
        value = source.get(key)
        if value is None:
            self.refuse(RefusalKind.MISSING, subject, key)
            return ""
        if not isinstance(value, str) or not value.strip() or value != value.strip():
            self.refuse(RefusalKind.MALFORMED, subject, f"{key} is not a clean string")
            return ""
        return value

    def integer(self, source: Mapping[str, Any], key: str, subject) -> int | None:
        """Return the integer, or None after naming why there is none.

        None is never a value the rules compare: zero is an integer like any
        other and is checked against its bound, never skipped as absent.
        """
        value = source.get(key)
        if value is None:
            self.refuse(RefusalKind.MISSING, subject, key)
            return None
        if isinstance(value, bool) or not isinstance(value, int):
            self.refuse(RefusalKind.MALFORMED, subject, f"{key} is not an integer")
            return None
        return value

    def flag(self, key: str, subject) -> bool:
        value = self.raw.get(key)
        if value is None:
            self.refuse(RefusalKind.MISSING, subject, key)
            return False
        if not isinstance(value, bool):
            self.refuse(RefusalKind.MALFORMED, subject, f"{key} is not a boolean")
            return False
        return value

    def endpoint(self, value: object, label: str) -> GrantedEndpoint:
        if not isinstance(value, Mapping):
            self.refuse(RefusalKind.MALFORMED, AcceptanceSubject.SELECTION, label)
            return GrantedEndpoint("", "", "", "")
        subject = AcceptanceSubject.SELECTION
        return GrantedEndpoint(
            name=self.text(value, "name", subject),
            interface=self.text(value, "interface", subject),
            ipv4=self.text(value, "ipv4", subject),
            switch_port=self.text(value, "switch_port", subject),
        )


def parse_grant(
    raw: object, proposal: ColdHttpProposal = COLD_HTTP_PROPOSAL
) -> tuple[ColdHttpGrant | None, tuple[AcceptanceRefusal, ...]]:
    """Parse and validate one grant document against the frozen proposal.

    Returns the grant only when it has no refusal at all. Every check here is
    about the document itself; the checkout, process, manifest and history it
    names are compared later, by the rules that consume their observations.
    """
    if not isinstance(raw, Mapping):
        return None, (
            acceptance_refusal(
                RefusalKind.MALFORMED, AcceptanceSubject.GRANT, "not a JSON object"
            ),
        )
    read = _Reader(raw)
    subject = AcceptanceSubject
    version = read.integer(raw, "schema_version", subject.GRANT)
    if version is not None and version != GRANT_SCHEMA_VERSION:
        read.refuse(RefusalKind.MISMATCH, subject.GRANT, f"schema_version {version}")
    authorization_id = read.text(raw, "authorization_id", subject.AUTHORIZATION_ID)
    attempt_id = read.text(raw, "attempt_id", subject.ATTEMPT)
    sha = read.text(raw, "sha", subject.SOURCE)
    tree = read.text(raw, "tree", subject.SOURCE)
    build = read.text(raw, "build", subject.BUILD)
    channel = read.text(raw, "channel", subject.CHANNEL)
    deployment_id = read.text(raw, "deployment_id", subject.DEPLOYMENT)
    manifest_hash = read.text(raw, "manifest_hash", subject.MANIFEST)
    topology_hash = read.text(raw, "physical_topology_hash", subject.MANIFEST)
    intent_sha256 = read.text(raw, "intent_sha256", subject.INTENT)
    switch = read.text(raw, "switch", subject.SELECTION)
    switch_model = read.text(raw, "switch_model", subject.SELECTION)
    vlan_id = read.integer(raw, "vlan_id", subject.SELECTION)
    prefix_length = read.integer(raw, "prefix_length", subject.SELECTION)
    gateway = read.text(raw, "gateway", subject.SELECTION)
    server = read.endpoint(raw.get("server"), "server")
    raw_clients = raw.get("clients")
    clients: tuple[GrantedEndpoint, ...] = ()
    if not isinstance(raw_clients, list):
        read.refuse(RefusalKind.MISSING, subject.SELECTION, "clients")
    else:
        clients = tuple(
            read.endpoint(item, f"clients[{index}]")
            for index, item in enumerate(raw_clients)
        )
    marker = read.text(raw, "marker", subject.MARKER)
    url = read.text(raw, "url", subject.URL)
    budget = {
        key: read.integer(raw, key, subject.BUDGET)
        for key in (
            "max_operations",
            "max_seconds",
            "reserve_operations",
            "reserve_seconds",
        )
    }
    process_id = read.integer(raw, "process_id", subject.PROCESS)
    process_path = read.text(raw, "process_path", subject.PROCESS)
    incarnation = read.text(raw, "process_incarnation", subject.PROCESS)
    lab = read.flag("exclusive_disposable_lab", subject.LABORATORY)
    fence = read.flag("local_fence_limitation_accepted", subject.LABORATORY)

    malformed = RefusalKind.MALFORMED
    if authorization_id and len(authorization_id) > 128:
        read.refuse(malformed, subject.AUTHORIZATION_ID, "longer than 128")
    if attempt_id and not _HEX_TOKEN.fullmatch(attempt_id):
        read.refuse(malformed, subject.ATTEMPT, "not 32 lowercase hex characters")
    for value, name in ((sha, "sha"), (tree, "tree")):
        if value and not is_full_sha(value):
            read.refuse(malformed, subject.SOURCE, f"{name} is not a full SHA")
    if build and not is_exact_packet_tracer_build(build):
        read.refuse(malformed, subject.BUILD, "not one exact four-part build")
    if channel and channel != ACCEPTANCE_CHANNEL:
        read.refuse(
            RefusalKind.NOT_PERMITTED,
            subject.CHANNEL,
            f"only the {ACCEPTANCE_CHANNEL!r} channel is bound by this envelope",
        )
    if deployment_id and safe_name_component(deployment_id, "") != deployment_id:
        read.refuse(malformed, subject.DEPLOYMENT, "not a safe store name")
    for value, name, where in (
        (manifest_hash, "manifest_hash", subject.MANIFEST),
        (topology_hash, "physical_topology_hash", subject.MANIFEST),
        (intent_sha256, "intent_sha256", subject.INTENT),
    ):
        if value and not _SHA256.fullmatch(value):
            read.refuse(malformed, where, f"{name} is not a lowercase SHA-256")
    read.found.extend(
        _selection_refusals(server, clients, vlan_id, prefix_length, switch, gateway)
    )
    if attempt_id and marker and marker != MARKER_PREFIX + attempt_id:
        read.refuse(
            RefusalKind.MISMATCH, subject.MARKER, "marker is not COLD_HTTP_<attempt>"
        )
    if server.ipv4 and url and url != f"http://{server.ipv4}/":
        read.refuse(RefusalKind.MISMATCH, subject.URL, "url is not http://<server>/")
    expected_budget = {
        "max_operations": proposal.max_operations,
        "max_seconds": proposal.max_seconds,
        "reserve_operations": proposal.reserve_operations,
        "reserve_seconds": proposal.reserve_seconds,
    }
    for key, value in budget.items():
        if value is not None and value != expected_budget[key]:
            read.refuse(
                RefusalKind.NOT_PERMITTED,
                subject.BUDGET,
                f"{key} {value} is not the frozen proposal {expected_budget[key]}; "
                "a different ceiling is a revised proposal",
            )
    if process_id is not None and process_id <= 0:
        read.refuse(malformed, subject.PROCESS, "process_id is not positive")
    if raw.get("exclusive_disposable_lab") is False:
        read.refuse(
            RefusalKind.NOT_PERMITTED,
            subject.LABORATORY,
            "an exclusive disposable laboratory was not accepted",
        )
    if raw.get("local_fence_limitation_accepted") is False:
        read.refuse(
            RefusalKind.NOT_PERMITTED,
            subject.LABORATORY,
            "the local, non-in-band receiver fence limitation was not accepted",
        )
    if read.found:
        return None, tuple(read.found)
    return (
        ColdHttpGrant(
            authorization_id=authorization_id,
            attempt_id=attempt_id,
            sha=sha,
            tree=tree,
            build=build,
            channel=channel,
            deployment_id=deployment_id,
            manifest_hash=manifest_hash,
            physical_topology_hash=topology_hash,
            intent_sha256=intent_sha256,
            switch=switch,
            switch_model=switch_model,
            vlan_id=int(vlan_id or 0),
            prefix_length=int(prefix_length or 0),
            gateway=gateway,
            server=server,
            clients=clients,
            marker=marker,
            url=url,
            max_operations=int(budget["max_operations"] or 0),
            max_seconds=int(budget["max_seconds"] or 0),
            reserve_operations=int(budget["reserve_operations"] or 0),
            reserve_seconds=int(budget["reserve_seconds"] or 0),
            process_id=int(process_id or 0),
            process_path=process_path,
            process_incarnation=incarnation,
            exclusive_disposable_lab=lab,
            local_fence_limitation_accepted=fence,
        ),
        (),
    )


def _selection_refusals(
    server: GrantedEndpoint,
    clients: Sequence[GrantedEndpoint],
    vlan_id: int | None,
    prefix_length: int | None,
    switch: str,
    gateway: str,
) -> list[AcceptanceRefusal]:
    """Check that the granted names, ports and addresses form one segment."""
    subject = AcceptanceSubject.SELECTION
    found: list[AcceptanceRefusal] = []
    if len(clients) != 2:
        found.append(
            acceptance_refusal(
                RefusalKind.MISMATCH, subject, "exactly two clients are granted"
            )
        )
    if vlan_id is not None and not 1 <= vlan_id <= 4094:
        found.append(acceptance_refusal(RefusalKind.MALFORMED, subject, "vlan_id"))
    if prefix_length is not None and not 8 <= prefix_length <= 30:
        found.append(
            acceptance_refusal(RefusalKind.MALFORMED, subject, "prefix_length")
        )
        return found
    endpoints = (server, *clients)
    if not all(item.name for item in endpoints) or prefix_length is None:
        return found
    names = [item.name for item in endpoints] + [switch]
    ports = [item.switch_port for item in endpoints]
    addresses = [item.ipv4 for item in endpoints]
    if len(set(names)) != len(names):
        found.append(acceptance_refusal(RefusalKind.MALFORMED, subject, "names repeat"))
    if len(set(ports)) != len(ports):
        found.append(acceptance_refusal(RefusalKind.MALFORMED, subject, "ports repeat"))
    if len(set(addresses)) != len(addresses):
        found.append(
            acceptance_refusal(RefusalKind.MALFORMED, subject, "addresses repeat")
        )
    networks = set()
    for item in endpoints:
        try:
            interface = ipaddress.IPv4Interface(f"{item.ipv4}/{prefix_length}")
        except ValueError:
            found.append(
                acceptance_refusal(RefusalKind.MALFORMED, subject, f"ipv4 {item.name}")
            )
            continue
        network = interface.network
        if interface.ip in (network.network_address, network.broadcast_address):
            found.append(
                acceptance_refusal(
                    RefusalKind.MALFORMED, subject, f"ipv4 {item.name} is not a host"
                )
            )
        networks.add(network)
    if len(networks) > 1:
        found.append(
            acceptance_refusal(
                RefusalKind.MISMATCH, subject, "endpoints are not one segment"
            )
        )
    if gateway and len(networks) == 1:
        try:
            gateway_ip = ipaddress.IPv4Address(gateway)
        except ValueError:
            gateway_ip = None
        network = next(iter(networks))
        if (
            gateway_ip is None
            or gateway_ip not in network
            or gateway_ip in (network.network_address, network.broadcast_address)
            or gateway in addresses
        ):
            found.append(
                acceptance_refusal(
                    RefusalKind.MALFORMED,
                    subject,
                    "gateway is not a free host address of the segment",
                )
            )
    return found


def repository_acceptance_refusals(
    found: Sequence[QualificationRefusal],
) -> tuple[AcceptanceRefusal, ...]:
    """Carry the shared repository rule's refusals under this envelope's type."""
    return tuple(
        acceptance_refusal(
            item.kind,
            AcceptanceSubject.REPOSITORY,
            f"{item.subject.value}:{item.detail}",
        )
        for item in found
    )


def process_refusals(
    grant: ColdHttpGrant, observed: DiagnosticLifecycleObservation
) -> tuple[AcceptanceRefusal, ...]:
    """Bind the attempt to one exact Packet Tracer incarnation and a quiet mailbox.

    Read-only and pre-transport. A PID and a path name a slot the operating
    system reuses; the creation identity is what names the process, so it is
    compared exactly and an unobserved one is never a match.
    """
    process = AcceptanceSubject.PROCESS
    if observed.error:
        return (acceptance_refusal(RefusalKind.UNOBSERVABLE, process, observed.error),)
    found: list[AcceptanceRefusal] = []
    if (observed.process_id, observed.process_path) != (
        grant.process_id,
        grant.process_path,
    ):
        found.append(
            acceptance_refusal(RefusalKind.MISMATCH, process, "PID or path differs")
        )
    if not observed.process_incarnation:
        found.append(
            acceptance_refusal(
                RefusalKind.UNOBSERVABLE, process, "creation identity unobserved"
            )
        )
    elif observed.process_incarnation != grant.process_incarnation:
        found.append(
            acceptance_refusal(RefusalKind.MISMATCH, process, "incarnation differs")
        )
    versions = tuple(
        value for value in (observed.product_version, observed.file_version) if value
    )
    if grant.build not in versions:
        found.append(
            acceptance_refusal(
                RefusalKind.MISMATCH if versions else RefusalKind.UNOBSERVABLE,
                process,
                "the process does not report the granted build",
            )
        )
    if observed.mailbox_entries:
        found.append(
            acceptance_refusal(
                RefusalKind.NOT_PERMITTED,
                AcceptanceSubject.MAILBOX,
                "stale command artifacts: " + ", ".join(observed.mailbox_entries[:8]),
            )
        )
    return tuple(found)


def manifest_refusals(
    grant: ColdHttpGrant,
    *,
    deployment_id: str,
    semantic_hash: str,
    physical_topology_hash: str,
    backend_version: str,
) -> tuple[AcceptanceRefusal, ...]:
    """Require the stored manifest to be exactly the granted one."""
    found: list[AcceptanceRefusal] = []
    for observed, expected, name in (
        (deployment_id, grant.deployment_id, "deployment_id"),
        (semantic_hash, grant.manifest_hash, "manifest_hash"),
        (physical_topology_hash, grant.physical_topology_hash, "physical_topology"),
        (backend_version, grant.build, "backend_version"),
    ):
        if observed != expected:
            found.append(
                acceptance_refusal(
                    RefusalKind.MISMATCH, AcceptanceSubject.MANIFEST, name
                )
            )
    return tuple(found)


# -- the compiled closure -------------------------------------------------------


def _e5_signature(item: EffectClosureAction) -> tuple[object, ...]:
    if item.action_type == "create_vlan":
        return (item.action_type, item.device_name, item.vlan_id)
    if item.action_type == "configure_access_port":
        return (
            item.action_type,
            item.device_name,
            item.interface,
            item.vlan_id,
            item.parameters.get("voice_vlan_id"),
        )
    if item.action_type == "set_endpoint_static":
        return (
            item.action_type,
            item.device_name,
            item.interface,
            item.ipv4,
            item.netmask,
            item.gateway,
            str(item.parameters.get("dns_server") or ""),
        )
    return (item.action_type, item.device_name)


def expected_e5_signatures(grant: ColdHttpGrant) -> list[tuple[object, ...]]:
    """Return the seven E5 effects this grant authorizes, as signatures."""
    vlan = [("create_vlan", grant.switch, grant.vlan_id)]
    ports = [
        ("configure_access_port", grant.switch, item.switch_port, grant.vlan_id, None)
        for item in grant.endpoints
    ]
    # No DNS service is in scope, so no endpoint is given a DNS server.
    addresses = [
        (
            "set_endpoint_static",
            item.name,
            item.interface,
            item.ipv4,
            grant.netmask,
            grant.gateway,
            "",
        )
        for item in grant.endpoints
    ]
    return sorted(vlan + ports + addresses, key=repr)


def effect_scope_findings(
    grant: ColdHttpGrant, closure: ServiceEffectClosure
) -> tuple[str, ...]:
    """Name every way the compiled closure differs from the granted one.

    Called by the product immediately before its first effect. An empty
    answer admits the closure; anything else refuses the run with nothing
    dispatched. A material change needs a revised proposal and grant, never
    an extra action hidden inside the budget.
    """
    found: list[str] = []
    identity = (
        (closure.deployment_id, grant.deployment_id, "deployment_id"),
        (closure.manifest_hash, grant.manifest_hash, "manifest_hash"),
        (
            closure.physical_topology_hash,
            grant.physical_topology_hash,
            "physical_topology_hash",
        ),
        (closure.transport, grant.channel, "transport"),
        (closure.observed_build, grant.build, "observed_build"),
        (closure.source_sha, grant.sha, "source_sha"),
    )
    for observed, expected, name in identity:
        if observed != expected:
            found.append(f"{name}_mismatch")
    if not closure.source_tree:
        found.append("source_tree_absent")
    elif closure.source_tree != grant.tree:
        found.append("source_tree_mismatch")
    if closure.source_dirty:
        found.append("source_tree_dirty")
    if closure.retained:
        found.append("retained_e5_actions:" + ",".join(closure.retained))
    observed_e5 = sorted((_e5_signature(item) for item in closure.e5_actions), key=repr)
    if observed_e5 != expected_e5_signatures(grant):
        found.append("e5_closure_differs_from_grant")
    if sorted(item.action_id for item in closure.e5_actions) != sorted(closure.mutated):
        found.append("e5_closure_does_not_describe_the_mutated_scope")
    unexpected_exclusions = sorted(
        item.action_id
        for item in closure.excluded_actions
        if item.action_type != "configure_hostname"
    )
    if unexpected_exclusions:
        found.append("non_hostname_exclusions:" + ",".join(unexpected_exclusions))
    found.extend(_service_findings(grant, closure))
    found.extend(_check_findings(grant, closure))
    return tuple(found)


def _service_findings(grant: ColdHttpGrant, closure: ServiceEffectClosure) -> list[str]:
    found: list[str] = []
    kinds = sorted(item.action_type for item in closure.service_actions)
    if kinds != ["enable_http_service", "set_http_content"]:
        found.append("e6_actions_are_not_http_enable_and_content:" + ",".join(kinds))
    for item in closure.service_actions:
        if item.device_name != grant.server.name:
            found.append(f"e6_action_off_server:{item.action_id}")
        if item.parameters.get("service_type") != "http":
            found.append(f"e6_action_not_http:{item.action_id}")
        if item.action_type == "set_http_content":
            content = str(item.parameters.get("content") or "")
            if grant.marker not in content:
                found.append("page_content_lacks_attempt_marker")
    return found


def _check_findings(grant: ColdHttpGrant, closure: ServiceEffectClosure) -> list[str]:
    found: list[str] = []
    fetches = [item for item in closure.checks if item.kind == "http_fetch"]
    direct = [
        item
        for item in closure.checks
        if item.kind == "direct_service_state" and item.evidence_kind == "direct_state"
    ]
    others = [item for item in closure.checks if item not in fetches + direct]
    if others:
        found.append(
            "unexpected_checks:" + ",".join(sorted(item.kind for item in others))
        )
    if len(direct) != 1:
        found.append(f"direct_http_state_checks:{len(direct)}")
    for item in direct:
        if item.host_device_name != grant.server.name or (
            item.expected.get("service_type") != "http"
        ):
            found.append(
                f"direct_check_not_the_server_http_state:{item.expectation_id}"
            )
    clients = sorted(item.client_device_name for item in fetches)
    if clients != sorted(item.name for item in grant.clients):
        found.append("http_fetch_clients_differ_from_grant")
    for item in fetches:
        expected = item.expected
        if item.host_device_name != grant.server.name:
            found.append(f"http_fetch_host_mismatch:{item.expectation_id}")
        if expected.get("hostname"):
            found.append(f"http_fetch_by_hostname:{item.expectation_id}")
        if str(expected.get("scheme") or "http") != "http":
            found.append(f"http_fetch_not_http:{item.expectation_id}")
        if expected.get("address") != grant.server.ipv4:
            found.append(f"http_fetch_not_by_server_ip:{item.expectation_id}")
        if expected.get("marker") != grant.marker:
            found.append(f"http_fetch_marker_mismatch:{item.expectation_id}")
    return found


# -- the record -----------------------------------------------------------------


class ClientAcceptance(BaseModel):
    """One client's first request, as the envelope observed and judged it."""

    client: str
    expectation_id: str = ""
    switch_port: str = ""
    first_dispatch_seq: int | None = None
    #: 1 for the client the product tested first. PC1's request may change
    #: shared network state before PC2's; the order is reported, not assumed.
    request_order: int | None = None
    dispatches: int = 0
    start_answer: str = ""
    content_before: str | None = None
    selected_url: str = ""
    selected_url_is_input: bool = False
    go_result: bool | None = None
    go_result_type: str = ""
    owner_device: str = ""
    owner_read: bool = False
    client_mode: str = ""
    status: str = ""
    observation: str = ""
    cause: str = ""
    inspections_performed: int = 0
    marker_observations: list[bool] = Field(default_factory=list)
    trace: list[dict[str, Any]] = Field(default_factory=list)
    release_outcome: str = ""
    release_answer: str = ""
    release_dispatches: int = 0
    findings: list[str] = Field(default_factory=list)
    accepted: bool = False


class AcceptanceBudget(BaseModel):
    """What the attempt was allowed and what it spent, dispatch by dispatch."""

    max_operations: int
    max_seconds: int
    reserve_operations: int
    reserve_seconds: int
    arithmetic: dict[str, int] = Field(default_factory=dict)
    used_operations: int = 0
    refused_calls: int = 0
    reserve_used: int = 0
    elapsed_seconds: float = 0.0
    local_observation_seconds: float = 0.0
    entries: list[OperationEntry] = Field(default_factory=list)


class CampaignOutcome(StrEnum):
    """How the attempt ended as a campaign, independently of HTTP acceptance."""

    __str__ = Enum.__str__

    REFUSED = "refused"
    STOPPED = "stopped"
    COMPLETED = "completed"


class ColdHttpAcceptanceEnvelope(BaseModel):
    """The immutable acceptance record of one attempt.

    It references the product run by path and SHA-256 and never rewrites it.
    Admission and stop facts, observed identities, the ledger, the start and
    end observations and each client's first request are kept as observed;
    anything the attempt did not observe stays absent rather than invented.
    """

    schema_version: int = ENVELOPE_SCHEMA_VERSION
    attempt_id: str
    authorization_id: str = ""
    started_at: datetime
    completed_at: datetime | None = None
    grant: dict[str, Any] = Field(default_factory=dict)
    grant_sha256: str = ""
    product_input: dict[str, str] = Field(default_factory=dict)
    admission: list[AcceptanceRefusal] = Field(default_factory=list)
    checks: list[str] = Field(default_factory=list)
    isolation: dict[str, str] = Field(default_factory=dict)
    runtime: dict[str, str] = Field(default_factory=dict)
    source: dict[str, Any] = Field(default_factory=dict)
    process_preflight: dict[str, Any] = Field(default_factory=dict)
    process_postflight: dict[str, Any] = Field(default_factory=dict)
    continuity: list[str] = Field(default_factory=list)
    channel: dict[str, str] = Field(default_factory=dict)
    campaign: dict[str, Any] = Field(default_factory=dict)
    manifest: dict[str, str] = Field(default_factory=dict)
    closure: ServiceEffectClosure | None = None
    closure_findings: list[str] = Field(default_factory=list)
    product: dict[str, Any] = Field(default_factory=dict)
    readiness: list[dict[str, Any]] = Field(default_factory=list)
    clients: list[ClientAcceptance] = Field(default_factory=list)
    ordering: list[str] = Field(default_factory=list)
    budget: AcceptanceBudget | None = None
    primary_failure: str = ""
    release_failures: list[str] = Field(default_factory=list)
    persistence_failures: list[str] = Field(default_factory=list)
    postflight_failures: list[str] = Field(default_factory=list)
    campaign_outcome: CampaignOutcome = CampaignOutcome.REFUSED
    http_accepted: bool = False
    reasons: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


#: What every envelope says about itself, whatever its outcome.
ENVELOPE_LIMITATIONS = (
    "effect_gate_is_local_and_not_an_in_band_receiver_fence",
    "exclusive_disposable_laboratory_accepted_by_grant",
    "no_universal_exclusion_of_replacement_processes",
    "no_exactly_once_execution_claim",
    "client_release_is_not_workspace_restoration",
    "product_topology_and_server_page_remain_by_design",
    "pc1_may_affect_shared_network_state_before_pc2",
)
