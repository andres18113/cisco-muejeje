"""Exact campaign ceilings and the plan-derived E4/cleanup call bound."""

from __future__ import annotations

from packet_tracer_mcp.application.use_cases.prepare_server_pt_commissioning import (
    prepare_server_pt_commissioning,
)


def test_phase_allowances_fit_the_charter_without_borrowing_acceptance_reserve():
    """The 35/36 plan and phase channel caps bound every setup/cleanup call."""
    from packet_tracer_mcp.application.use_cases.server_pt_phase_budget import (
        derive_phase_budget,
    )

    bundle = prepare_server_pt_commissioning(
        30, "COLD_HTTP_0f1e2d3c4b5a69788796a5b4c3d2e1f0"
    )
    budget = derive_phase_budget(bundle)

    assert budget.e4_max_operations == 935
    assert budget.e5_max_operations == 3343
    assert (
        budget.e4_max_operations + budget.e5_max_operations
        <= budget.setup_max_operations
    )
    assert budget.prequalification_structural_max_operations == 203
    assert budget.prequalification_structural_max_seconds < 300
    assert budget.setup_coded_wait_seconds == 1484.25
    from packet_tracer_mcp.infrastructure.execution.product_channel import (
        INVENTORY_TIMEOUT_SECONDS,
    )

    assert INVENTORY_TIMEOUT_SECONDS == 10.0
    assert budget.cleanup_structural_max_operations == 73
    assert budget.prequalification_max_operations + budget.setup_max_operations == 5000
    assert budget.prequalification_max_seconds + budget.setup_max_seconds == 1800
    assert budget.setup_max_operations - budget.e4_max_operations == 3815
    assert (
        budget.cleanup_structural_max_operations <= budget.cleanup_max_operations == 250
    )
    assert budget.cleanup_max_seconds == 300
    assert budget.cleanup_structural_max_seconds <= 300


def test_setup_can_bound_ios_boot_without_changing_other_runtime_callers():
    """Four switches cannot each spend the generic 90-second wait in setup."""
    from packet_tracer_mcp.infrastructure.execution.enterprise_configuration_runtime import (
        PacketTracerEnterpriseConfigurationRuntime,
    )

    runtime = PacketTracerEnterpriseConfigurationRuntime(
        query_inventory=lambda: [],
        send=lambda _script: True,
        send_and_wait=lambda _script, _timeout: '{"found":true,"booting":true}',
        ios_boot_timeout_seconds=0.0,
    )

    assert runtime._wait_for_ios("HQ-DEFAULT-ACCESS-SW-01") is False


def test_setup_ios_query_has_an_enforced_nested_bridge_call_ceiling():
    """The derived E5 bound counts actual nested IOS calls, not outer queries."""
    from packet_tracer_mcp.infrastructure.execution.ios_terminal import (
        ControlledIosExecutor,
        OperationalQueryId,
    )

    calls = []

    def answer(script, _timeout):
        calls.append(script)
        return '{"found":true,"terminal":true,"prompt":"Switch0#","output":"Switch0#"}'

    executor = ControlledIosExecutor(answer, max_query_calls=1)
    result = executor.execute("Switch0", OperationalQueryId.SHOW_INTERFACES_TRUNK)
    assert len(calls) == 1
    assert result.executed is False
    assert "bridge-call ceiling" in result.failure_reason


def test_setup_ios_query_has_an_absolute_nested_wall_deadline():
    """A single grouped trunk inspection cannot spend unlimited IOS time."""
    from packet_tracer_mcp.infrastructure.execution.ios_terminal import (
        ControlledIosExecutor,
        OperationalQueryId,
    )

    now = [0.0]
    timeouts = []

    def answer(_script, timeout):
        timeouts.append(timeout)
        now[0] += 1.0
        return '{"found":true,"terminal":true,"prompt":"Switch0#","output":"Switch0#"}'

    executor = ControlledIosExecutor(
        answer,
        clock=lambda: now[0],
        sleeper=lambda seconds: now.__setitem__(0, now[0] + seconds),
        max_query_seconds=1.5,
    )
    result = executor.execute("Switch0", OperationalQueryId.SHOW_INTERFACES_TRUNK)
    assert len(timeouts) <= 2
    assert timeouts[-1] <= 0.5
    assert result.executed is False
    assert "wall deadline" in result.failure_reason
