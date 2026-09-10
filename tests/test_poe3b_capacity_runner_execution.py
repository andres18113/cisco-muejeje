"""PoE-3B bounded execution, fixture accounting and cleanup."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from tests.poe3b_capacity_runner_helpers import (
    facts,
    measured_capture,
    packet_tracer_processes,
    runner,
)


@pytest.mark.parametrize("model,count", [("3560-24PS", 21), ("3650-24PS", 11)])
def test_fixture_has_one_phone_and_link_per_governed_binding(
    runner,
    model,
    count,
):
    plan = runner.governed_plan(model)
    made, links = [], []

    class Device(SimpleNamespace):
        def model_dump(self, **kwargs):
            return vars(self)

    def create(model, name, ports, **kwargs):
        made.append((model, name, ports))
        return Device(model=model, name=name)

    def link(switch, port, phone, endpoint_port):
        links.append((port, endpoint_port))
        return Device(port=port)

    transport = SimpleNamespace(create_device=create, create_link=link)
    session = runner.PacketTracerPoE3BSession(
        "offline",
        switch_ports=tuple(binding.switch_port for binding in plan.bindings),
        endpoint_role="PH",
        transport=transport,
    )
    session.create_fixture(plan.candidate_model, plan.bindings)
    assert len(made) == count + 1 and len(links) == count
    assert made[0] == (
        model,
        session.switch_name,
        tuple(binding.switch_port for binding in plan.bindings),
    )
    assert all(item[0] == "7960" and item[2] == ("Switch",) for item in made[1:])
    assert session.attempted_device_names == tuple(item[1] for item in made)
    assert session.created_device_names == session.attempted_device_names
    assert len(set(session.attempted_device_names)) == count + 1
    assert links == [
        (binding.switch_port, "Switch") for binding in plan.bindings
    ]


def test_cleanup_attempts_every_identity_even_after_a_deletion_failure(runner):
    plan = runner.governed_plan("3560-24PS")
    bindings = plan.bindings[:3]
    calls = []

    class Device(SimpleNamespace):
        def model_dump(self, **kwargs):
            return dict(vars(self))

    transport = SimpleNamespace(
        create_device=lambda model, name, ports, **kwargs: Device(
            model=model,
            name=name,
        ),
        create_link=lambda *args: Device(linked=True),
    )
    session = runner.PacketTracerPoE3BSession(
        "offline-cleanup",
        switch_ports=tuple(binding.switch_port for binding in bindings),
        transport=transport,
    )
    session.create_fixture(plan.candidate_model, bindings)
    switch, phone1, phone2, phone3 = session.attempted_device_names

    def delete(name):
        calls.append(name)
        if name == phone2:
            raise RuntimeError("controlled failure")
        return name != phone1

    transport.delete_device = delete

    cleanup = session.cleanup_fixture()

    assert calls == [phone3, phone2, phone1, switch]
    assert cleanup.deleted == (phone3, switch)
    assert len(cleanup.problems) == 2


def test_partial_fixture_tracks_created_identity_before_link_failure(runner):
    plan = runner.governed_plan("3560-24PS")

    class Device(SimpleNamespace):
        def model_dump(self, **kwargs):
            return dict(vars(self))

    def link(*args):
        raise RuntimeError("link failure")

    session = runner.PacketTracerPoE3BSession(
        "offline-partial",
        switch_ports=tuple(binding.switch_port for binding in plan.bindings),
        transport=SimpleNamespace(
            create_device=lambda model, name, *args, **kwargs: Device(
                model=model,
                name=name,
            ),
            create_link=link,
        ),
    )
    with pytest.raises(RuntimeError, match="link failure"):
        session.create_fixture(plan.candidate_model, plan.bindings)
    assert session.attempted_device_names == session.created_device_names
    assert session.attempted_device_names == (
        session.switch_name,
        session.endpoint_prefix + "-1",
    )


def test_runner_cycle_uses_only_the_instrumented_bounded_session_transport(
    runner,
) -> None:
    plan = runner.governed_plan("3560-24PS")
    baseline, _restoration, _final = facts()
    artifacts = runner.reserve_artifacts("offline-e2e")

    class Dump(SimpleNamespace):
        def model_dump(self, **kwargs):
            return dict(vars(self))

    class InstrumentedPoE3BTransport:
        def __init__(self):
            self.calls = []

        def record(self, operation):
            self.calls.append(operation)

        def bridge_healthy(self):
            self.record(runner.PoE3BSessionOperation.TRANSPORT_HEALTH)
            return True

        def mailbox_entries(self):
            self.record(runner.PoE3BSessionOperation.MAILBOX_OBSERVATION)
            return ()

        def start_control_bridge(self):
            self.record(runner.PoE3BSessionOperation.CONTROL_BRIDGE_START)
            return dict(
                authenticated_status=200,
                unauthenticated_status=401,
                active_pt_transport="instrumented_session_transport",
            )

        def stop_control_bridge(self):
            self.record(runner.PoE3BSessionOperation.CONTROL_BRIDGE_STOP)

        def environment(self):
            self.record(runner.PoE3BSessionOperation.ENVIRONMENT_OBSERVATION)
            return dict(
                devices=0,
                links=0,
                saved_filename="",
                simulation_mode=False,
                pt_version=plan.packet_tracer_build,
            )

        def inventory_fingerprint(self):
            self.record(runner.PoE3BSessionOperation.INVENTORY_OBSERVATION)
            return "a" * 64 + "|"

        def device_names(self):
            self.record(runner.PoE3BSessionOperation.DEVICE_NAMES_OBSERVATION)
            return frozenset()

        def create_device(self, model, name, required_ports, *, arm):
            self.record(runner.PoE3BSessionOperation.FIXTURE_DEVICE_CREATE)
            return Dump(
                name=name,
                model=model,
                observed_ports=list(required_ports),
            )

        def create_link(self, switch, switch_port, endpoint, endpoint_port):
            self.record(runner.PoE3BSessionOperation.FIXTURE_LINK_CREATE)
            return Dump(
                first=dict(device_name=switch.name, port=switch_port),
                second=dict(device_name=endpoint.name, port=endpoint_port),
            )

        def wait_until_ready(self, switch_name, *, timeout_seconds):
            self.record(runner.PoE3BSessionOperation.DEVICE_READINESS)
            return Dump(state="operational_ready", attempts=1)

        def apply_inline_mode(self, switch_name, switch_ports, mode):
            self.record(runner.PoE3BSessionOperation.INLINE_MODE_APPLY)

        def capture_inline_status(self, switch_name, switch_ports, label):
            self.record(runner.PoE3BSessionOperation.INLINE_CAPTURE)
            capture = measured_capture(runner, plan, label)
            for observation in (
                capture.observation,
                capture.repeat_observation,
            ):
                observation["switch_identity"] = switch_name
                observation["observed_device_name"] = switch_name
                observation["command_result"][
                    "observed_device_name"
                ] = switch_name
            capture.table_completeness = runner.completeness(
                capture.observation,
                capture.expected_prompt,
                capture.stable,
                switch_name,
            )
            return capture

        def delete_device(self, name):
            self.record(runner.PoE3BSessionOperation.FIXTURE_DEVICE_DELETE)
            return True

        def retire_session_residue(self, preexisting):
            self.record(runner.PoE3BSessionOperation.RESIDUE_RETIRE)
            return ()

        def wait_for_inventory_fingerprint(self, expected):
            self.record(runner.PoE3BSessionOperation.INVENTORY_RESTORATION)
            return expected

        def collect_completed(self):
            self.record(runner.PoE3BSessionOperation.IPC_DRAIN)

        def transport_problems(self):
            self.record(runner.PoE3BSessionOperation.TRANSPORT_PROBLEMS)
            return ()

    transport = InstrumentedPoE3BTransport()
    session = runner.PacketTracerPoE3BSession(
        artifacts.run_id,
        switch_ports=tuple(binding.switch_port for binding in plan.bindings),
        endpoint_role="PH",
        transport=transport,
    )
    source = dict(
        source_branch=baseline["source_branch"],
        source_head=baseline["local_head"],
        source_tree=baseline["source_tree"],
        upstream=baseline["upstream"],
        upstream_head=baseline["upstream_head"],
        worktree_clean=True,
    )
    execution = runner.execute_governed_qualification(
        session=session,
        plan=plan,
        baseline=baseline,
        artifacts=artifacts,
        process_probe=packet_tracer_processes,
        source_state_probe=lambda: dict(source),
    )

    observed = tuple(record.operation for record in session.dispatches)
    assert execution.problems == []
    assert execution.snapshot is not None
    assert execution.snapshot_path is None
    assert observed == tuple(transport.calls)
    assert runner.PoE3BSessionOperation.WORKSPACE_FILE_OPERATION not in observed
    assert observed.count(runner.PoE3BSessionOperation.FIXTURE_DEVICE_CREATE) == 22
    assert observed.count(runner.PoE3BSessionOperation.FIXTURE_LINK_CREATE) == 21
    assert observed.count(runner.PoE3BSessionOperation.INLINE_MODE_APPLY) == 4
    assert observed.count(runner.PoE3BSessionOperation.INLINE_CAPTURE) == 4
    assert observed.count(runner.PoE3BSessionOperation.FIXTURE_DEVICE_DELETE) == 22
    assert execution.file_operation_ledger.ephemeral_safe
