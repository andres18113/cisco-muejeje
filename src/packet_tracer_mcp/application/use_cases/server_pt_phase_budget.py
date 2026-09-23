"""Plan-derived structural calls and hard per-phase C31 dispatch ceilings."""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil

from ...domain.models.plans import TopologyPlan
from .prepare_server_pt_commissioning import ServerPtCommissioningBundle

# The authorized preliminary extension consumes this share of the original
# setup ceiling. These are enforced by GovernedPhaseChannel before dispatch.
PREQUALIFICATION_MAX_OPERATIONS = 250
PREQUALIFICATION_MAX_SECONDS = 300
PREQUALIFICATION_RESERVE_OPERATIONS = 20
PREQUALIFICATION_RESERVE_SECONDS = 50
SETUP_MAX_OPERATIONS = 4750
SETUP_MAX_SECONDS = 1500
CLEANUP_MAX_OPERATIONS = 250
CLEANUP_MAX_SECONDS = 300
E5_IOS_QUERY_MAX_CALLS = 30
E5_IOS_QUERY_MAX_SECONDS = 5.0


@dataclass(frozen=True)
class ServerPtPhaseBudget:
    """Bounded operation arithmetic for the exact 30-client physical plan."""

    prequalification_max_operations: int
    prequalification_max_seconds: int
    setup_max_operations: int
    setup_max_seconds: int
    cleanup_max_operations: int
    cleanup_max_seconds: int
    e4_max_operations: int
    e5_max_operations: int
    prequalification_structural_max_operations: int
    prequalification_structural_max_seconds: float
    setup_coded_wait_seconds: float
    cleanup_structural_max_operations: int
    cleanup_structural_max_seconds: float
    setup_e5_remaining_operations: int


def derive_phase_budget(bundle: ServerPtCommissioningBundle) -> ServerPtPhaseBudget:
    """Count E4 and cleanup calls; enforce the charter's independent caps.

    E4 performs two empty-workspace observations, up to three calls per
    device, and per link one pre-read, one mutation receipt and a 4-second
    exact-link readback at 0.15-second intervals. E5 counts its one inventory,
    selected mutations, IOS boot polls, VLAN polls and grouped trunk rounds.
    Each registered IOS query has an enforced nested bridge-call ceiling of 30.
    This setup wires no PVST transition observer, so no learning extension can
    be admitted by the grouped trunk verifier. An unknown effect stops rather
    than borrowing acceptance's 30-operation/40-second release reserve.
    Cleanup performs one pre-read and one receipt per owned device plus the
    pre-cleanup and two restoration inventories.
    """
    topology = TopologyPlan.model_validate_json(bundle.topology_json)
    if bundle.client_count != 30 or bundle.site_count != 1:
        raise ValueError("campaign phase budget needs the 30-client campus")
    link_readback_max = 1 + ceil(3.0 / 0.15)
    e4_calls = (
        2 + 3 * len(topology.devices) + (2 + link_readback_max) * len(topology.links)
    )
    ios_switches = sum(
        device.model in {"2950T-24", "3560-24PS"} for device in topology.devices
    )
    vlan_actions = bundle.setup_action_types.get("create_vlan", 0)
    trunk_actions = bundle.setup_action_types.get("configure_trunk", 0)
    if (
        ios_switches != 4
        or vlan_actions != 4
        or trunk_actions != 10
        or len(bundle.setup_action_ids) != vlan_actions + trunk_actions
    ):
        raise ValueError("setup action or IOS target count changed")
    e5_calls = (
        1  # Applicator inventory.
        + len(bundle.setup_action_ids)  # At most one mutation send per action.
        + ios_switches * (1 + ceil(45.0 / 0.25))  # IOS boot.
        + vlan_actions * (1 + ceil(5.0 / 0.25))  # VLAN manager readback.
        + ios_switches
        * (1 + ceil(5.0 / 0.25))
        * E5_IOS_QUERY_MAX_CALLS  # One SHOW per switch per grouped trunk round.
    )
    cleanup_calls = 2 * len(topology.devices) + 3
    prequalification_calls = (
        8
        + 1
        + 1
        + (1 + ceil(30.0 / 0.25))
        + 1
        + 1
        + (1 + ceil(8.0 / 0.25))
        + 1
        + (1 + ceil(8.0 / 0.25))
        + 1
        + 2
    )
    prequalification_seconds = (
        8 * 5.0  # Port qualifier's bounded workspace/device calls.
        + 15.0
        + 30.0  # One probe create/readback and selected IOS boot wait.
        + 2 * 8.0
        + 10.0
        + 2 * 4.0  # Trunk readbacks, delete, restoration.
        + prequalification_calls * 0.5  # Fresh handle-bound receiver reads.
    )
    e4_seconds = (
        2 * 3.0
        + len(topology.devices) * 3 * 3.0
        + len(topology.links) * (3.0 + 3.0 + 3.0 + 3.0)
        + e4_calls * 0.25  # Receiver continuity before every bridge call.
        + 1.5  # A final timed-out E4 read can require mailbox cancellation.
    )
    boot_polls = 1 + ceil(45.0 / 0.25)
    vlan_polls = 1 + ceil(5.0 / 0.25)
    e5_seconds = (
        ios_switches * (45.0 + 3.0 + 1.5 + boot_polls * 0.25)
        + vlan_actions * (5.0 + 3.0 + 1.5 + vlan_polls * 0.25)
        + 5.0  # Grouped trunk wait, checked after each full inspection.
        + ios_switches * (E5_IOS_QUERY_MAX_SECONDS + 1.5 + 0.25)
        + 12.0  # One inventory: 10s read, 1.5s cancellation, receiver.
        + len(bundle.setup_action_ids) * 1.0  # Local batch publish allowance.
    )
    setup_seconds = e4_seconds + e5_seconds
    cleanup_seconds = (
        len(topology.devices) * (2.5 + 2.5) + 3 * 2.5 + cleanup_calls * 0.25
    )
    if (
        PREQUALIFICATION_MAX_OPERATIONS + SETUP_MAX_OPERATIONS > 5000
        or PREQUALIFICATION_MAX_SECONDS + SETUP_MAX_SECONDS > 1800
        or e4_calls + e5_calls > SETUP_MAX_OPERATIONS
        or prequalification_calls
        > PREQUALIFICATION_MAX_OPERATIONS - PREQUALIFICATION_RESERVE_OPERATIONS
        or prequalification_seconds > PREQUALIFICATION_MAX_SECONDS
        or setup_seconds > SETUP_MAX_SECONDS
        or cleanup_calls > CLEANUP_MAX_OPERATIONS
        or cleanup_seconds > CLEANUP_MAX_SECONDS
    ):
        raise ValueError("derived setup or cleanup allowance exceeds the charter")
    return ServerPtPhaseBudget(
        prequalification_max_operations=PREQUALIFICATION_MAX_OPERATIONS,
        prequalification_max_seconds=PREQUALIFICATION_MAX_SECONDS,
        setup_max_operations=SETUP_MAX_OPERATIONS,
        setup_max_seconds=SETUP_MAX_SECONDS,
        cleanup_max_operations=CLEANUP_MAX_OPERATIONS,
        cleanup_max_seconds=CLEANUP_MAX_SECONDS,
        e4_max_operations=e4_calls,
        e5_max_operations=e5_calls,
        prequalification_structural_max_operations=prequalification_calls,
        prequalification_structural_max_seconds=prequalification_seconds,
        setup_coded_wait_seconds=setup_seconds,
        cleanup_structural_max_operations=cleanup_calls,
        cleanup_structural_max_seconds=cleanup_seconds,
        setup_e5_remaining_operations=SETUP_MAX_OPERATIONS - e4_calls,
    )
