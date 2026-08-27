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
    IosCommandResult,
    IosQualificationQueryId,
    IosSessionState,
    OperationalQueryId,
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


def test_the_candidate_is_one_closed_command_not_a_product_or_raw_input() -> None:
    assert ControlledIosExecutor.qualification_command(
        IosQualificationQueryId.SHOW_IP_DHCP_POOL,
    ) == "show ip dhcp pool"
    assert "SHOW_IP_DHCP_POOL" not in OperationalQueryId.__members__

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
