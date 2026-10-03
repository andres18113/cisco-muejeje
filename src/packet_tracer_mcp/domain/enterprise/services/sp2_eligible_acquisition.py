"""Prospective explicit-start comparisons without changing the v1 oracle.

Eligibility and causal credit are separate. Every selected subject remains in
shared identity checks, including subjects excluded from intervention. These
rules interpret observed state; they do not assert native retry or renewal.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any

from ..models.service_plan import ConfigureServerDhcpPool
from ..models.service_qualification import MeasurementConclusion
from .dhcp_lease_evidence import (
    ROW_MAC_ELSEWHERE,
    ROW_REPEATED,
    ROW_WRONG_MAC,
    normalized_mac,
)
from .service_qualification_evidence import Assessment
from .sp2_acquisition_discriminator import (
    ARM_CONTROL,
    ARM_EXPLICIT_START,
    AcquisitionSample,
    acquisition_precondition,
    assess_acquisition_arms,
    client_outcome,
)


@dataclass(frozen=True)
class EligibleCohort:
    """Observed dispositions and reasons a fixed comparison may not proceed."""

    eligible: tuple[str, ...]
    observations: Mapping[str, str]
    causes: tuple[str, ...]

    @property
    def holds(self) -> bool:
        """Whether an observed eligible comparison has no shared refusal."""
        return bool(self.eligible) and not self.causes


def _policy_causes(
    server: object, pools: Mapping[str, ConfigureServerDhcpPool]
) -> list[str]:
    expected = {pool.effective_pool_name: pool for pool in pools.values()}
    if not isinstance(server, Mapping):
        return ["server_policy_unobserved"]
    rows = server.get("pools")
    if not isinstance(rows, list) or not all(
        isinstance(row, Mapping) and isinstance(row.get("name"), str) for row in rows
    ):
        return ["server_pool_policy_unobserved"]
    causes: list[str] = []
    observed = {row["name"]: row for row in rows}
    for name, pool in expected.items():
        values = {
            "network": pool.network,
            "mask": pool.netmask,
            "gateway": pool.gateway,
            "dns": pool.dns_server,
            "start": pool.lease_start,
            "end": pool.lease_end,
            "max": pool.max_users,
        }
        if name not in observed or any(
            observed[name].get(key) != value for key, value in values.items()
        ):
            causes.append(f"server_pool_policy_changed:{name}")
    exclusions = sorted(
        {
            (item.start, item.end)
            for pool in expected.values()
            for item in pool.excluded_ranges
        }
    )
    raw = server.get("exclusions")
    if (
        not isinstance(raw, list)
        or not all(
            isinstance(row, Mapping)
            and isinstance(row.get("start"), str)
            and isinstance(row.get("end"), str)
            for row in raw
        )
        or server.get("excluded_count") != len(raw)
        or sorted((row["start"], row["end"]) for row in raw) != exclusions
    ):
        causes.append("server_exclusions_changed_or_unobserved")
    return causes


def _comparison_causes(
    arms: Mapping[str, str], pools: Mapping[str, ConfigureServerDhcpPool]
) -> list[str]:
    causes = []
    for pool in sorted({item.effective_pool_name for item in pools.values()}):
        selected = {
            arm for name, arm in arms.items() if pools[name].effective_pool_name == pool
        }
        for arm in (ARM_EXPLICIT_START, ARM_CONTROL):
            if arm not in selected:
                causes.append(f"comparison_absent:{pool}:{arm}")
    return causes


def eligible_cohort(
    arms: Mapping[str, str],
    pools: Mapping[str, ConfigureServerDhcpPool],
    sample: AcquisitionSample,
    server: object,
    *,
    require_comparisons: bool = True,
) -> EligibleCohort:
    """Classify a fresh full census before any fixed-arm intervention.

    Local unreadable subjects are excluded. Shared policy, pool or identity
    contradictions refuse the comparison. Assigned subjects stay observations.
    Subsequent censuses keep the assignment and may only remove eligibility.
    """
    if (
        not arms
        or set(arms) != set(pools)
        or not set(arms.values())
        <= {
            ARM_CONTROL,
            ARM_EXPLICIT_START,
        }
    ):
        return EligibleCohort((), {}, ("eligible_arm_binding_invalid",))
    names = tuple(sorted({pool.effective_pool_name for pool in pools.values()}))
    causes = _policy_causes(server, pools)
    if causes:
        return EligibleCohort(
            (), {name: "not_evaluated:shared_policy" for name in arms}, tuple(causes)
        )
    causes.extend(acquisition_precondition((), {}, server, sample.scans, names).causes)
    causes.extend(sample.read_causes)
    macs = Counter(
        normalized_mac(row.mac)
        for row in sample.readings.values()
        if row.observed and normalized_mac(row.mac)
    )
    addresses = Counter(
        row.ipv4
        for row in sample.readings.values()
        if row.observed
        and row.ipv4 not in ("", "0.0.0.0")
        and not row.ipv4.startswith("169.254.")
    )
    causes.extend(f"duplicate_mac:{mac}" for mac, count in macs.items() if count > 1)
    causes.extend(
        f"duplicate_address:{ip}" for ip, count in addresses.items() if count > 1
    )
    eligible = []
    observations: dict[str, str] = {}
    for name in sorted(arms):
        reading = sample.readings.get(name)
        if reading is None or not reading.observed:
            observations[name] = "unobserved"
            continue
        outcome = client_outcome(
            name, ARM_CONTROL, "none", pools[name], [sample], frozenset(names)
        )
        state = outcome.samples[0]
        if state["competing"]:
            causes.append(f"competing_identity:{name}")
        if state["intended_row"] in (ROW_WRONG_MAC, ROW_REPEATED, ROW_MAC_ELSEWHERE):
            causes.append(f"intended_pool_identity_conflict:{name}")
        precondition = acquisition_precondition(
            [name], sample.readings, server, sample.scans, names
        )
        if precondition.holds and outcome.complete:
            eligible.append(name)
            observations[name] = "eligible"
        elif state["usable"]:
            observations[name] = "assigned_observer"
        else:
            observations[name] = "ineligible:" + precondition.clients[name]
            causes.extend(
                cause
                for cause in precondition.causes
                if cause.startswith("client_row_present:")
                and precondition.clients[name] == "link_local"
            )
    if require_comparisons:
        causes.extend(
            _comparison_causes({name: arms[name] for name in eligible}, pools)
        )
    return EligibleCohort(tuple(eligible), observations, tuple(sorted(set(causes))))


def assess_eligible_arms(
    arms: Mapping[str, str],
    pools: Mapping[str, ConfigureServerDhcpPool],
    interventions: Mapping[str, str],
    samples: Sequence[AcquisitionSample],
    servers: Sequence[object],
    *,
    expected_samples: int | None = None,
) -> Assessment:
    """Require complete shared exposure and sustained post-acquisition evidence.

    Pre-effect acquisition never earns causal credit. A later contradiction
    keeps the earlier positive observation but revokes the causal conclusion.
    """
    all_arms = {name: arms.get(name, ARM_CONTROL) for name in pools}
    active = {
        name: arm
        for name, arm in arms.items()
        if interventions.get(name) != "observed_before_intervention"
    }
    causes = _comparison_causes(active, pools)
    if (
        len(servers) != len(samples)
        or not samples
        or (expected_samples is not None and len(samples) != expected_samples)
    ):
        causes.append("eligible_shared_window_incomplete")
    for sample, server in zip(samples, servers, strict=False):
        cohort = eligible_cohort(
            all_arms, pools, sample, server, require_comparisons=False
        )
        causes.extend(f"sample:{sample.index}:{cause}" for cause in cohort.causes)
    assessment = assess_acquisition_arms(
        active, {name: pools[name] for name in active}, interventions, samples
    )
    planned = frozenset(pool.effective_pool_name for pool in pools.values())
    observed: dict[str, Any] = {}
    for name in pools:
        outcome = client_outcome(
            name,
            all_arms[name],
            interventions.get(name, "observer"),
            pools[name],
            samples,
            planned,
        )
        observed[name] = outcome.as_facts()
        if name not in active:
            observed[name].update(
                arm="observer",
                acquired=False,
                observed_stable_lease=outcome.acquired,
            )
        if name in active and not outcome.complete:
            causes.append(f"required_reading_lost:{name}")
        if name in active and outcome.acquired:
            first = next(
                (i for i, state in enumerate(outcome.samples) if state["usable"]), None
            )
            if first is not None and any(
                not state["usable"] for state in outcome.samples[first:]
            ):
                causes.append(f"acquired_prerequisite_revoked:{name}")
            if first is not None and any(
                (
                    sample.readings[name].ipv4,
                    normalized_mac(sample.readings[name].mac),
                )
                != outcome.stable_identity
                for sample in samples[first:]
                if name in sample.readings
            ):
                causes.append(f"acquired_identity_changed:{name}")
    return replace(
        assessment,
        conclusion=MeasurementConclusion.INCONCLUSIVE
        if causes
        else assessment.conclusion,
        facts={
            **assessment.facts,
            "all_subjects": observed,
            "pre_effect_observers": [name for name in arms if name not in active],
        },
        causes=sorted(set([*assessment.causes, *causes])),
    )
