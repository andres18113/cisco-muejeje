"""Bounded qualification contract for the next Voice DHCP-pool observer.

The candidate is deliberately not a product ``OperationalQueryId`` yet.  This
module first pins the one-command developer boundary used to measure Packet
Tracer support.  Parser and product-readback tests belong here only after a
fresh complete real fixture exists.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from src.packet_tracer_mcp.application.use_cases.qualify_dhcp_pool_command import (
    QUALIFICATION_POOL_NAME,
    DhcpPoolCommandQualifier,
    DhcpPoolCommandSupport,
    classify_dhcp_pool_command_support,
)
from src.packet_tracer_mcp.domain.enterprise.models.configuration import (
    ConfigureDhcpPool,
)
from src.packet_tracer_mcp.domain.enterprise.models.configuration_runtime import (
    RuntimeActionMutation,
)
from src.packet_tracer_mcp.domain.enterprise.models.physical_deployment import (
    MutationDisposition,
    PhysicalMutationResult,
    PhysicalObjectKind,
    PhysicalWorkspaceDeviceObservation,
    PhysicalWorkspaceObservation,
)
from src.packet_tracer_mcp.infrastructure.execution.ios_terminal import (
    ControlledIosExecutor,
    DeviceIdentityProvenance,
    DhcpPoolSubnetStatistics,
    DhcpPoolStatistics,
    IosCommandResult,
    IosQualificationQueryId,
    IosSessionState,
    OperationalQueryId,
    parse_show_ip_dhcp_pool,
)
from src.packet_tracer_mcp.infrastructure.execution.enterprise_configuration_runtime import (
    PacketTracerEnterpriseConfigurationRuntime,
)


_ANSWER = (
    "show ip dhcp pool\n"
    "Pool MCP_DHCP_POOL_Q :\n"
    " Total addresses : 6\n"
    " Leased addresses : 0\n"
    "Router#"
)
_INVALID = (
    "show ip dhcp pool\n"
    "             ^\n"
    "% Invalid input detected at '^' marker.\n"
    "Router#"
)
_REAL_PT_9_0_1_0858_POOL = (
    "show ip dhcp pool\n"
    "\n"
    "Pool MCP_DHCP_POOL_Q :\n"
    " Utilization mark (high/low)    : 100 / 0\n"
    " Subnet size (first/next)       : 0 / 0 \n"
    " Total addresses                : 6\n"
    " Leased addresses               : 0\n"
    " Excluded addresses             : 1\n"
    " Pending event                  : none\n"
    "\n"
    " 1 subnet is currently in the pool\n"
    " Current index        IP address range                    Leased/Excluded/Total\n"
    " 198.18.250.1         198.18.250.1     - 198.18.250.6      0    / 1     / 6\n"
    "Router#"
)


def _show(
    output: str = _ANSWER,
    *,
    executed: bool = True,
    fresh: bool = True,
    complete: bool = True,
    identity: DeviceIdentityProvenance = DeviceIdentityProvenance.CONFIRMED_UNIQUE,
) -> IosCommandResult:
    return IosCommandResult(
        device_name="MCP-DHCPPOOLQ-tok",
        query_id=IosQualificationQueryId.SHOW_IP_DHCP_POOL,
        executed=executed,
        output=output,
        session_state=IosSessionState.EXEC_PROMPT_READY,
        fresh_output_observed=fresh,
        output_complete=complete,
        device_identity_provenance=identity.value,
    )


def test_the_measured_candidate_is_promoted_without_opening_a_raw_input() -> None:
    assert ControlledIosExecutor.qualification_command(
        IosQualificationQueryId.SHOW_IP_DHCP_POOL,
    ) == "show ip dhcp pool"
    assert ControlledIosExecutor._registered_command(
        OperationalQueryId.SHOW_IP_DHCP_POOL,
        interface="",
    ) == "show ip dhcp pool"

    executor = ControlledIosExecutor(lambda _js, _timeout: None)
    with pytest.raises(TypeError, match="OperationalQueryId only"):
        executor.execute(  # type: ignore[arg-type]
            "R1", IosQualificationQueryId.SHOW_IP_DHCP_POOL,
        )
    with pytest.raises(TypeError, match="IosQualificationQueryId only"):
        executor.qualify(  # type: ignore[arg-type]
            "R1", OperationalQueryId.SHOW_IP_DHCP_BINDING,
        )


def test_live_harness_accepts_no_ios_or_javascript_from_the_caller() -> None:
    root = Path(__file__).resolve().parents[1]
    source = (
        root / "tools" / "cp_scale_dhcp_pool_qualification_live.py"
    ).read_text(encoding="utf-8")

    assert "DhcpPoolCommandQualifier" in source
    assert "ImportIsolationPreflight" in source
    assert "safe_for_disposable_mutation" not in source  # owned by the use case
    assert "--execute" in source
    assert "--command" not in source
    assert "pt_send_raw" not in source
    assert "show running-config" not in source
    assert "show run" not in source


def test_a_fresh_complete_uniquely_attributed_answer_means_supported() -> None:
    assert classify_dhcp_pool_command_support(
        _show(),
    ) is DhcpPoolCommandSupport.YES


def test_real_packet_tracer_fixture_parses_pool_range_and_available_space() -> None:
    pools = parse_show_ip_dhcp_pool(_REAL_PT_9_0_1_0858_POOL)

    assert pools == [DhcpPoolStatistics(
        name="MCP_DHCP_POOL_Q",
        utilization_high=100,
        utilization_low=0,
        subnet_size_first=0,
        subnet_size_next=0,
        total_addresses=6,
        leased_addresses=0,
        excluded_addresses=1,
        pending_event="none",
        declared_subnet_count=1,
        subnets=(DhcpPoolSubnetStatistics(
            current_index="198.18.250.1",
            range_start="198.18.250.1",
            range_end="198.18.250.6",
            leased_addresses=0,
            excluded_addresses=1,
            total_addresses=6,
        ),),
    )]
    assert pools[0].available_addresses == 5


@pytest.mark.parametrize(
    "output",
    [
        _INVALID,
        "show ip dhcp pool\nRouter#",
        _REAL_PT_9_0_1_0858_POOL.replace(
            " Pending event                  : none\n",
            " Unknown field                  : value\n"
            " Pending event                  : none\n",
        ),
        _REAL_PT_9_0_1_0858_POOL.replace(" Total addresses                : 6", ""),
        _REAL_PT_9_0_1_0858_POOL.replace(
            "Pool MCP_DHCP_POOL_Q :",
            "Pool MCP_DHCP_POOL_Q :\nPool MCP_DHCP_POOL_Q :",
        ),
        _REAL_PT_9_0_1_0858_POOL.replace(
            " 0    / 1     / 6", " 0    / 1     / 7",
        ),
    ],
)
def test_parser_mismatch_or_unknown_shape_is_unobservable(output: str) -> None:
    assert parse_show_ip_dhcp_pool(output) is None


class _ProductQuery:
    def __init__(self, result: IosCommandResult) -> None:
        self.result = result
        self.calls = []

    def execute(self, device_name, query_id, *, interface=""):
        self.calls.append((device_name, query_id, interface))
        return self.result


def _product_show(
    output: str = _REAL_PT_9_0_1_0858_POOL,
    *,
    executed: bool = True,
    fresh: bool = True,
    complete: bool = True,
    identity: DeviceIdentityProvenance = DeviceIdentityProvenance.CONFIRMED_UNIQUE,
) -> IosCommandResult:
    return IosCommandResult(
        device_name="R1",
        query_id=OperationalQueryId.SHOW_IP_DHCP_POOL,
        executed=executed,
        output=output,
        session_state=IosSessionState.EXEC_PROMPT_READY,
        fresh_output_observed=fresh,
        output_complete=complete,
        device_identity_provenance=identity.value,
    )


def _runtime_with_product_show(show: IosCommandResult):
    sent = []
    runtime = PacketTracerEnterpriseConfigurationRuntime(
        query_inventory=lambda: [],
        send=lambda payload: sent.append(payload) or True,
        send_and_wait=lambda _payload, _timeout: None,
    )
    query = _ProductQuery(show)
    runtime._ios = query
    return runtime, query, sent


def test_runtime_observer_keeps_presence_range_and_space_independent() -> None:
    runtime, query, sent = _runtime_with_product_show(_product_show())

    observed = runtime.read_dhcp_pool(
        "R1", "MCP_DHCP_POOL_Q", "198.18.250.2", "198.18.250.6",
    )

    assert observed.pool_present is True
    assert observed.requested_range_covered is True
    assert observed.range_start == "198.18.250.1"
    assert observed.range_end == "198.18.250.6"
    assert observed.total_addresses == 6
    assert observed.leased_addresses == 0
    assert observed.excluded_addresses == 1
    assert observed.available_addresses == 5
    assert observed.fresh_evidence
    assert observed.output_complete
    assert query.calls == [(
        "R1", OperationalQueryId.SHOW_IP_DHCP_POOL, "",
    )]
    assert sent == []


@pytest.mark.parametrize(
    "show",
    [
        _product_show(executed=False),
        _product_show(fresh=False),
        _product_show(complete=False),
        _product_show(identity=DeviceIdentityProvenance.MISMATCHED),
        _product_show(output=_INVALID),
        _product_show(output="show ip dhcp pool\nRouter#"),
    ],
)
def test_unusable_product_read_never_becomes_an_empty_or_absent_pool(show) -> None:
    runtime, _, _ = _runtime_with_product_show(show)

    observed = runtime.read_dhcp_pool(
        "R1", "VOICEAB_VOICE", "10.93.0.10", "10.93.0.254",
    )

    assert observed.pool_present is None
    assert observed.requested_range_covered is None
    assert observed.available_addresses is None


def test_a_pool_printed_in_another_case_is_not_reported_as_absent() -> None:
    # A false `pool_present=False` is not a neutral miss: the ladder publishes
    # it as CONTRADICTED, which is a strong causal claim about the router. The
    # parser already refuses a table holding two casefold-equal pool
    # identities, so matching the requested name the same way cannot be
    # ambiguous -- and it cannot invent an absence out of letter case either.
    runtime, _, _ = _runtime_with_product_show(_product_show(
        output=_REAL_PT_9_0_1_0858_POOL.replace(
            "Pool MCP_DHCP_POOL_Q :", "Pool mcp_dhcp_pool_q :",
        ),
    ))

    observed = runtime.read_dhcp_pool(
        "R1", "MCP_DHCP_POOL_Q", "198.18.250.2", "198.18.250.6",
    )

    assert observed.pool_present is True
    assert observed.requested_range_covered is True
    assert observed.available_addresses == 5


def test_expected_pool_absence_is_authoritative_only_in_a_readable_nonempty_table() -> None:
    runtime, _, _ = _runtime_with_product_show(_product_show())

    observed = runtime.read_dhcp_pool(
        "R1", "VOICEAB_VOICE", "10.93.0.10", "10.93.0.254",
    )

    assert observed.pool_present is False
    assert observed.requested_range_covered is None
    assert observed.available_addresses is None


def test_an_ios_rejection_means_unsupported_not_an_empty_pool() -> None:
    assert classify_dhcp_pool_command_support(
        _show(_INVALID),
    ) is DhcpPoolCommandSupport.NO


@pytest.mark.parametrize(
    "show",
    [
        _show(executed=False),
        _show(fresh=False),
        _show(complete=False),
        _show(identity=DeviceIdentityProvenance.NOT_OBSERVED),
        _show(identity=DeviceIdentityProvenance.AMBIGUOUS),
        _show(identity=DeviceIdentityProvenance.MISMATCHED),
    ],
)
def test_an_unusable_capture_keeps_command_support_unobservable(show) -> None:
    assert classify_dhcp_pool_command_support(
        show,
    ) is DhcpPoolCommandSupport.UNOBSERVABLE


@dataclass(frozen=True)
class _ModeState:
    observed: bool = True
    simulation_mode: bool = False


class _Mode:
    def __init__(self, states=None) -> None:
        self._states = list(states or [_ModeState(), _ModeState()])
        self.reads = 0

    def read_simulation_state(self):
        self.reads += 1
        return self._states.pop(0)


class _Physical:
    def __init__(self, *, preexisting=()) -> None:
        self.preexisting = list(preexisting)
        self.live: list[str] = []
        self.created: list[str] = []
        self.removed: list[str] = []

    def observe_workspace(self):
        return PhysicalWorkspaceObservation(
            devices=[
                PhysicalWorkspaceDeviceObservation(name=name, model="2811")
                for name in [*self.preexisting, *self.live]
            ],
            links=[],
        )

    def ensure_device(self, device):
        self.created.append(device.name)
        self.live.append(device.name)
        return PhysicalMutationResult(
            target_id=device.id,
            target_kind=PhysicalObjectKind.DEVICE,
            disposition=MutationDisposition.CHANGED,
            applied=True,
        )

    def remove_device(self, device):
        if device.name in self.live:
            self.live.remove(device.name)
        self.removed.append(device.name)
        return PhysicalMutationResult(
            target_id=device.id,
            target_kind=PhysicalObjectKind.DEVICE,
            disposition=MutationDisposition.CHANGED,
            applied=True,
        )


class _Configuration:
    def __init__(self, *, applied: bool = True) -> None:
        self.applied = applied
        self.batches: list[list] = []

    def apply_actions(self, actions):
        self.batches.append(list(actions))
        return [
            RuntimeActionMutation(
                action_id=item.id,
                applied=self.applied,
                message="",
            )
            for item in actions
        ]


class _Query:
    def __init__(self, result=None, *, error: Exception | None = None) -> None:
        self.result = result or _show()
        self.error = error
        self.calls: list[tuple[str, IosQualificationQueryId]] = []

    def qualify(self, device_name, query_id):
        self.calls.append((device_name, query_id))
        if self.error is not None:
            raise self.error
        return self.result


def test_qualification_uses_one_typed_pool_action_and_one_read_only_observation() -> None:
    physical = _Physical()
    configuration = _Configuration()
    query = _Query()
    mode = _Mode()

    result = DhcpPoolCommandQualifier(
        physical, configuration, query, mode, name_token="tok",
    ).qualify("2811")

    assert result.command_support is DhcpPoolCommandSupport.YES
    assert result.configuration_applied
    assert result.workspace_restored
    assert result.realtime_restored
    assert physical.created == ["MCP-DHCPPOOLQ-tok"]
    assert physical.removed == ["MCP-DHCPPOOLQ-tok"]
    assert query.calls == [(
        "MCP-DHCPPOOLQ-tok", IosQualificationQueryId.SHOW_IP_DHCP_POOL,
    )]
    assert len(configuration.batches) == 1
    assert len(configuration.batches[0]) == 1
    action = configuration.batches[0][0]
    assert isinstance(action, ConfigureDhcpPool)
    assert action.pool_name == QUALIFICATION_POOL_NAME
    assert action.network == "198.18.250.0"
    assert action.prefix == 29
    assert action.lease_start == "198.18.250.2"
    assert action.lease_end == "198.18.250.6"


def test_a_query_exception_still_removes_only_the_owned_disposable() -> None:
    physical = _Physical()

    result = DhcpPoolCommandQualifier(
        physical,
        _Configuration(),
        _Query(error=RuntimeError("observer failed")),
        _Mode(),
        name_token="tok",
    ).qualify("2811")

    assert result.command_support is DhcpPoolCommandSupport.UNOBSERVABLE
    assert result.workspace_restored
    assert physical.live == []
    assert physical.removed == ["MCP-DHCPPOOLQ-tok"]
    assert any("observer failed" in item for item in result.errors)


def test_nonempty_workspace_refuses_every_mutation_and_query() -> None:
    physical = _Physical(preexisting=("USER-R1",))
    configuration = _Configuration()
    query = _Query()

    result = DhcpPoolCommandQualifier(
        physical, configuration, query, _Mode(), name_token="tok",
    ).qualify("2811")

    assert result.command_support is DhcpPoolCommandSupport.UNOBSERVABLE
    assert physical.created == []
    assert physical.removed == []
    assert configuration.batches == []
    assert query.calls == []


def test_simulation_mode_refuses_every_mutation_and_query() -> None:
    physical = _Physical()
    configuration = _Configuration()
    query = _Query()

    result = DhcpPoolCommandQualifier(
        physical,
        configuration,
        query,
        _Mode(states=[_ModeState(simulation_mode=True)]),
        name_token="tok",
    ).qualify("2811")

    assert result.command_support is DhcpPoolCommandSupport.UNOBSERVABLE
    assert physical.created == []
    assert configuration.batches == []
    assert query.calls == []


# --- provenance of the LIVE qualification this parser was built from --------
#
# `data/` is ignored, so the artefact that measured the command can be gone on
# the next checkout.  The tracked record is what keeps the measurement's
# identity, exactly as `positive_voice_ab_runs.json` does for the raw runs.

import hashlib  # noqa: E402
import json  # noqa: E402
from pathlib import Path  # noqa: E402

_ROOT = Path(__file__).resolve().parents[1]
_QUALIFICATION = (
    _ROOT / "docs" / "reference" / "cp-scale"
    / "dhcp_pool_command_qualification.json"
)
_RAW_DIRECTORY = _ROOT / "data" / "cp-scale"


def _qualification() -> dict:
    return json.loads(_QUALIFICATION.read_text(encoding="utf-8"))


def test_the_qualification_record_pins_the_head_and_digest_it_measured() -> None:
    record = _qualification()

    assert record["schema"] == "cp-scale-command-qualification-v1"
    assert record["command"] == "show ip dhcp pool"
    assert record["outcome"] == "COMMAND_SUPPORTED"
    assert record["packet_tracer_version"] == "9.0.1.0858"
    assert record["source_head"] == "ce222edd72bc3779a6141382d22653e5555f4f7c"
    assert len(record["sha256"]) == 64
    assert record["live_capture"] == {
        "executed": True,
        "fresh_output_observed": True,
        "output_complete": True,
        "device_identity_provenance": "confirmed_unique",
        "dispatch_attempts": 1,
    }


def test_the_qualification_record_keeps_the_unexposed_fields_unexposed() -> None:
    # The parser may only claim what the fixture prints.  Recording the
    # boundary is what stops a later session reading a supported command as a
    # verified pool CONFIGURATION.
    record = _qualification()

    assert set(record["does_not_expose"]) == {
        "DEFAULT_ROUTER", "EXCLUDED_RANGES", "OPTION150",
    }
    assert "EXCLUDED_ADDRESS_COUNT" in record["exposes"]
    assert "EXCLUDED_RANGES" not in record["exposes"]


def test_the_retained_qualification_artefact_still_hashes_to_the_record() -> None:
    record = _qualification()
    raw = _RAW_DIRECTORY / record["filename"]
    if not raw.is_file():
        pytest.skip("the ignored qualification artefact is absent here")

    assert hashlib.sha256(raw.read_bytes()).hexdigest() == record["sha256"]
