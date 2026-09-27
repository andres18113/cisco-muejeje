"""Classify an SP-2 native named/default pool sample without inferring leases."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from ..models.service_qualification import MeasurementConclusion
from .dhcp_lease_evidence import (
    ROW_EXACT,
    ROW_MAC_ELSEWHERE,
    ROW_WRONG_MAC,
    TERMINATION_REPEAT,
    AddressRange,
    ClientReading,
    LeaseScan,
    is_dotted_mac,
    normalized_mac,
    row_status,
)
from .service_qualification_evidence import Assessment


def assess_sp2_pool_identity(
    selected: Sequence[str],
    clients: Mapping[str, ClientReading],
    named: LeaseScan,
    native: LeaseScan,
    *,
    named_pool: str,
    native_pool: str,
    named_range: AddressRange,
    expected_netmask: str,
    other_pools: Sequence[str] = (),
) -> Assessment:
    """Distinguish physical pool rows for every selected client in one sample.

    The result describes this read only. A clean scan proves no matching row
    inside its calibrated window; it does not establish future capacity,
    renewal, or that a request caused the observed address. An exact native
    row is a negative finding even when a named pool was configured.
    """
    facts: dict[str, object] = {
        "named_pool": named_pool,
        "native_pool": native_pool,
        "named_scan": named.as_facts(),
        "native_scan": native.as_facts(),
        "clients": {},
    }
    contradictions: list[str] = []
    negatives: list[str] = []
    unknown: list[str] = []
    if not selected or len(set(selected)) != len(selected):
        contradictions.append("selected_clients_not_unique")
    if not named_pool or not native_pool or named_pool == native_pool:
        contradictions.append("pool_identity_ambiguous")
    if (named.pool, native.pool) != (named_pool, native_pool):
        contradictions.append("scan_pool_identity_mismatch")
    if other_pools:
        contradictions.append(
            "unexpected_physical_pools:" + ",".join(sorted(other_pools))
        )
    if (
        named.termination == TERMINATION_REPEAT
        or native.termination == TERMINATION_REPEAT
    ):
        contradictions.append("repeated_lease_row")
    if not named.observed:
        unknown.append("named_scan_unobserved")
    if not native.observed:
        unknown.append("native_scan_unobserved")
    seen_ip: dict[str, str] = {}
    seen_mac: dict[str, str] = {}
    per_client: dict[str, object] = {}
    for name in selected:
        reading = clients.get(name)
        if reading is None or reading.client != name or not reading.observed:
            per_client[name] = {
                "observed": False,
                "cause": reading.cause if reading else "missing",
            }
            unknown.append(f"{name}:client_unobserved")
            continue
        named_row = row_status(named, reading, None)
        native_row = row_status(native, reading, None)
        per_client[name] = {
            "observed": True,
            "mode": reading.mode,
            "ipv4": reading.ipv4,
            "netmask": reading.netmask,
            "mac": reading.mac,
            "named_row": named_row,
            "native_row": native_row,
        }
        if reading.ipv4 not in ("", "0.0.0.0"):
            prior_ip = seen_ip.setdefault(reading.ipv4, name)
            if prior_ip != name:
                contradictions.append(f"duplicate_address:{prior_ip}:{name}")
        if reading.mac:
            mac = normalized_mac(reading.mac)
            prior_mac = seen_mac.setdefault(mac, name)
            if prior_mac != name:
                contradictions.append(f"duplicate_mac:{prior_mac}:{name}")
        if named_row in (ROW_WRONG_MAC, ROW_MAC_ELSEWHERE) or native_row in (
            ROW_WRONG_MAC,
            ROW_MAC_ELSEWHERE,
        ):
            contradictions.append(f"{name}:lease_identity_conflict")
        if named_row == ROW_EXACT and native_row == ROW_EXACT:
            contradictions.append(f"{name}:row_in_both_pools")
        elif native_row == ROW_EXACT:
            negatives.append(f"{name}:served_by_native_default")
        elif named_row != ROW_EXACT:
            unknown.append(f"{name}:named_row_unattributed")
        if (
            reading.mode is not True
            or not reading.ipv4
            or not is_dotted_mac(reading.mac)
        ):
            unknown.append(f"{name}:client_binding_unusable")
        elif (
            not named_range.contains(reading.ipv4)
            or reading.netmask != expected_netmask
        ):
            if named_row == ROW_EXACT:
                contradictions.append(f"{name}:named_row_outside_intended_policy")
            else:
                unknown.append(f"{name}:address_outside_intended_policy")
    facts["clients"] = per_client
    if contradictions:
        conclusion = MeasurementConclusion.CONTRADICTED
        causes = contradictions
    elif negatives:
        conclusion = MeasurementConclusion.NEGATIVE_OBSERVED
        causes = negatives
    else:
        if not named.clean:
            unknown.append("named_scan_incomplete")
        if not native.clean:
            unknown.append("native_scan_incomplete")
        if unknown:
            conclusion = MeasurementConclusion.INCONCLUSIVE
            causes = unknown
        else:
            conclusion = MeasurementConclusion.SUPPORTED_IN_SAMPLE
            causes = []
    return Assessment(
        conclusion,
        facts=facts,
        causes=causes,
        limitations=[
            "physical_pool_rows_only:not_product_service_acceptance",
            "scan_window_and_termination_are_local_to_this_sample",
            "no_inference_about_dhcp_run_renewal_or_total_capacity",
        ],
    )
