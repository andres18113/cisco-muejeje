"""The scalable HTTP-by-IP acceptance profile: grant, derived scope and cost.

Grant schema 1 stays the legacy two-client smoke profile with its frozen
1,015 / 420 / 2 / 40 proposal; nothing here reads or reinterprets it. Schema 2
is the scalable profile. Its grant names the attempt, the source, the process,
the deployment and manifest, the intent digest, the attempt marker, the exact
selected client and server names, the digest of the derived scope, and a budget
that must equal the derived proposal. Everything else -- placements, paths,
readiness groups, URLs, E5 and E6 signatures and the cost -- is derived from
the persisted manifest and the compiled plans through the product's own
effect closure, and bound to the grant by the scope digest.

Every rule here is a pure function over values and fails closed: a missing,
duplicate, foreign or unobservable identity is a refusal, never a default.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from typing import Any

from ....shared.utils import safe_name_component
from .cold_http_acceptance import (
    ACCEPTANCE_CHANNEL,
    MARKER_PREFIX,
    AcceptanceRefusal,
    AcceptanceSubject,
    acceptance_refusal,
)
from .service_entry import ServiceEffectClosure
from .service_qualification import (
    RefusalKind,
    is_exact_packet_tracer_build,
    is_full_sha,
)

SCALABLE_GRANT_SCHEMA_VERSION = 2
SCALABLE_PROFILE = "http_by_ip_scalable_v1"
MAX_SELECTED_CLIENTS = 1000
_HEX_TOKEN = re.compile(r"[0-9a-f]{32}")
_SHA256 = re.compile(r"[0-9a-f]{64}")

#: The only E5 and E6 action types, checks and path shapes the profile admits.
SCALABLE_E5_ACTION_TYPES = frozenset(
    {"create_vlan", "configure_access_port", "set_endpoint_static"}
)
SCALABLE_E6_ACTION_TYPES = frozenset({"enable_http_service", "set_http_content"})
SCALABLE_PATH_KINDS = frozenset({"local_access", "l2_multi_access"})

#: What every scalable envelope says about itself, whatever its outcome.
SCALABLE_ENVELOPE_LIMITATIONS = (
    "effect_gate_is_local_and_not_an_in_band_receiver_fence",
    "exclusive_disposable_laboratory_accepted_by_grant",
    "no_universal_exclusion_of_replacement_processes",
    "no_exactly_once_execution_claim",
    "client_release_is_not_workspace_restoration",
    "product_topology_and_server_page_remain_by_design",
    "clients_run_sequentially_and_may_affect_shared_state_before_the_next",
    "trunks_transit_vlans_and_gateways_not_configured_by_acceptance",
    "routed_paths_are_not_supported_by_this_profile",
)


# -- the grant ----------------------------------------------------------------------


@dataclass(frozen=True)
class ScalableHttpGrant:
    """An operator's exact authorization for one scalable attempt, as parsed.

    It carries the same identity fields the legacy grant carries, under the
    same names, so the shared process, manifest and repository rules decide
    it unchanged.
    """

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
    server_names: tuple[str, ...]
    client_names: tuple[str, ...]
    scope_sha256: str
    marker: str
    max_operations: int
    max_seconds: int
    reserve_operations: int
    reserve_seconds: int
    process_id: int
    process_path: str
    process_incarnation: str
    exclusive_disposable_lab: bool
    local_fence_limitation_accepted: bool
    profile: str = SCALABLE_PROFILE
    schema_version: int = SCALABLE_GRANT_SCHEMA_VERSION

    @property
    def run_label(self) -> str:
        """Return the display label the product run carries for this attempt."""
        return f"scalable-http-acceptance:{self.attempt_id}"


def _names(
    raw: Mapping[str, Any], key: str, found: list[AcceptanceRefusal]
) -> tuple[str, ...]:
    value = raw.get(key)
    subject = AcceptanceSubject.SELECTION
    if value is None:
        found.append(acceptance_refusal(RefusalKind.MISSING, subject, key))
        return ()
    if not isinstance(value, list) or not value:
        found.append(
            acceptance_refusal(RefusalKind.MALFORMED, subject, f"{key} is not a list")
        )
        return ()
    names: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip() or item != item.strip():
            found.append(
                acceptance_refusal(
                    RefusalKind.MALFORMED, subject, f"{key} holds a non-name"
                )
            )
            return ()
        names.append(item)
    duplicates = sorted(name for name, count in Counter(names).items() if count > 1)
    if duplicates:
        found.append(
            acceptance_refusal(
                RefusalKind.MALFORMED,
                subject,
                f"{key} repeats: " + ", ".join(duplicates[:8]),
            )
        )
        return ()
    return tuple(names)


def parse_scalable_grant(
    raw: object,
) -> tuple[ScalableHttpGrant | None, tuple[AcceptanceRefusal, ...]]:
    """Parse one schema 2 grant; every field is required and checked."""
    if not isinstance(raw, Mapping):
        return None, (
            acceptance_refusal(
                RefusalKind.MALFORMED, AcceptanceSubject.GRANT, "not a JSON object"
            ),
        )
    found: list[AcceptanceRefusal] = []
    subject = AcceptanceSubject

    def text(key: str, where: AcceptanceSubject) -> str:
        value = raw.get(key)
        if value is None:
            found.append(acceptance_refusal(RefusalKind.MISSING, where, key))
            return ""
        if not isinstance(value, str) or not value.strip() or value != value.strip():
            found.append(
                acceptance_refusal(
                    RefusalKind.MALFORMED, where, f"{key} is not a clean string"
                )
            )
            return ""
        return value

    def integer(key: str, where: AcceptanceSubject) -> int | None:
        value = raw.get(key)
        if value is None:
            found.append(acceptance_refusal(RefusalKind.MISSING, where, key))
            return None
        if isinstance(value, bool) or not isinstance(value, int):
            found.append(
                acceptance_refusal(
                    RefusalKind.MALFORMED, where, f"{key} is not an integer"
                )
            )
            return None
        return value

    def flag(key: str) -> bool:
        value = raw.get(key)
        if value is None:
            found.append(
                acceptance_refusal(RefusalKind.MISSING, subject.LABORATORY, key)
            )
            return False
        if not isinstance(value, bool):
            found.append(
                acceptance_refusal(
                    RefusalKind.MALFORMED, subject.LABORATORY, f"{key} is not a boolean"
                )
            )
            return False
        if value is False:
            found.append(
                acceptance_refusal(
                    RefusalKind.NOT_PERMITTED, subject.LABORATORY, f"{key} is false"
                )
            )
        return value

    version = integer("schema_version", subject.GRANT)
    if version is not None and version != SCALABLE_GRANT_SCHEMA_VERSION:
        found.append(
            acceptance_refusal(
                RefusalKind.MISMATCH, subject.GRANT, f"schema_version {version}"
            )
        )
    profile = text("profile", subject.GRANT)
    if profile and profile != SCALABLE_PROFILE:
        found.append(
            acceptance_refusal(
                RefusalKind.MISMATCH, subject.GRANT, f"profile {profile!r}"
            )
        )
    authorization_id = text("authorization_id", subject.AUTHORIZATION_ID)
    attempt_id = text("attempt_id", subject.ATTEMPT)
    sha = text("sha", subject.SOURCE)
    tree = text("tree", subject.SOURCE)
    build = text("build", subject.BUILD)
    channel = text("channel", subject.CHANNEL)
    deployment_id = text("deployment_id", subject.DEPLOYMENT)
    manifest_hash = text("manifest_hash", subject.MANIFEST)
    topology_hash = text("physical_topology_hash", subject.MANIFEST)
    intent_sha256 = text("intent_sha256", subject.INTENT)
    scope_sha256 = text("scope_sha256", subject.SELECTION)
    marker = text("marker", subject.MARKER)
    servers = _names(raw, "servers", found)
    clients = _names(raw, "clients", found)
    budget = {
        key: integer(key, subject.BUDGET)
        for key in (
            "max_operations",
            "max_seconds",
            "reserve_operations",
            "reserve_seconds",
        )
    }
    process_id = integer("process_id", subject.PROCESS)
    process_path = text("process_path", subject.PROCESS)
    incarnation = text("process_incarnation", subject.PROCESS)
    lab = flag("exclusive_disposable_lab")
    fence = flag("local_fence_limitation_accepted")

    malformed = RefusalKind.MALFORMED
    if authorization_id and len(authorization_id) > 128:
        found.append(
            acceptance_refusal(malformed, subject.AUTHORIZATION_ID, "longer than 128")
        )
    if attempt_id and not _HEX_TOKEN.fullmatch(attempt_id):
        found.append(
            acceptance_refusal(
                malformed, subject.ATTEMPT, "not 32 lowercase hex characters"
            )
        )
    for value, name in ((sha, "sha"), (tree, "tree")):
        if value and not is_full_sha(value):
            found.append(
                acceptance_refusal(
                    malformed, subject.SOURCE, f"{name} is not a full SHA"
                )
            )
    if build and not is_exact_packet_tracer_build(build):
        found.append(
            acceptance_refusal(
                malformed, subject.BUILD, "not one exact four-part build"
            )
        )
    if channel and channel != ACCEPTANCE_CHANNEL:
        found.append(
            acceptance_refusal(
                RefusalKind.NOT_PERMITTED,
                subject.CHANNEL,
                f"only the {ACCEPTANCE_CHANNEL!r} channel is bound by this envelope",
            )
        )
    if deployment_id and safe_name_component(deployment_id, "") != deployment_id:
        found.append(
            acceptance_refusal(malformed, subject.DEPLOYMENT, "not a safe store name")
        )
    for value, name, where in (
        (manifest_hash, "manifest_hash", subject.MANIFEST),
        (topology_hash, "physical_topology_hash", subject.MANIFEST),
        (intent_sha256, "intent_sha256", subject.INTENT),
        (scope_sha256, "scope_sha256", subject.SELECTION),
    ):
        if value and not _SHA256.fullmatch(value):
            found.append(
                acceptance_refusal(
                    malformed, where, f"{name} is not a lowercase SHA-256"
                )
            )
    if attempt_id and marker and marker != MARKER_PREFIX + attempt_id:
        found.append(
            acceptance_refusal(
                RefusalKind.MISMATCH,
                subject.MARKER,
                "marker is not COLD_HTTP_<attempt>",
            )
        )
    if clients and len(clients) > MAX_SELECTED_CLIENTS:
        found.append(
            acceptance_refusal(
                RefusalKind.NOT_PERMITTED,
                subject.SELECTION,
                f"more than {MAX_SELECTED_CLIENTS} selected clients",
            )
        )
    if set(servers) & set(clients):
        found.append(
            acceptance_refusal(
                malformed, subject.SELECTION, "a server is also a client"
            )
        )
    for key, value in budget.items():
        if value is not None and value <= 0:
            found.append(
                acceptance_refusal(malformed, subject.BUDGET, f"{key} is not positive")
            )
    if process_id is not None and process_id <= 0:
        found.append(
            acceptance_refusal(malformed, subject.PROCESS, "process_id is not positive")
        )
    if found:
        return None, tuple(found)
    return (
        ScalableHttpGrant(
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
            server_names=servers,
            client_names=clients,
            scope_sha256=scope_sha256,
            marker=marker,
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


# -- the cost model -----------------------------------------------------------------


@dataclass(frozen=True)
class CostProfile:
    """The worst-case cost of each bounded step, as the executed code bounds it.

    Operations count Script Engine dispatches at the ledger, nested calls
    included. Seconds are upper bounds from the steps' own windows and call
    timeouts. Every value names the product constant it comes from, and a test
    compares them with the constants the runtimes use.
    """

    #: 90 s IOS boot window polled every 0.25 s, first read included.
    ios_boot_reads: int = 361
    ios_boot_seconds: float = 93.0
    #: 5 s VLAN readback window at 0.25 s.
    vlan_readback_reads: int = 21
    vlan_readback_seconds: float = 8.0
    access_port_readback_reads: int = 1
    access_port_readback_seconds: float = 6.0
    #: 30 s endpoint readback window at 0.25 s.
    endpoint_readback_reads: int = 121
    endpoint_readback_seconds: float = 33.0
    #: MAX_ENDPOINT_CALLS_PER_SEND of the E5 runtime.
    endpoint_calls_per_send: int = 64
    #: One readiness episode's enforced call allowance: 30 samples at a
    #: six-call share, plus the auxiliary read, inside a 30 s window. One
    #: sample may borrow up to 16 of it to finish a paginated table; together
    #: they never exceed it. Narrowing may add one more episode.
    readiness_sample_reads: int = 30 * 6 + 1
    readiness_episode_seconds: float = 30.0
    readiness_episodes_per_group: int = 2
    #: One continuity episode: at most 31 rounds at a six-call share per
    #: switch reading (one reading may borrow up to 16), inside a 30 s window.
    #: Narrowing may add one more.
    continuity_rounds: int = 31
    continuity_calls_per_reading: int = 6
    continuity_episode_seconds: float = 30.0
    continuity_episodes_per_group: int = 2
    #: E6: an enable batch and a content batch per server, one direct read.
    e6_batches_per_server: int = 2
    e6_direct_reads_per_server: int = 1
    e6_seconds_per_server: float = 25.0
    #: One client: its start, at most 33 inspections (8 s at 0.25 s), its
    #: release from the reserve.
    client_ordinary_reads: int = 1 + 33
    client_ordinary_seconds: float = 16.0
    client_release_reads: int = 1
    client_release_seconds: float = 3.0
    #: Admission: the environment read, one targeted inventory read and one
    #: drift read per endpoint in the closure.
    admission_fixed_reads: int = 2
    admission_fixed_seconds: float = 20.0
    drift_read_seconds: float = 3.0
    #: Local reads that cost time and no operation: the lifecycle pairing
    #: before and after the run, and one receiver reading per dispatch.
    lifecycle_seconds: float = 60.0
    receiver_check_seconds: float = 0.05
    #: Reserved finalization: the in-flight release, the postflight pairing
    #: and local completion.
    reserve_seconds: int = 40


COST_PROFILE = CostProfile()


@dataclass(frozen=True)
class CostModel:
    """The preflight cost of one derived scope, line by line."""

    operation_lines: tuple[tuple[str, int], ...]
    seconds_lines: tuple[tuple[str, float], ...]
    polling_windows: tuple[tuple[str, float], ...]
    reserve_operations: int
    reserve_seconds: int

    @property
    def ordinary_operations(self) -> int:
        """Return the ordinary worst case, releases excluded."""
        return sum(value for _, value in self.operation_lines)

    @property
    def ordinary_seconds(self) -> float:
        """Return the ordinary wall-clock upper bound."""
        return sum(value for _, value in self.seconds_lines)

    @property
    def max_operations(self) -> int:
        """Return the operation ceiling a grant must name."""
        return self.ordinary_operations + self.reserve_operations

    @property
    def max_seconds(self) -> int:
        """Return the time ceiling a grant must name."""
        return math.ceil(self.ordinary_seconds) + self.reserve_seconds

    def document(self) -> dict[str, Any]:
        """Return the JSON-ready model the scope digest covers."""
        return {
            "operation_lines": [list(item) for item in self.operation_lines],
            "seconds_lines": [
                [key, round(value, 3)] for key, value in self.seconds_lines
            ],
            "polling_windows": [
                [key, round(value, 3)] for key, value in self.polling_windows
            ],
            "reserve_operations": self.reserve_operations,
            "reserve_seconds": self.reserve_seconds,
            "max_operations": self.max_operations,
            "max_seconds": self.max_seconds,
        }


# -- the derived scope --------------------------------------------------------------


@dataclass(frozen=True)
class ScopedServer:
    """One selected server and what the closure does on it."""

    name: str
    ipv4: str
    service_actions: tuple[str, ...]
    direct_check: str


@dataclass(frozen=True)
class ScopedClient:
    """One selected client, its one request and every group it waits on."""

    name: str
    expectation_id: str
    server: str
    url: str
    vlan_id: int
    switch: str
    port: str
    server_switch: str
    server_port: str
    groups: tuple[str, ...]
    path_kind: str


@dataclass(frozen=True)
class ReadinessGroupScope:
    """One readiness group, as the closure named it."""

    key: str
    kind: str
    vlan_id: int
    switches: tuple[str, ...]
    interfaces: tuple[str, ...]
    dependents: tuple[str, ...]
    #: Each compiled trunk link of a continuity group as its two ends.
    links: tuple[str, ...] = ()


@dataclass(frozen=True)
class AcceptanceScope:
    """Everything a scalable attempt may do and must show, derived not granted."""

    deployment_id: str
    manifest_hash: str
    physical_topology_hash: str
    configuration_semantic_hash: str
    service_semantic_hash: str
    servers: tuple[ScopedServer, ...]
    clients: tuple[ScopedClient, ...]
    groups: tuple[ReadinessGroupScope, ...]
    e5_signatures: tuple[tuple[str, ...], ...]
    e6_signatures: tuple[tuple[str, ...], ...]
    cost: CostModel
    profile: str = SCALABLE_PROFILE
    _by_client: dict[str, ScopedClient] = field(
        default_factory=dict, compare=False, repr=False
    )

    def client(self, name: str) -> ScopedClient | None:
        """Return one selected client by deployed name."""
        if not self._by_client:
            self._by_client.update({item.name: item for item in self.clients})
        return self._by_client.get(name)

    def document(self) -> dict[str, Any]:
        """Return the canonical JSON-ready scope the digest covers."""
        return {
            "profile": self.profile,
            "deployment_id": self.deployment_id,
            "manifest_hash": self.manifest_hash,
            "physical_topology_hash": self.physical_topology_hash,
            "configuration_semantic_hash": self.configuration_semantic_hash,
            "service_semantic_hash": self.service_semantic_hash,
            "servers": [asdict(item) for item in self.servers],
            "clients": [asdict(item) for item in self.clients],
            "groups": [asdict(item) for item in self.groups],
            "e5_signatures": [list(item) for item in self.e5_signatures],
            "e6_signatures": [list(item) for item in self.e6_signatures],
            "cost": self.cost.document(),
        }

    def digest(self) -> str:
        """Return the SHA-256 of the canonical scope document."""
        text = json.dumps(self.document(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _e5_signature(action) -> tuple[str, ...]:
    return (
        action.action_type,
        action.device_name,
        action.interface,
        "" if action.vlan_id is None else str(action.vlan_id),
        action.ipv4,
        action.netmask,
        action.gateway,
        str(action.parameters.get("dns_server") or ""),
    )


def derive_scope(
    closure: ServiceEffectClosure,
    marker: str,
    profile: CostProfile = COST_PROFILE,
) -> tuple[AcceptanceScope | None, tuple[str, ...]]:
    """Derive the scalable scope from one compiled closure, or name why not.

    The closure is what the product will do; this reads it and nothing else.
    Findings are about the closure itself: an action, a check or a path shape
    the profile does not admit, a request without exactly one client, a
    client with more than one request, or a server without its one direct
    check.
    """
    found: list[str] = []
    if closure.retained:
        found.append("retained_e5_actions:" + ",".join(closure.retained[:8]))
    for item in closure.e5_actions:
        if item.action_type not in SCALABLE_E5_ACTION_TYPES:
            found.append(f"e5_action_outside_profile:{item.action_id}")
        if item.action_type == "set_endpoint_static" and item.parameters.get(
            "dns_server"
        ):
            found.append(f"endpoint_dns_server:{item.action_id}")
    by_server_actions: dict[str, list[str]] = {}
    for item in closure.service_actions:
        if item.action_type not in SCALABLE_E6_ACTION_TYPES:
            found.append(f"e6_action_outside_profile:{item.action_id}")
        if item.parameters.get("service_type") != "http":
            found.append(f"e6_action_not_http:{item.action_id}")
        if item.action_type == "set_http_content" and marker not in str(
            item.parameters.get("content") or ""
        ):
            found.append(f"page_content_lacks_attempt_marker:{item.action_id}")
        by_server_actions.setdefault(item.device_name, []).append(item.action_id)
    fetches = [item for item in closure.checks if item.kind == "http_fetch"]
    directs = [
        item
        for item in closure.checks
        if item.kind == "direct_service_state" and item.evidence_kind == "direct_state"
    ]
    others = [item for item in closure.checks if item not in fetches + directs]
    if others:
        found.append(
            "unexpected_checks:" + ",".join(sorted({item.kind for item in others}))
        )
    direct_by_server: dict[str, list[str]] = {}
    for item in directs:
        if item.expected.get("service_type") != "http":
            found.append(f"direct_check_not_http:{item.expectation_id}")
        direct_by_server.setdefault(item.host_device_name, []).append(
            item.expectation_id
        )
    paths = {item.expectation_id: item for item in closure.paths}
    groups = tuple(
        ReadinessGroupScope(
            key=item.key,
            kind=item.kind,
            vlan_id=item.vlan_id,
            switches=tuple(item.switches),
            interfaces=tuple(item.interfaces),
            dependents=tuple(sorted(item.dependents)),
            links=tuple(sorted(item.links)),
        )
        for item in sorted(closure.readiness_groups, key=lambda group: group.key)
    )
    clients: list[ScopedClient] = []
    addresses: dict[str, set[str]] = {}
    seen: dict[str, int] = {}
    for item in fetches:
        expected = item.expected
        name = item.client_device_name
        if not name:
            found.append(f"http_fetch_without_client:{item.expectation_id}")
            continue
        seen[name] = seen.get(name, 0) + 1
        if expected.get("hostname"):
            found.append(f"http_fetch_by_hostname:{item.expectation_id}")
        if str(expected.get("scheme") or "http") != "http":
            found.append(f"http_fetch_not_http:{item.expectation_id}")
        if expected.get("marker") != marker:
            found.append(f"http_fetch_marker_mismatch:{item.expectation_id}")
        address = str(expected.get("address") or "")
        if not address:
            found.append(f"http_fetch_without_address:{item.expectation_id}")
        addresses.setdefault(item.host_device_name, set()).add(address)
        path = paths.get(item.expectation_id)
        if path is None or path.kind not in SCALABLE_PATH_KINDS:
            found.append(f"path_unobservable:{name}:{path.kind if path else 'absent'}")
            continue
        if not (path.client_switch and path.client_port and path.host_port):
            found.append(f"path_unplaced:{name}")
            continue
        clients.append(
            ScopedClient(
                name=name,
                expectation_id=item.expectation_id,
                server=item.host_device_name,
                url=f"http://{address}/",
                vlan_id=int(path.vlan_id or 0),
                switch=path.client_switch,
                port=path.client_port,
                server_switch=path.host_switch,
                server_port=path.host_port,
                groups=tuple(path.groups),
                path_kind=path.kind,
            )
        )
    repeated = sorted(name for name, count in seen.items() if count > 1)
    if repeated:
        found.append("clients_with_several_requests:" + ",".join(repeated[:8]))
    servers: list[ScopedServer] = []
    for name in sorted(set(by_server_actions) | set(addresses) | set(direct_by_server)):
        known = sorted(addresses.get(name, set()))
        if len(known) != 1:
            found.append(f"server_address_not_one:{name}")
        if len(direct_by_server.get(name, [])) != 1:
            found.append(
                f"server_direct_checks:{name}:{len(direct_by_server.get(name, []))}"
            )
        servers.append(
            ScopedServer(
                name=name,
                ipv4=known[0] if len(known) == 1 else "",
                service_actions=tuple(sorted(by_server_actions.get(name, []))),
                direct_check=(direct_by_server.get(name) or [""])[0],
            )
        )
    if not clients:
        found.append("no_selected_client")
    if found:
        return None, tuple(found)
    cost = derive_cost(
        closure,
        clients=len(clients),
        servers=len(servers),
        groups=groups,
        profile=profile,
    )
    return (
        AcceptanceScope(
            deployment_id=closure.deployment_id,
            manifest_hash=closure.manifest_hash,
            physical_topology_hash=closure.physical_topology_hash,
            configuration_semantic_hash=closure.configuration_semantic_hash,
            service_semantic_hash=closure.service_semantic_hash,
            servers=tuple(servers),
            clients=tuple(sorted(clients, key=lambda item: item.expectation_id)),
            groups=groups,
            e5_signatures=tuple(
                sorted(_e5_signature(item) for item in closure.e5_actions)
            ),
            e6_signatures=tuple(
                sorted(
                    (
                        item.action_type,
                        item.device_name,
                        str(item.parameters.get("service_type") or ""),
                        hashlib.sha256(
                            str(item.parameters.get("content") or "").encode("utf-8")
                        ).hexdigest(),
                    )
                    for item in closure.service_actions
                )
            ),
            cost=cost,
        ),
        (),
    )


def derive_cost(
    closure: ServiceEffectClosure,
    *,
    clients: int,
    servers: int,
    groups: Sequence[ReadinessGroupScope],
    profile: CostProfile = COST_PROFILE,
) -> CostModel:
    """Derive the preflight cost from what the closure will actually do."""
    e5 = closure.e5_actions
    ios = [
        item
        for item in e5
        if item.action_type in {"create_vlan", "configure_access_port"}
    ]
    ios_devices = {item.device_name for item in ios}
    ios_batches = {
        (item.device_name, int(item.parameters.get("phase") or 0)) for item in ios
    }
    vlans = sum(1 for item in e5 if item.action_type == "create_vlan")
    ports = sum(1 for item in e5 if item.action_type == "configure_access_port")
    endpoints = sum(1 for item in e5 if item.action_type == "set_endpoint_static")
    access = [item for item in groups if item.kind == "access"]
    continuity = [item for item in groups if item.kind == "trunk_continuity"]
    continuity_reads = sum(
        profile.continuity_episodes_per_group
        * profile.continuity_rounds
        * len(item.switches)
        * profile.continuity_calls_per_reading
        for item in continuity
    )
    operation_lines = (
        (
            "admission_environment_inventory_drift_reads",
            profile.admission_fixed_reads + endpoints,
        ),
        ("e5_ios_boot_waits", len(ios_devices) * profile.ios_boot_reads),
        ("e5_ios_phase_batches", len(ios_batches)),
        ("e5_endpoint_sends", math.ceil(endpoints / profile.endpoint_calls_per_send)),
        (
            "e5_readback",
            vlans * profile.vlan_readback_reads
            + ports * profile.access_port_readback_reads
            + endpoints * profile.endpoint_readback_reads,
        ),
        (
            "readiness_access_episodes",
            len(access)
            * profile.readiness_episodes_per_group
            * profile.readiness_sample_reads,
        ),
        ("readiness_continuity_episodes", continuity_reads),
        (
            "e6_batches_and_direct_reads",
            servers
            * (profile.e6_batches_per_server + profile.e6_direct_reads_per_server),
        ),
        ("client_starts_and_inspections", clients * profile.client_ordinary_reads),
    )
    ordinary = sum(value for _, value in operation_lines)
    reserve_operations = clients * profile.client_release_reads
    windows = (
        ("ios_boot", profile.ios_boot_seconds),
        ("vlan_readback", profile.vlan_readback_seconds),
        ("endpoint_readback", profile.endpoint_readback_seconds),
        ("readiness_episode", profile.readiness_episode_seconds),
        ("continuity_episode", profile.continuity_episode_seconds),
        ("client_request", profile.client_ordinary_seconds),
    )
    seconds_lines = (
        ("lifecycle_pairings", profile.lifecycle_seconds),
        (
            "receiver_readings",
            (ordinary + reserve_operations) * profile.receiver_check_seconds,
        ),
        (
            "admission_reads",
            profile.admission_fixed_seconds + endpoints * profile.drift_read_seconds,
        ),
        ("e5_ios_boot_waits", len(ios_devices) * profile.ios_boot_seconds),
        (
            "e5_readback",
            vlans * profile.vlan_readback_seconds
            + ports * profile.access_port_readback_seconds
            + endpoints * profile.endpoint_readback_seconds,
        ),
        (
            "readiness_episodes",
            len(access)
            * profile.readiness_episodes_per_group
            * profile.readiness_episode_seconds
            + len(continuity)
            * profile.continuity_episodes_per_group
            * profile.continuity_episode_seconds,
        ),
        ("e6_servers", servers * profile.e6_seconds_per_server),
        (
            "clients",
            clients
            * (profile.client_ordinary_seconds + profile.client_release_seconds),
        ),
    )
    return CostModel(
        operation_lines=operation_lines,
        seconds_lines=seconds_lines,
        polling_windows=windows,
        reserve_operations=reserve_operations,
        reserve_seconds=profile.reserve_seconds,
    )


def scope_findings(
    grant: ScalableHttpGrant,
    scope: AcceptanceScope,
) -> tuple[str, ...]:
    """Compare a grant with the scope derived for it; any difference refuses."""
    found: list[str] = []
    derived_clients = {item.name for item in scope.clients}
    granted_clients = set(grant.client_names)
    omitted = sorted(derived_clients - granted_clients)
    foreign = sorted(granted_clients - derived_clients)
    if omitted:
        found.append("selected_clients_not_granted:" + ",".join(omitted[:8]))
    if foreign:
        found.append("granted_clients_not_selected:" + ",".join(foreign[:8]))
    derived_servers = {item.name for item in scope.servers}
    if derived_servers != set(grant.server_names):
        found.append("servers_differ_from_grant")
    if scope.digest() != grant.scope_sha256:
        found.append("scope_digest_differs_from_grant")
    for name, granted, derived in (
        ("max_operations", grant.max_operations, scope.cost.max_operations),
        ("max_seconds", grant.max_seconds, scope.cost.max_seconds),
        ("reserve_operations", grant.reserve_operations, scope.cost.reserve_operations),
        ("reserve_seconds", grant.reserve_seconds, scope.cost.reserve_seconds),
    ):
        if granted != derived:
            found.append(f"budget_{name}_{granted}_is_not_derived_{derived}")
    return tuple(found)
