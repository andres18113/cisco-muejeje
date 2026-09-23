"""Compile the exact Server-PT intent, E4 plan and L2 setup selection offline."""

from __future__ import annotations

import hashlib
from collections import Counter

from pydantic import BaseModel, Field

from ...domain.enterprise.models.configuration import (
    ConfigurationActionType,
    ConfigurationPlan,
)
from ...domain.enterprise.scenarios.server_pt_campus import server_pt_campus_intent
from ...domain.enterprise.services.service_policy import derive_service_policy
from .compile_configuration import compile_enterprise_configuration
from .compose_enterprise_reference import compose_enterprise_reference

SERVER_PT_BUILD = "9.0.1.0858"
_SETUP_TYPES = frozenset(
    {ConfigurationActionType.CREATE_VLAN, ConfigurationActionType.CONFIGURE_TRUNK}
)


class ServerPtCommissioningBundle(BaseModel):
    """Full exported product inputs and identities; no runtime claim is implied."""

    schema_version: int = 1
    build: str
    client_count: int
    site_count: int
    marker: str
    intent_json: str
    intent_sha256: str
    topology_json: str
    topology_sha256: str
    physical_topology_hash: str
    configuration_semantic_hash: str
    setup_action_ids: list[str] = Field(default_factory=list)
    setup_action_types: dict[str, int] = Field(default_factory=dict)


def _setup_action_ids(plan: ConfigurationPlan) -> tuple[str, ...]:
    """Select all compiled trunks and exactly their dependency closure."""
    by_id = {action.id: action for action in plan.actions}
    selected = {
        action.id
        for action in plan.actions
        if action.action_type is ConfigurationActionType.CONFIGURE_TRUNK
    }
    if not selected:
        raise ValueError("the compiled campus has no trunk foundations")
    pending = list(selected)
    while pending:
        action = by_id[pending.pop()]
        for dependency in (*action.depends_on, *action.apply_dependencies):
            if dependency not in by_id:
                raise ValueError(f"setup dependency is absent: {dependency}")
            if dependency not in selected:
                selected.add(dependency)
                pending.append(dependency)
    unexpected = sorted(
        action_id
        for action_id in selected
        if by_id[action_id].action_type not in _SETUP_TYPES
    )
    if unexpected:
        raise ValueError(
            "setup requires an out-of-scope dependency: " + ", ".join(unexpected)
        )
    return tuple(action.id for action in plan.actions if action.id in selected)


def _reviewed_live_topology(topology) -> None:
    """Refuse a planner change outside the activated campus's physical shape."""
    roles = Counter(
        (device.model, device.enterprise_role) for device in topology.devices
    )
    expected = Counter(
        {
            ("PC-PT", "user_pc"): 30,
            ("Server-PT", "server"): 1,
            ("2950T-24", "access_switch"): 2,
            ("3560-24PS", "distribution_switch"): 2,
        }
    )
    cables = Counter(link.cable for link in topology.links)
    if (
        len(topology.devices) != 35
        or len(topology.links) != 36
        or topology.modules
        or roles != expected
        or cables != Counter({"straight": 31, "cross": 5})
    ):
        raise ValueError("reviewed campaign shape changed: physical plan")


def _reviewed_live_configuration(plan: ConfigurationPlan) -> None:
    """Refuse new setup effects or a changed VLAN/trunk topology."""
    vlan_actions = [
        action
        for action in plan.actions
        if action.action_type is ConfigurationActionType.CREATE_VLAN
    ]
    trunks = [
        action
        for action in plan.actions
        if action.action_type is ConfigurationActionType.CONFIGURE_TRUNK
    ]
    links = Counter(action.source_link_id for action in trunks)
    if (
        len(vlan_actions) != 4
        or any(action.vlan_id != 10 for action in vlan_actions)
        or len(trunks) != 10
        or len(links) != 5
        or any(count != 2 for count in links.values())
        or any(action.allowed_vlans != [10] for action in trunks)
    ):
        raise ValueError("reviewed campaign shape changed: L2 configuration")


def prepare_server_pt_commissioning(
    clients: int,
    marker: str,
    *,
    sites: int = 1,
    build: str = SERVER_PT_BUILD,
) -> ServerPtCommissioningBundle:
    """Compile a full E4 export and predicted E5 identity without contact.

    Configuration identity is the planned semantic hash. Setup must recompile
    against the actually observed E4 manifest and compare before dispatch.
    """
    if build != SERVER_PT_BUILD:
        raise ValueError("Server-PT commissioning requires the exact measured build")
    intent = server_pt_campus_intent(clients, marker, sites=sites)
    composed = compose_enterprise_reference(intent, packet_tracer_version=build)
    if not composed.valid or not all(
        (composed.enterprise, composed.topology, composed.traffic)
    ):
        raise ValueError("campus composition failed: " + "; ".join(composed.issues))
    if clients == 30 and sites == 1:
        _reviewed_live_topology(composed.topology)
    policy = derive_service_policy(
        intent, enterprise=composed.enterprise, topology=composed.topology
    )
    if not policy.is_valid:
        raise ValueError("campus service policy failed")
    configuration = compile_enterprise_configuration(
        composed.enterprise,
        composed.topology,
        policy.policy,
        capabilities=composed.capabilities,
        traffic_by_link=composed.traffic.contributions_by_link,
        packet_tracer_version=build,
    )
    if not configuration.is_valid or configuration.plan is None:
        raise ValueError("campus configuration compilation failed")
    if clients == 30 and sites == 1:
        _reviewed_live_configuration(configuration.plan)
    action_ids = _setup_action_ids(configuration.plan)
    selected = set(action_ids)
    counts = Counter(
        action.action_type.value
        for action in configuration.plan.actions
        if action.id in selected
    )
    intent_json = intent.model_dump_json()
    topology_json = composed.topology.model_dump_json()
    return ServerPtCommissioningBundle(
        build=build,
        client_count=clients,
        site_count=sites,
        marker=marker,
        intent_json=intent_json,
        intent_sha256=hashlib.sha256(intent_json.encode("utf-8")).hexdigest(),
        topology_json=topology_json,
        topology_sha256=hashlib.sha256(topology_json.encode("utf-8")).hexdigest(),
        physical_topology_hash=composed.topology.physical_identity_hash,
        configuration_semantic_hash=configuration.plan.semantic_hash,
        setup_action_ids=list(action_ids),
        setup_action_types=dict(sorted(counts.items())),
    )
