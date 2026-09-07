"""Exact Packet Tracer POE-2 calibration contract and raw evidence reader."""
from __future__ import annotations

import hashlib
import re
from ...domain.enterprise.models.poe2 import PoE2Capture, PoE2Evidence
from ...domain.enterprise.rules.poe2 import validate_poe2_evidence as _validate

START_HEAD = "580a64586e51cfb813fc2af48de5bb9a99f535af"
BUILD = "9.0.1.0858"
BINDING = {"switch_model": "3560-24PS", "switch_port": "FastEthernet0/13",
           "endpoint_model": "AccessPoint-PT", "endpoint_port": "Port 0"}
COMPLETENESS_KEYS = {"observer_complete", "all_pagers_traversed",
                     "expected_privileged_prompt_reached", "no_pending_continuation",
                     "attributable", "stable", "dispatch_integrity_valid", "fresh"}
_RULE = "--------- ------ ---------- ------- ------------------- ----- ----"
_ROW = re.compile(r"^\s*(Fa[0-9]+/[0-9]+)\s+(\S+)\s+(\S+)\s+([0-9]+(?:\.[0-9]+)?)\s+(.+?)\s+(\S+)\s+([0-9]+(?:\.[0-9]+)?)\s*$")


def raw_target_row(output: str) -> dict | None:
    """Read one measured interface, refusing duplicate or malformed row text."""
    if output.count(_RULE) != 1:
        raise ValueError("Exactly one calibrated table is required")
    rows = []
    seen = set()
    for line in output.split(_RULE, 1)[1].splitlines():
        if not line.strip() or re.fullmatch(r"[A-Za-z0-9_.-]+#", line.strip()):
            continue
        match = _ROW.fullmatch(line)
        if match is None:
            raise ValueError("Unknown table content cannot establish absence")
        interface, admin, oper, power, device, power_class, maximum = match.groups()
        if interface in seen:
            raise ValueError("Duplicate interface in raw table")
        seen.add(interface)
        if interface == "Fa0/13":
            rows.append(dict(interface=interface, admin=admin, oper=oper,
                             power_watts=float(power), device=device,
                             power_class=power_class, max_watts=float(maximum)))
    # This exact 3560 table covers 24 access ports, minus a disabled target.
    expected = {"Fa0/" + str(n) for n in range(1, 25)}
    if seen not in (expected, expected - {"Fa0/13"}):
        raise ValueError("Unexpected or missing non-target rows")
    return rows[0] if rows else None


def completeness(observation: dict, expected_prompt: str, stable: bool,
                 switch_name: str) -> dict[str, bool]:
    dispatch = observation.get("command_result") or {}
    output = observation.get("raw_output", "")
    privileged = bool(re.fullmatch(r"[A-Za-z0-9_.-]+#", expected_prompt))
    return dict(
        observer_complete=observation.get("capture_complete") is True,
        all_pagers_traversed=dispatch.get("pager_continuation") in
            {"completed", "not_encountered"} and dispatch.get("pager_pages_captured", 0) >= 1,
        expected_privileged_prompt_reached=privileged and
            output.rstrip().endswith("\n" + expected_prompt) and
            dispatch.get("session_state") == "exec_prompt_ready",
        no_pending_continuation=dispatch.get("truncated_by_pager") is False and
            "--More--" not in output,
        attributable=observation.get("device_identity_provenance") == "confirmed_unique" and
            observation.get("observed_device_name") == switch_name and
            observation.get("switch_identity") == switch_name and
            dispatch.get("observed_device_name") == switch_name and
            dispatch.get("device_identity_provenance") == "confirmed_unique",
        stable=stable,
        dispatch_integrity_valid=dispatch.get("dispatch_classification") == "dispatched" and
            dispatch.get("echo_observed") == "show power inline" and
            dispatch.get("query_id") == "qualification_show_power_inline" and
            dispatch.get("executed") is True,
        fresh=observation.get("fresh_output_observed") is True and
            dispatch.get("fresh_output_observed") is True,
    )


def capture_delivery(capture: PoE2Capture, raw: bytes, switch_name: str) -> str:
    if hashlib.sha256(raw).hexdigest() != capture.raw_sha256:
        raise ValueError("Raw SHA-256 mismatch")
    output = raw.decode("utf-8")
    first, repeat = capture.observation, capture.repeat_observation
    if not capture.stable or first.get("raw_output") != repeat.get("raw_output"):
        raise ValueError("Capture stability not proven")
    for observation in (first, repeat):
        gates = completeness(observation, capture.expected_prompt, True, switch_name)
        if set(gates) != COMPLETENESS_KEYS or not all(gates.values()):
            raise ValueError("Incomplete, stale or unattributable table")
        if capture.table_completeness != gates:
            raise ValueError("Completeness summary disagrees with dispatch evidence")
        if observation.get("status") != "observed" or observation.get("refusal_reason"):
            raise ValueError("Observer refused")
        if output != observation.get("raw_output") or output != observation["command_result"].get("output"):
            raise ValueError("Raw output and interpreted dispatch disagree")
        ports = observation.get("ports")
        if not isinstance(ports, list) or len(ports) != 1 or ports[0].get("port") != BINDING["switch_port"]:
            raise ValueError("Observation does not concern the exact port")
        row = raw_target_row(output)
        if row != ports[0].get("row"):
            raise ValueError("Raw and typed port rows disagree")
        if row is None:
            delivery = "not_delivering"
        elif row["oper"] == "on" and row["power_watts"] > 0:
            delivery = "delivering"
        elif row["oper"] == "off" and row["power_watts"] == 0:
            # Diagnostic state only; negative experiment below requires the
            # causally calibrated ABSENCE, not an uncharacterized off row.
            delivery = "not_delivering"
        else:
            raise ValueError("Measured row is ambiguous")
        if ports[0].get("delivery") != delivery:
            raise ValueError("Raw and typed delivery disagree")
    return first["ports"][0]["delivery"]


def validate_poe2_evidence(bundle: PoE2Evidence, raw_files: dict[str, bytes]):
    return _validate(bundle, raw_files, expected_start_head=START_HEAD,
                     expected_build=BUILD, expected_binding=BINDING,
                     capture_verifier=capture_delivery)
