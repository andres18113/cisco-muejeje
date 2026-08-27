"""Governed LIVE for the positive disposable Voice slice (A side of the A/B).

Every adapter here maps a production runtime onto the qualifier's protocol. No
adapter invents a mutation: the reads reuse the same `verify` comparison and the
same registered operational queries the canonical run uses, and the writes are
the same typed actions.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

GOVERNED_ROOT = Path(__file__).resolve().parents[1]
if str(GOVERNED_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(GOVERNED_ROOT / "src"))

from packet_tracer_mcp.application.use_cases.qualify_positive_voice_slice import (  # noqa: E402
    DATA_VLAN_ID,
    VOICE_VLAN_ID,
    PositiveVoiceSliceQualifier,
)
from packet_tracer_mcp.domain.enterprise.models.configuration import (  # noqa: E402
    VerificationExpectation,
    VerificationKind,
)
from packet_tracer_mcp.infrastructure.execution.configuration_runtime import (  # noqa: E402
    PacketTracerConfigurationRuntime,
)
from packet_tracer_mcp.infrastructure.execution.enterprise_configuration_runtime import (  # noqa: E402
    PacketTracerEnterpriseConfigurationRuntime,
)
from packet_tracer_mcp.infrastructure.execution.enterprise_voice_runtime import (  # noqa: E402
    PacketTracerEnterpriseVoiceRuntime,
)
from packet_tracer_mcp.infrastructure.execution.ios_terminal import (  # noqa: E402
    ControlledIosExecutor,
    OperationalQueryId,
    parse_show_ip_dhcp_binding,
    parse_show_spanning_tree,
)
from packet_tracer_mcp.infrastructure.execution.live_bridge import (  # noqa: E402
    PacketTracerHttpTransport,
)
from packet_tracer_mcp.infrastructure.execution.packet_tracer_physical_runtime import (  # noqa: E402
    PacketTracerPhysicalTopologyRuntime,
)
from packet_tracer_mcp.infrastructure.execution.simulation_trace_runtime import (  # noqa: E402
    SimulationTraceRuntime,
)

EVIDENCE_PATH = GOVERNED_ROOT / "data" / "cp-scale" / "positive-voice-ab.json"
ROUTER_MODEL = "2811"
SWITCH_MODEL = "3560-24PS"
PHONE_MODEL = "7960"

#: A value that can never equal a real VLAN id, so a FAILED field reads as
#: CONTRADICTED without inventing the number that was actually observed.
_CONTRADICTED_VLAN = -1


class _ReadPort:
    __slots__ = ("data_vlan_id", "voice_vlan_id")

    def __init__(self, data_vlan_id, voice_vlan_id):
        self.data_vlan_id = data_vlan_id
        self.voice_vlan_id = voice_vlan_id


def _table_readable(show) -> bool:
    """The three dimensions a registered operational read has to establish.

    EXECUTED is only the terminal answering.  FRESH is this capture being of
    this moment, and COMPLETE is it being the whole logical read rather than
    the first page of one.  Parsing a table that fails either of the last two
    turns a property of the READ into a property of the network: an STP row
    that never got printed reads ABSENT, and a binding table that stopped at a
    pager reads as zero bindings.  Both are discriminants of this A/B, so both
    have to come from a read that established all three.
    """
    return bool(
        getattr(show, "executed", False)
        and getattr(show, "fresh_output_observed", False)
        and getattr(show, "output_complete", False)
    )


def _field_to_vlan(status_name: str, expected: int):
    """VERIFIED keeps the expected value; FAILED contradicts; anything else is
    unread.  The comparison itself already happened inside the runtime."""
    text = str(status_name or "").upper()
    if "VERIFIED" in text:
        return expected
    if "FAILED" in text:
        return _CONTRADICTED_VLAN
    return None


class _ConfigurationAdapter:
    """Applies typed configuration and reads back through production paths."""

    def __init__(self, enterprise, ios):
        self._enterprise = enterprise
        self._ios = ios

    def apply_actions(self, actions):
        return self._enterprise.apply_actions(actions)

    def read_access_port(self, device_name: str, interface: str):
        expectation = VerificationExpectation(
            id=f"voiceab/verify/{interface}",
            action_id="voiceab/access",
            kind=VerificationKind.ACCESS_PORT,
            device_id="voiceab/sw",
            device_name=device_name,
            expected={
                "interface": interface,
                "vlan_id": DATA_VLAN_ID,
                "voice_vlan_id": VOICE_VLAN_ID,
            },
        )
        results = self._enterprise.verify([expectation])
        if not results:
            return None
        fields = getattr(results[0], "fields", {}) or {}
        return _ReadPort(
            _field_to_vlan(fields.get("vlan_id"), DATA_VLAN_ID),
            _field_to_vlan(fields.get("voice_vlan_id"), VOICE_VLAN_ID),
        )

    def read_spanning_tree(self, device_name: str):
        """None means the table was never read; it never means no rows.

        The qualifier turns None into UNOBSERVABLE and a parsed table with no
        phone row into ABSENT, and those are different answers to the causal
        question.  Only a read that was fresh and complete may produce either.
        """
        show = self._ios.execute(device_name, OperationalQueryId.SHOW_SPANNING_TREE)
        if not _table_readable(show):
            return None
        return parse_show_spanning_tree(show.output)

    def read_dhcp_bindings(self, device_name: str):
        """Same gate: an incomplete binding table is not zero bindings."""
        show = self._ios.execute(
            device_name, OperationalQueryId.SHOW_IP_DHCP_BINDING,
        )
        if not _table_readable(show):
            return None
        return parse_show_ip_dhcp_binding(show.output)


class _CallControlAdapter:
    def __init__(self, voice):
        self._voice = voice

    def apply_actions(self, actions):
        return self._voice.apply_actions(actions)

    def observe_registrations(self, expectations):
        return self._voice.observe_registrations(expectations)


class _EndpointAdapter:
    def __init__(self, configuration):
        self._configuration = configuration

    def configure_endpoint_dhcp(self, device_name: str, interface: str):
        return self._configuration.configure_endpoint_dhcp(device_name, interface)

    def read_endpoint_address(self, device_name: str, interface: str):
        reader = getattr(self._configuration, "read_endpoint_address", None)
        if reader is None:
            # No separate endpoint reader on this runtime: the registration
            # surface stays the only address evidence, and its absence must read
            # UNOBSERVABLE rather than as a missing address.
            return None
        return reader(device_name, interface)


def _serialize(result) -> dict:
    return {
        "diagnostic": "POSITIVE_DISPOSABLE_VOICE_AB",
        "router_model": result.router_model,
        "switch_model": result.switch_model,
        "phone_model": result.phone_model,
        "router_name": result.router_name,
        "switch_name": result.switch_name,
        "voice_vlan_id": result.voice_vlan_id,
        "outcome": result.outcome,
        "portfast": result.portfast,
        "voice_binding_count": result.voice_binding_count,
        "voice_bindings_observed": result.voice_bindings_observed,
        "stp_phone_row_after": result.stp_phone_row_after,
        "realtime_before": result.realtime_before,
        "realtime_after": result.realtime_after,
        "lifecycle": [
            {
                "sequence": item.sequence,
                "name": item.name,
                "observed": item.observed,
                "status": item.status,
                "detail": item.detail,
            }
            for item in result.lifecycle
        ],
        "phones": [
            {
                "phone_name": item.phone_name,
                "extension": item.extension,
                "switch_interface": item.switch_interface,
                "data_vlan_readback": item.data_vlan_readback,
                "voice_vlan_readback": item.voice_vlan_readback,
                "dhcp_enabled": item.dhcp_enabled,
                "ipv4": item.ipv4,
                "voice_svi_present": item.voice_svi_present,
                "address_channel": item.address_channel,
                "device_ipv4": item.device_ipv4,
                "addressed": item.addressed,
                "registration": item.registration,
                "stp_row_before": item.stp_row_before,
                "stp_row_after": item.stp_row_after,
                "succeeded": item.succeeded,
                "matches_cp_scale_signature": item.matches_cp_scale_signature,
            }
            for item in result.phones
        ],
        "baseline": (
            result.baseline_inventory.compact_summary()
            if result.baseline_inventory is not None else None
        ),
        "final": (
            result.final_inventory.compact_summary()
            if result.final_inventory is not None else None
        ),
        "workspace_restored": result.workspace_restored,
        "realtime_restored": result.realtime_restored,
        "owned_links": list(result.owned_links),
        "removed": list(result.removed),
        "errors": list(result.errors),
    }


def _inventory(physical) -> list[dict]:
    observation = physical.observe_workspace()
    if not observation.observed:
        raise RuntimeError("Live inventory became unobservable: " + observation.message)
    return [
        {"name": item.name, "model": item.model, "ports": list(item.ports)}
        for item in observation.semantic_devices
    ]


def run(packet_tracer_version: str) -> int:
    transport = PacketTracerHttpTransport()
    if not transport.start(timeout_seconds=20.0):
        print(json.dumps({"hard_stop": "The Packet Tracer bridge did not connect."}))
        return 2
    try:
        physical = PacketTracerPhysicalTopologyRuntime(
            transport.send_and_wait,
            mutation_timeout_seconds=30.0,
            observation_timeout_seconds=12.0,
        )
        enterprise = PacketTracerEnterpriseConfigurationRuntime(
            lambda: _inventory(physical),
            transport.send,
            transport.send_and_wait,
            l3_timeout_seconds=20.0,
        )
        ios = ControlledIosExecutor(transport.send_and_wait)
        configuration = PacketTracerConfigurationRuntime(transport.send)
        result = PositiveVoiceSliceQualifier(
            physical,
            _ConfigurationAdapter(enterprise, ios),
            _CallControlAdapter(
                PacketTracerEnterpriseVoiceRuntime(
                    lambda: _inventory(physical),
                    transport.send,
                    transport.send_and_wait,
                )
            ),
            _EndpointAdapter(configuration),
            SimulationTraceRuntime(transport.send_and_wait),
        ).qualify(ROUTER_MODEL, SWITCH_MODEL, PHONE_MODEL)
    finally:
        transport.stop()

    evidence = _serialize(result)
    evidence["packet_tracer_version"] = packet_tracer_version
    EVIDENCE_PATH.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE_PATH.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(json.dumps({
        "event": "POSITIVE_VOICE_AB_COMPLETE",
        "outcome": evidence["outcome"],
        "portfast": evidence["portfast"],
        "voice_bindings": evidence["voice_bindings_observed"],
        "stp_phone_row_after": evidence["stp_phone_row_after"],
        "phones": [
            {
                key: item[key]
                for key in (
                    "extension", "voice_vlan_readback", "dhcp_enabled",
                    "addressed", "registration", "stp_row_after",
                )
            }
            for item in evidence["phones"]
        ],
        "workspace_restored": evidence["workspace_restored"],
        "realtime_restored": evidence["realtime_restored"],
        "errors": evidence["errors"][:5],
    }))
    return 0 if result.workspace_restored else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packet-tracer-version", required=True)
    args = parser.parse_args()
    return run(args.packet_tracer_version)


if __name__ == "__main__":
    raise SystemExit(main())
