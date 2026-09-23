"""Which access ports one HTTP-family expectation needs forwarding, and where.

Operational readiness is a third question, separate from whether configuration
applied and from whether a service behaves. This module answers only the first
half of it and performs no I/O: given the compiled E5 configuration plan and the
E6 verification expectations, it says which switch/VLAN groups must forward, on
exactly which interfaces, and which expectation of which client depends on each
group.

The derivation source is the plan itself. `ConfigureAccessPort` names the
switch, the interface, the data VLAN and the semantic endpoints wired to that
port, and an expectation names its host and client endpoints. Nothing here reads
a device name pattern, an interface number ordering or a topology position: a
fixture called `...-PC-01` and a production endpoint are derived the same way,
because the only thing consulted is what the plan compiled.

An endpoint the plan never puts on an access port is not silently dropped from
the required set. It becomes a named unresolved endpoint, which makes the
requirement unsatisfiable and blocks its dependents, because a path whose ports
cannot be identified is not a path anybody observed.

A request between two access switches in one VLAN depends on three groups: the
client's access group, the server's access group and the trunk continuity of
the compiled component that joins them. Each group is observed once per
invocation and shared by every dependent that names it; a dependent is
admitted only when every group it names admits it. A request whose switches no
compiled component joins stays unplaced.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field

from ..models.service_plan import ServiceVerificationKind
from .service_path_closure import L2Component, PathTopology

#: The one configuration action type that places endpoints on a switch access
#: port. Compared as its wire value so this module stays independent of the
#: configuration action union while still refusing everything else.
ACCESS_PORT_ACTION_TYPE = "configure_access_port"

#: The verification kinds that make an HTTP request from a client. Each one
#: opens a TCP connection to the server through the access ports of both
#: endpoints, so each one needs the same forwarding statement. Matched by
#: exact identity: a kind that merely reads a getter is not in this set.
HTTP_REQUEST_KINDS: frozenset[ServiceVerificationKind] = frozenset(
    {
        ServiceVerificationKind.HTTP_FETCH,
        ServiceVerificationKind.HTTPS_FETCH,
        ServiceVerificationKind.HTTP_BY_HOSTNAME,
    }
)


@dataclass(frozen=True)
class AccessPortPlacement:
    """One switch access port as the configuration plan compiled it."""

    switch_device_id: str
    switch_device_name: str
    interface: str
    vlan_id: int
    endpoint_ids: tuple[str, ...]


@dataclass(frozen=True)
class ReadinessDependent:
    """One expectation that may not run before its group forwards."""

    expectation_id: str
    service_id: str
    kind: ServiceVerificationKind
    client_device_id: str
    host_device_id: str
    #: The interfaces this one expectation needs, which is its client's access
    #: port and its host's. Kept per dependent so a blocked group can report
    #: per-client coverage instead of one undifferentiated switch failure.
    interfaces: tuple[str, ...] = ()
    #: Endpoints of this expectation the plan puts on no access port. A
    #: non-empty tuple makes the dependent unsatisfiable on its own.
    unresolved_endpoint_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class AccessReadinessRequirement:
    """One switch/VLAN group to observe once, and everything that waits on it."""

    switch_device_id: str
    switch_device_name: str
    vlan_id: int
    interfaces: tuple[str, ...]
    dependents: tuple[ReadinessDependent, ...] = ()

    @property
    def key(self) -> tuple[str, int]:
        """Return the identity one grouped observation answers."""
        return (self.switch_device_id, self.vlan_id)

    @property
    def unresolved_endpoint_ids(self) -> tuple[str, ...]:
        """Return every endpoint of this group the plan left off an access port."""
        return tuple(
            dict.fromkeys(
                endpoint
                for dependent in self.dependents
                for endpoint in dependent.unresolved_endpoint_ids
            )
        )


@dataclass(frozen=True)
class ContinuityDependent:
    """One expectation whose two access switches a component must join."""

    expectation_id: str
    service_id: str
    kind: ServiceVerificationKind
    client_device_id: str
    host_device_id: str
    client_switch_id: str
    host_switch_id: str


@dataclass(frozen=True)
class ContinuityRequirement:
    """One compiled L2 component to observe once, and what waits on it."""

    component: L2Component
    dependents: tuple[ContinuityDependent, ...] = ()

    @property
    def key(self) -> tuple[str, int, tuple[str, ...]]:
        """Return the complete identity one continuity observation answers."""
        return self.component.key

    @property
    def vlan_id(self) -> int:
        """Return the VLAN the component carries."""
        return self.component.vlan_id


#: One group identity: `(switch_id, vlan)` for an access group, and
#: `("trunk_continuity", vlan, switch_ids)` for a continuity group.
GroupKey = tuple


@dataclass(frozen=True)
class AccessReadinessPlan:
    """Every group one invocation must observe, plus what it could not place."""

    requirements: tuple[AccessReadinessRequirement, ...] = ()
    #: Expectations whose endpoints the plan places on no access port at all,
    #: so they belong to no group and cannot be observed into readiness.
    unplaced: tuple[ReadinessDependent, ...] = ()
    #: Every group each expectation depends on, in the order they are decided:
    #: the client's access group, the server's access group, then continuity.
    #: The gate resolves a dependent only through this map, so an expectation
    #: can never be matched to a group by name or by position.
    groups_by_expectation: Mapping[str, tuple[GroupKey, ...]] = field(
        default_factory=dict
    )
    continuity: tuple[ContinuityRequirement, ...] = ()

    @property
    def gated_expectation_ids(self) -> tuple[str, ...]:
        """Return every expectation this plan gates, in derivation order."""
        return tuple(
            dict.fromkeys(
                [
                    dependent.expectation_id
                    for requirement in self.requirements
                    for dependent in requirement.dependents
                ]
                + [dependent.expectation_id for dependent in self.unplaced]
            )
        )

    @property
    def group_count(self) -> int:
        """Return how many distinct groups this plan can ask about."""
        return len(self.requirements) + len(self.continuity)


def access_port_placements(
    actions: Iterable[object],
) -> tuple[AccessPortPlacement, ...]:
    """Return the access-port placements one configuration plan declares.

    Typed structurally rather than by import, because the caller holds the
    compiled plan and this module must not depend on the configuration action
    union to read four attributes off it. An action missing any of them is not
    an access-port placement and is skipped, not guessed at.
    """
    placements: list[AccessPortPlacement] = []
    for action in actions:
        # The declared action type first. Four matching attribute names are not
        # an access port: a trunk action carries an interface and a device too,
        # and reading one as a placement would invent a required port out of a
        # link this question is not about.
        declared = getattr(action, "action_type", None)
        if str(getattr(declared, "value", declared)) != ACCESS_PORT_ACTION_TYPE:
            continue
        interface = getattr(action, "interface", None)
        vlan_id = getattr(action, "data_vlan_id", None)
        device_id = getattr(action, "device_id", None)
        endpoint_ids = getattr(action, "endpoint_ids", None)
        if not isinstance(interface, str) or not interface:
            continue
        if isinstance(vlan_id, bool) or not isinstance(vlan_id, int):
            continue
        if not isinstance(device_id, str) or not device_id:
            continue
        if not isinstance(endpoint_ids, (list, tuple)):
            continue
        placements.append(
            AccessPortPlacement(
                switch_device_id=device_id,
                switch_device_name=str(getattr(action, "device_name", "") or ""),
                interface=interface,
                vlan_id=vlan_id,
                endpoint_ids=tuple(
                    str(item) for item in endpoint_ids if isinstance(item, str) and item
                ),
            )
        )
    return tuple(placements)


def derive_access_readiness_plan(
    *,
    configuration_actions: Iterable[object],
    verification_expectations: Sequence[object],
) -> AccessReadinessPlan:
    """Group the HTTP-family expectations by every group their path needs.

    One access group per `(switch, VLAN)`, holding the union of the interfaces
    its dependents need on that switch, so the observation cost follows the
    topology and not the client count. A request inside one group is the
    legacy single-segment path. A request between two access switches of one
    VLAN also depends on the continuity group of the compiled component that
    joins them. Grouping is by the semantic device ids the plan assigns; the
    deployed name travels with the group for the query and for the report, and
    is never what a group is keyed on.
    """
    actions = list(configuration_actions)
    placements = access_port_placements(actions)
    topology: PathTopology | None = None
    by_endpoint: dict[str, list[AccessPortPlacement]] = {}
    for placement in placements:
        for endpoint_id in placement.endpoint_ids:
            by_endpoint.setdefault(endpoint_id, []).append(placement)

    grouped: dict[tuple[str, int], list[ReadinessDependent]] = {}
    names: dict[tuple[str, int], str] = {}
    interfaces: dict[tuple[str, int], set[str]] = {}
    continuity: dict[GroupKey, tuple[L2Component, list[ContinuityDependent]]] = {}
    unplaced: list[ReadinessDependent] = []
    groups_by_expectation: dict[str, tuple[GroupKey, ...]] = {}

    def join(key: tuple[str, int], dependent: ReadinessDependent, name: str) -> None:
        grouped.setdefault(key, []).append(dependent)
        names.setdefault(key, name)
        interfaces.setdefault(key, set()).update(dependent.interfaces)

    for expectation in verification_expectations:
        kind = getattr(expectation, "kind", None)
        if kind not in HTTP_REQUEST_KINDS:
            continue
        expectation_id = str(getattr(expectation, "id", "") or "")
        service_id = str(getattr(expectation, "service_id", "") or "")
        host_id = str(getattr(expectation, "host_device_id", "") or "")
        client_id = str(getattr(expectation, "client_device_id", "") or "")
        # Both ends of the request travel through their own access port. A
        # client-less expectation is host-only, and the host's port still has
        # to forward for anything to answer.
        wanted = tuple(dict.fromkeys(item for item in (client_id, host_id) if item))
        resolved = [
            placement for item in wanted for placement in by_endpoint.get(item, ())
        ]
        unresolved = tuple(item for item in wanted if not by_endpoint.get(item))
        keys = list(
            dict.fromkeys(
                (placement.switch_device_id, placement.vlan_id)
                for placement in resolved
            )
        )

        def dependent(
            on: tuple[str, int] | None = None,
            *,
            missing: tuple[str, ...] = unresolved,
            chosen: list[AccessPortPlacement] = resolved,
            identifier: str = expectation_id,
            service: str = service_id,
            request_kind: object = kind,
            client: str = client_id,
            host: str = host_id,
        ) -> ReadinessDependent:
            return ReadinessDependent(
                expectation_id=identifier,
                service_id=service,
                kind=request_kind,  # type: ignore[arg-type]
                client_device_id=client,
                host_device_id=host,
                interfaces=tuple(
                    dict.fromkeys(
                        placement.interface
                        for placement in chosen
                        if on is None
                        or (placement.switch_device_id, placement.vlan_id) == on
                    )
                ),
                unresolved_endpoint_ids=missing,
            )

        if len(keys) == 1:
            key = keys[0]
            join(key, dependent(), resolved[0].switch_device_name)
            groups_by_expectation[expectation_id] = (key,)
            continue
        joined = None
        if (
            len(keys) == 2
            and not unresolved
            and client_id
            and host_id
            and len(by_endpoint.get(client_id, ())) == 1
            and len(by_endpoint.get(host_id, ())) == 1
            and keys[0][1] == keys[1][1]
        ):
            if topology is None:
                topology = PathTopology(actions)
            client_key = (
                by_endpoint[client_id][0].switch_device_id,
                by_endpoint[client_id][0].vlan_id,
            )
            host_key = (
                by_endpoint[host_id][0].switch_device_id,
                by_endpoint[host_id][0].vlan_id,
            )
            component = topology.component_of(client_key[1], client_key[0])
            if component is not None and host_key[0] in set(
                component.switch_device_ids
            ):
                joined = (client_key, host_key, component)
        if joined is None:
            # No placement at all, or a path this derivation cannot join: a
            # request spanning two switches that no compiled component
            # connects, or two VLANs, is not observable as one path.
            unplaced.append(dependent())
            continue
        client_key, host_key, component = joined
        client_placement = by_endpoint[client_id][0]
        host_placement = by_endpoint[host_id][0]
        join(client_key, dependent(client_key), client_placement.switch_device_name)
        join(host_key, dependent(host_key), host_placement.switch_device_name)
        bucket = continuity.setdefault(component.key, (component, []))
        bucket[1].append(
            ContinuityDependent(
                expectation_id=expectation_id,
                service_id=service_id,
                kind=kind,  # type: ignore[arg-type]
                client_device_id=client_id,
                host_device_id=host_id,
                client_switch_id=client_key[0],
                host_switch_id=host_key[0],
            )
        )
        groups_by_expectation[expectation_id] = (client_key, host_key, component.key)

    requirements = tuple(
        AccessReadinessRequirement(
            switch_device_id=key[0],
            switch_device_name=names.get(key, ""),
            vlan_id=key[1],
            # Configuration-plan order, deduplicated: two plan rows naming one
            # interface are one interface to observe, and the report should not
            # ask about it twice.
            interfaces=tuple(
                dict.fromkeys(
                    placement.interface
                    for placement in placements
                    if (placement.switch_device_id, placement.vlan_id) == key
                    and placement.interface in interfaces.get(key, set())
                )
            ),
            dependents=tuple(dependents),
        )
        for key, dependents in grouped.items()
    )
    return AccessReadinessPlan(
        requirements=requirements,
        unplaced=tuple(unplaced),
        groups_by_expectation=dict(groups_by_expectation),
        continuity=tuple(
            ContinuityRequirement(component=component, dependents=tuple(items))
            for component, items in continuity.values()
        ),
    )


#: What one group's readiness observation concluded. `ADMITTED` is the only
#: value that lets a dependent request run. `REFUSED` is a real sample that did
#: not grant permission; `NOT_OBSERVED` is the absence of a sample, which is a
#: different fact and is equally non-authorizing.
READINESS_ADMITTED = "admitted"
READINESS_REFUSED = "refused"
READINESS_NOT_OBSERVED = "not_observed"

#: The dimension reported when readiness was never observed at all, so no
#: sample dimension exists to name.
DIMENSION_NOT_OBSERVED = "NOT_OBSERVED"

#: Why a group can end up without a sample, or without covering a dependent.
#: Each is a statement about this invocation, never about the network.
CAUSE_OBSERVER_UNAVAILABLE = "observer_unavailable"
CAUSE_BUDGET_EXHAUSTED = "readiness_budget_exhausted"
CAUSE_OBSERVATION_FAILED = "readiness_observation_failed"
CAUSE_ENDPOINT_NOT_ON_ACCESS_PORT = "endpoint_not_on_access_port"
CAUSE_PATH_NOT_SINGLE_SEGMENT = "path_not_single_switch_and_vlan"
CAUSE_INTERFACES_NOT_COVERED = "interfaces_not_covered_by_sample"
#: The observation came back describing a different switch, a different VLAN or
#: a narrower interface set than the one it was asked about. It is an answer to
#: another question, so it is not a sample of this group at all.
CAUSE_ANSWER_DOES_NOT_MATCH_REQUEST = "observation_does_not_answer_the_request"
#: The sample ended on its own nested-call budget rather than on completion, so
#: it is incomplete by construction whatever its rows happen to say.
CAUSE_SAMPLE_BUDGET_EXHAUSTED = "sample_call_budget_exhausted"
#: The caller never said how forwarding would be established for this request.
#: Silence is not an exemption, so the request is refused.
CAUSE_READINESS_NOT_DECLARED = "readiness_not_declared"


@dataclass(frozen=True)
class ReadinessDependentResult:
    """Whether one expectation own path was admitted, and why not."""

    expectation_id: str
    service_id: str
    kind: str
    client_device_id: str
    host_device_id: str
    interfaces: tuple[str, ...]
    admitted: bool
    cause: str = ""

    def as_row(self) -> dict[str, object]:
        """Return the public per-client coverage row."""
        return {
            "expectation_id": self.expectation_id,
            "service_id": self.service_id,
            "kind": self.kind,
            "client_device_id": self.client_device_id,
            "host_device_id": self.host_device_id,
            "interfaces": list(self.interfaces),
            "admitted": self.admitted,
            "cause": self.cause,
        }


@dataclass(frozen=True)
class AccessReadinessGroupResult:
    """One grouped observation, its verdict and everything that depended on it."""

    switch_device_id: str
    switch_device_name: str
    vlan_id: int
    interfaces: tuple[str, ...]
    status: str
    dimension: str
    causes: tuple[str, ...] = ()
    #: The rendered sample, exactly as `access_forwarding_facts` produced it, or
    #: an empty mapping when no sample was taken. It is never synthesized.
    sample: Mapping[str, object] = field(default_factory=dict)
    dependents: tuple[ReadinessDependentResult, ...] = ()

    @property
    def admitted(self) -> bool:
        """Whether this group grants its dependents permission to request."""
        return self.status == READINESS_ADMITTED

    def as_row(self) -> dict[str, object]:
        """Return the public readiness row, sample included."""
        return {
            "switch_device_id": self.switch_device_id,
            "switch_device_name": self.switch_device_name,
            "vlan_id": self.vlan_id,
            "requested_interfaces": list(self.interfaces),
            "status": self.status,
            "dimension": self.dimension,
            "causes": list(self.causes),
            "sample": dict(self.sample),
            "dependents": [item.as_row() for item in self.dependents],
        }


def _kind_value(kind: object) -> str:
    """Return the wire value of one verification kind, never its repr.

    `ServiceVerificationKind` restores the qualified `Enum.__str__`, so `str()`
    on it yields `ServiceVerificationKind.HTTP_FETCH`. The public row carries
    the protocol value every other report already uses.
    """
    return str(getattr(kind, "value", kind))


def _dependent_result(
    dependent: ReadinessDependent,
    *,
    admitted: bool,
    cause: str,
) -> ReadinessDependentResult:
    """Bind one dependent to the verdict its own path received."""
    unresolved = dependent.unresolved_endpoint_ids
    if unresolved:
        # A sample cannot speak for an endpoint the plan never placed on an
        # access port, whatever it said about the interfaces it did cover.
        return ReadinessDependentResult(
            expectation_id=dependent.expectation_id,
            service_id=dependent.service_id,
            kind=_kind_value(dependent.kind),
            client_device_id=dependent.client_device_id,
            host_device_id=dependent.host_device_id,
            interfaces=dependent.interfaces,
            admitted=False,
            cause=f"{CAUSE_ENDPOINT_NOT_ON_ACCESS_PORT}:" + ",".join(unresolved),
        )
    return ReadinessDependentResult(
        expectation_id=dependent.expectation_id,
        service_id=dependent.service_id,
        kind=_kind_value(dependent.kind),
        client_device_id=dependent.client_device_id,
        host_device_id=dependent.host_device_id,
        interfaces=dependent.interfaces,
        admitted=admitted,
        cause="" if admitted else cause,
    )


def observed_group_result(
    requirement: AccessReadinessRequirement,
    *,
    admitted: bool,
    dimension: str,
    causes: Sequence[str],
    sample: Mapping[str, object],
    forwarding_interfaces: Sequence[str] = (),
) -> AccessReadinessGroupResult:
    """State what one taken sample grants this group and each dependent.

    A dependent is admitted only when the group was admitted and every interface
    its own path needs appears among the ones the sample admitted. A group-level
    pass is never sufficient on its own: a sample that covered fewer interfaces
    than a dependent needs does not cover that dependent.
    """
    granted = frozenset(forwarding_interfaces)
    collected = tuple(causes)
    dependents: list[ReadinessDependentResult] = []
    for dependent in requirement.dependents:
        covered = bool(dependent.interfaces) and granted.issuperset(
            dependent.interfaces
        )
        dependents.append(
            _dependent_result(
                dependent,
                admitted=admitted and covered,
                cause=(
                    CAUSE_INTERFACES_NOT_COVERED
                    if admitted
                    else f"{dimension}:" + ",".join(collected)
                ),
            )
        )
    return AccessReadinessGroupResult(
        switch_device_id=requirement.switch_device_id,
        switch_device_name=requirement.switch_device_name,
        vlan_id=requirement.vlan_id,
        interfaces=requirement.interfaces,
        status=(
            READINESS_ADMITTED
            if admitted and dependents and all(item.admitted for item in dependents)
            else READINESS_REFUSED
        ),
        dimension=dimension,
        causes=collected,
        sample=dict(sample),
        dependents=tuple(dependents),
    )


def unobserved_group_result(
    requirement: AccessReadinessRequirement,
    *,
    cause: str,
) -> AccessReadinessGroupResult:
    """State that this group has no sample, and why, without inventing one."""
    return AccessReadinessGroupResult(
        switch_device_id=requirement.switch_device_id,
        switch_device_name=requirement.switch_device_name,
        vlan_id=requirement.vlan_id,
        interfaces=requirement.interfaces,
        status=READINESS_NOT_OBSERVED,
        dimension=DIMENSION_NOT_OBSERVED,
        causes=(cause,),
        sample={},
        dependents=tuple(
            _dependent_result(dependent, admitted=False, cause=cause)
            for dependent in requirement.dependents
        ),
    )


def unplaced_group_result(
    dependents: Sequence[ReadinessDependent],
) -> AccessReadinessGroupResult:
    """Return the one row carrying every expectation no single group can hold."""
    return AccessReadinessGroupResult(
        switch_device_id="",
        switch_device_name="",
        vlan_id=0,
        interfaces=(),
        status=READINESS_NOT_OBSERVED,
        dimension=DIMENSION_NOT_OBSERVED,
        causes=(CAUSE_PATH_NOT_SINGLE_SEGMENT,),
        sample={},
        dependents=tuple(
            _dependent_result(
                dependent,
                admitted=False,
                cause=CAUSE_PATH_NOT_SINGLE_SEGMENT,
            )
            for dependent in dependents
        ),
    )


@dataclass(frozen=True)
class ContinuityDependentResult:
    """Whether one dependent's two access switches were joined, and why not."""

    expectation_id: str
    service_id: str
    kind: str
    client_device_id: str
    host_device_id: str
    client_switch_id: str
    host_switch_id: str
    admitted: bool
    cause: str = ""

    def as_row(self) -> dict[str, object]:
        """Return the public per-client continuity row."""
        return {
            "expectation_id": self.expectation_id,
            "service_id": self.service_id,
            "kind": self.kind,
            "client_device_id": self.client_device_id,
            "host_device_id": self.host_device_id,
            "client_switch_id": self.client_switch_id,
            "host_switch_id": self.host_switch_id,
            "admitted": self.admitted,
            "cause": self.cause,
        }


@dataclass(frozen=True)
class ContinuityGroupResult:
    """One continuity observation of one component, and its dependents."""

    component: L2Component
    status: str
    dimension: str
    causes: tuple[str, ...] = ()
    sample: Mapping[str, object] = field(default_factory=dict)
    dependents: tuple[ContinuityDependentResult, ...] = ()

    @property
    def key(self) -> tuple[str, int, tuple[str, ...]]:
        """Return the identity this result answers."""
        return self.component.key

    def as_row(self) -> dict[str, object]:
        """Return the public continuity row, sample included."""
        component = self.component
        return {
            "kind": "trunk_continuity",
            "vlan_id": component.vlan_id,
            "switch_device_ids": list(component.switch_device_ids),
            "switch_device_names": list(component.switch_device_names),
            "links": [
                {
                    "link_id": link.link_id,
                    "switch_a_id": link.switch_a_id,
                    "interface_a": link.interface_a,
                    "switch_b_id": link.switch_b_id,
                    "interface_b": link.interface_b,
                }
                for link in component.links
            ],
            "status": self.status,
            "dimension": self.dimension,
            "causes": list(self.causes),
            "sample": dict(self.sample),
            "dependents": [item.as_row() for item in self.dependents],
        }


def _continuity_dependent(
    dependent: ContinuityDependent, *, admitted: bool, cause: str
) -> ContinuityDependentResult:
    return ContinuityDependentResult(
        expectation_id=dependent.expectation_id,
        service_id=dependent.service_id,
        kind=_kind_value(dependent.kind),
        client_device_id=dependent.client_device_id,
        host_device_id=dependent.host_device_id,
        client_switch_id=dependent.client_switch_id,
        host_switch_id=dependent.host_switch_id,
        admitted=admitted,
        cause="" if admitted else cause,
    )


def observed_continuity_result(
    requirement: ContinuityRequirement,
    *,
    verdicts: Mapping[tuple[str, str], tuple[bool, str, str]],
    sample: Mapping[str, object],
) -> ContinuityGroupResult:
    """Bind each dependent to its own pair's verdict from one observation.

    `verdicts` maps `(client_switch, host_switch)` to `(admitted, dimension,
    cause)`. A dependent whose pair has no verdict is not admitted.
    """
    dependents = tuple(
        _continuity_dependent(
            item,
            admitted=verdicts.get(
                (item.client_switch_id, item.host_switch_id), (False,)
            )[0],
            cause=verdicts.get(
                (item.client_switch_id, item.host_switch_id),
                (False, "NOT_OBSERVED", "pair_not_decided"),
            )[2],
        )
        for item in requirement.dependents
    )
    refused = [verdict for verdict in verdicts.values() if not verdict[0]]
    return ContinuityGroupResult(
        component=requirement.component,
        status=(
            READINESS_ADMITTED
            if dependents and all(item.admitted for item in dependents)
            else READINESS_REFUSED
        ),
        dimension=refused[0][1] if refused else "NONE",
        causes=tuple(dict.fromkeys(verdict[2] for verdict in refused)),
        sample=dict(sample),
        dependents=dependents,
    )


def unobserved_continuity_result(
    requirement: ContinuityRequirement, *, cause: str
) -> ContinuityGroupResult:
    """State that a component has no observation, and why."""
    return ContinuityGroupResult(
        component=requirement.component,
        status=READINESS_NOT_OBSERVED,
        dimension=DIMENSION_NOT_OBSERVED,
        causes=(cause,),
        dependents=tuple(
            _continuity_dependent(item, admitted=False, cause=cause)
            for item in requirement.dependents
        ),
    )


def access_group_key(switch_name: str, vlan_id: int) -> str:
    """Return the text identity of one access group on deployed names."""
    return f"access:{switch_name}:{vlan_id}"


def continuity_group_key(vlan_id: int, switch_names: Sequence[str]) -> str:
    """Return the text identity of one continuity group on deployed names.

    The switch names are taken in the component's own order, which is the
    order the gate reads them in, so the closure, the ledger label and the
    record row name the same group the same way.
    """
    digest = hashlib.sha256(",".join(switch_names).encode("utf-8")).hexdigest()
    return f"trunk_continuity:{vlan_id}:{len(switch_names)}:{digest[:16]}"
