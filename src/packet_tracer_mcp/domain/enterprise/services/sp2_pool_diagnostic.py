"""Classify an SP-2 native named/default pool sample without inferring leases."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from ..models.service_qualification import MeasurementConclusion
from .dhcp_lease_evidence import (
    ROW_EXACT,
    ROW_MAC_ELSEWHERE,
    ROW_REPEATED,
    ROW_REPRESENTATION,
    ROW_WRONG_MAC,
    TERMINATION_MALFORMED,
    TERMINATION_NON_MONOTONE,
    TERMINATION_NULL,
    TERMINATION_REPEAT,
    TERMINATION_THROW,
    TERMINATION_UNDEFINED,
    TERMINATION_WINDOW,
    AddressRange,
    ClientReading,
    LeaseCalibration,
    LeaseScan,
    is_dotted_mac,
    normalized_mac,
    row_status,
)
from .service_qualification_evidence import Assessment


def cap_sp2_pool_identity(
    assessment: Assessment,
    progression: Mapping[str, Mapping[str, object]],
    selected: Sequence[str],
    *,
    preclient_complete: bool = True,
) -> Assessment:
    """Preserve earlier sample failures when the latest physical row is good."""
    failed = [
        name
        for name in selected
        if progression.get(name, {}).get("admitted") is not True
    ]
    for name, decision in progression.items():
        if decision.get("admitted") is True:
            continue
        causes = decision.get("causes")
        if isinstance(causes, list | tuple):
            assessment.causes.extend(
                f"{name}:{cause}" for cause in causes if isinstance(cause, str)
            )
    if assessment.conclusion is MeasurementConclusion.SUPPORTED_IN_SAMPLE and failed:
        conflict = any(
            cause == "competing_default_row"
            or cause.endswith("default_identity_conflict")
            for name in failed
            for cause in progression.get(name, {}).get("causes", ())
            if isinstance(cause, str)
        )
        assessment.conclusion = (
            MeasurementConclusion.CONTRADICTED
            if conflict
            else MeasurementConclusion.INCONCLUSIVE
        )
        assessment.causes.extend(
            f"two_sample_progression_unmet:{name}" for name in failed
        )
    if not preclient_complete:
        assessment.limitations.append("preclient_lease_absence_not_fully_observed")
        if assessment.conclusion is MeasurementConclusion.SUPPORTED_IN_SAMPLE:
            assessment.conclusion = MeasurementConclusion.INCONCLUSIVE
            assessment.causes.append("preclient_lease_absence_not_fully_observed")
    return assessment


def sp2_client_progression(
    readings: Sequence[ClientReading],
    bindings: Sequence[Mapping[str, object]],
    named_scans: Sequence[LeaseScan],
    native_scans: Sequence[LeaseScan],
    *,
    named_range: AddressRange,
    expected_mask: str,
    expected_gateway: str,
    expected_dns: str,
    preclient_complete: bool = True,
) -> tuple[bool, tuple[str, ...]]:
    """Admit a second probe client only after two stable first-client samples.

    This is a sampling gate, not exclusive named-pool support. A complete
    bounded default window can admit another investigative client even when
    its null end has not been calibrated across empty and nonempty states.
    """
    if any(
        len(items) != 2 for items in (readings, bindings, named_scans, native_scans)
    ):
        return False, ("two_samples_required",)
    first, second = readings
    causes: list[str] = []
    if not preclient_complete:
        causes.append("preclient_lease_absence_not_fully_observed")
    mac = normalized_mac(first.mac)
    if (
        not first.observed
        or not second.observed
        or first.client != second.client
        or first.mode is not True
        or second.mode is not True
        or not mac
        or normalized_mac(second.mac) != mac
        or first.ipv4 != second.ipv4
        or first.netmask != second.netmask
        or not named_range.contains(first.ipv4)
        or first.netmask != expected_mask
    ):
        causes.append("client_binding_unstable_or_outside_policy")
    positive = frozenset((ROW_EXACT, ROW_REPRESENTATION))
    conflicts = frozenset((ROW_WRONG_MAC, ROW_MAC_ELSEWHERE, ROW_REPEATED))
    for index, (binding, named, native, reading) in enumerate(
        zip(bindings, named_scans, native_scans, readings, strict=True), start=1
    ):
        if named.pool != named_scans[0].pool or named.pool == "serverPool":
            causes.append(f"sample_{index}:named_pool_identity_mismatch")
        if native.pool != "serverPool":
            causes.append(f"sample_{index}:default_pool_identity_mismatch")
        if not named.observed or row_status(named, reading, None) not in positive:
            causes.append(f"sample_{index}:named_row_not_exact")
        if not native.observed:
            causes.append(f"sample_{index}:default_scan_unobserved")
        else:
            if not native.clean:
                causes.append(f"sample_{index}:default_scan_incomplete")
            default_row = row_status(native, reading, None)
            if default_row in positive:
                causes.append("competing_default_row")
            elif default_row in conflicts:
                causes.append(f"sample_{index}:default_identity_conflict")
        gateways = binding.get("gateway_reads")
        observed_gateways = (
            [
                item.get("value")
                for item in gateways
                if isinstance(item, Mapping)
                and item.get("api") is True
                and item.get("error") == ""
            ]
            if isinstance(gateways, list)
            else []
        )
        gateway_ok = bool(observed_gateways) and all(
            value == expected_gateway for value in observed_gateways
        )
        if not (
            binding.get("device") == reading.client
            and binding.get("found") is True
            and binding.get("port_found") is True
            and binding.get("error") == ""
            and binding.get("ipv4") == reading.ipv4
            and binding.get("netmask") == reading.netmask
            and gateway_ok
            and binding.get("dns_api") is True
            and binding.get("dns_error") == ""
            and binding.get("dns_server") == expected_dns
        ):
            causes.append(f"sample_{index}:gateway_or_resolver_unusable")
    return not causes, tuple(dict.fromkeys(causes))


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
    native_calibration: LeaseCalibration | None = None,
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
        "native_calibration": (
            native_calibration.as_facts() if native_calibration is not None else None
        ),
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
    positive_rows = frozenset({ROW_EXACT, ROW_REPRESENTATION})
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
        if named_row in positive_rows and native_row in positive_rows:
            contradictions.append(f"{name}:row_in_both_pools")
        elif native_row in positive_rows:
            negatives.append(f"{name}:served_by_native_default")
        elif named_row not in positive_rows:
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
            if named_row in positive_rows:
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
        if (
            native_calibration is None
            or native_calibration.pool != native_pool
            or not native_calibration.null_ends_rows
        ):
            unknown.append("native_absence_uncalibrated")
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


def assess_sp2_remote_samples(
    readings: Sequence[ClientReading],
    bindings: Sequence[Mapping[str, object]],
    named_scans: Sequence[LeaseScan],
    native_scans: Sequence[LeaseScan],
    *,
    named_range: AddressRange,
    expected_mask: str,
    expected_gateway: str,
    expected_dns: str,
    expected_capacity: int,
) -> Assessment:
    """Assess stable remote usability with exact named rows, without end inference.

    A matching physical row proves association for this sample. It does not
    prove that the default pool has no later row or that the packet carried a
    particular giaddr value. Those claims stay separate from usability.
    """
    if any(len(rows) != 2 for rows in (readings, bindings, named_scans, native_scans)):
        return Assessment(
            MeasurementConclusion.INCONCLUSIVE,
            causes=["two_samples_required"],
            limitations=["packet_giaddr_not_observed"],
        )
    first, second = readings
    positives = frozenset((ROW_EXACT, ROW_REPRESENTATION))
    conflicts = frozenset((ROW_WRONG_MAC, ROW_MAC_ELSEWHERE, ROW_REPEATED))
    named_rows = [
        row_status(scan, reading, None)
        for scan, reading in zip(named_scans, readings, strict=True)
    ]
    default_rows = [
        row_status(scan, reading, None)
        for scan, reading in zip(native_scans, readings, strict=True)
    ]
    causes: list[str] = []
    contradictions: list[str] = []
    negatives: list[str] = []
    stable = (
        first.observed
        and second.observed
        and first.client == second.client
        and first.mode is True
        and second.mode is True
        and normalized_mac(first.mac) != ""
        and normalized_mac(first.mac) == normalized_mac(second.mac)
        and first.ipv4 == second.ipv4
        and first.netmask == second.netmask == expected_mask
        and named_range.contains(first.ipv4)
    )
    if not stable:
        causes.append("client_binding_unstable_or_outside_policy")
    for index, (reading, binding, named, native, named_row, default_row) in enumerate(
        zip(
            readings,
            bindings,
            named_scans,
            native_scans,
            named_rows,
            default_rows,
            strict=True,
        ),
        start=1,
    ):
        if named.pool == "serverPool" or named.pool != named_scans[0].pool:
            contradictions.append(f"sample_{index}:named_pool_identity_mismatch")
        if native.pool != "serverPool":
            contradictions.append(f"sample_{index}:default_pool_identity_mismatch")
        if named_row in conflicts or default_row in conflicts:
            contradictions.append(f"sample_{index}:physical_identity_conflict")
        if (
            named.termination == TERMINATION_REPEAT
            or native.termination == TERMINATION_REPEAT
        ):
            contradictions.append(f"sample_{index}:repeated_physical_row")
        if named.capacity is None:
            causes.append(f"sample_{index}:named_capacity_unobserved")
        elif named.capacity != expected_capacity:
            contradictions.append(f"sample_{index}:named_capacity_mismatch")
        if named.capacity is not None and len(named.rows) > named.capacity:
            contradictions.append(f"sample_{index}:named_rows_exceed_capacity")
        if native.capacity is not None and len(native.rows) > native.capacity:
            contradictions.append(f"sample_{index}:default_rows_exceed_capacity")
        for pool_label, scan in (("named", named), ("default", native)):
            mac = normalized_mac(reading.mac)
            if mac and any(
                row.ip != reading.ipv4
                for row in scan.rows_with_normalized_mac(reading.mac)
            ):
                contradictions.append(
                    f"sample_{index}:{pool_label}_mac_multiple_addresses"
                )
            if any(
                normalized_mac(row.mac) != mac
                for row in scan.rows_with_ip(reading.ipv4)
            ):
                contradictions.append(f"sample_{index}:{pool_label}_ip_multiple_macs")
            if any(normalized_mac(row.mac) != mac for row in scan.rows):
                causes.append(f"sample_{index}:unselected_{pool_label}_lease_row")
        if named.termination not in {
            TERMINATION_NULL,
            TERMINATION_WINDOW,
            TERMINATION_THROW,
            TERMINATION_UNDEFINED,
        }:
            causes.append(f"sample_{index}:named_scan_incomplete")
        if native.termination in {
            TERMINATION_MALFORMED,
            TERMINATION_NON_MONOTONE,
        }:
            causes.append(f"sample_{index}:default_scan_incomplete")
        if default_row in positives:
            if named_row in positives:
                contradictions.append(f"sample_{index}:row_in_both_pools")
            else:
                negatives.append(f"sample_{index}:served_by_native_default")
        if not named.observed or named_row not in positives:
            causes.append(f"sample_{index}:named_row_not_exact")
        if not native.observed:
            causes.append(f"sample_{index}:default_scan_unobserved")
        gateways = binding.get("gateway_reads")
        observed_gateways = (
            [
                item.get("value")
                for item in gateways
                if isinstance(item, Mapping)
                and item.get("api") is True
                and item.get("error") == ""
            ]
            if isinstance(gateways, list)
            else []
        )
        if not (
            binding.get("device") == reading.client
            and binding.get("found") is True
            and binding.get("port_found") is True
            and binding.get("error") == ""
            and binding.get("ipv4") == reading.ipv4
            and binding.get("netmask") == reading.netmask
            and observed_gateways
            and all(value == expected_gateway for value in observed_gateways)
            and binding.get("dns_api") is True
            and binding.get("dns_error") == ""
            and binding.get("dns_server") == expected_dns
        ):
            causes.append(f"sample_{index}:gateway_or_resolver_unusable")
    conclusion = (
        MeasurementConclusion.CONTRADICTED
        if contradictions
        else MeasurementConclusion.NEGATIVE_OBSERVED
        if negatives
        else MeasurementConclusion.INCONCLUSIVE
        if causes
        else MeasurementConclusion.SUPPORTED_IN_SAMPLE
    )
    return Assessment(
        conclusion,
        facts={
            "client": first.client,
            "readings": [reading.__dict__ for reading in readings],
            "bindings": [dict(binding) for binding in bindings],
            "named_rows": named_rows,
            "default_rows": default_rows,
            "named_scans": [scan.as_facts() for scan in named_scans],
            "default_scans": [scan.as_facts() for scan in native_scans],
            "exclusive_serving": False,
        },
        causes=list(dict.fromkeys([*contradictions, *negatives, *causes])),
        limitations=[
            "relay_associated_selection_not_packet_giaddr_bytes",
            "default_table_end_not_calibrated",
            "named_table_end_not_calibrated",
            "pre_mode_absence_not_proven_no_causal_acquisition_claim",
            "exclusive_serving_not_established",
            "native_capacity_not_established",
        ],
    )


def sp2_remote_acquired(reading: ClientReading) -> bool:
    """Whether one relayed client reading shows an acquired address.

    No address and the all-zero address are no acquisition, and a link-local
    fallback is a failed acquisition, not an address. Mode, attribution and
    pool membership are separate observations this predicate claims nothing
    about.
    """
    return bool(
        reading.observed
        and reading.ipv4 not in ("", "0.0.0.0")
        and not reading.ipv4.startswith("169.254.")
    )
