"""PoE-3B bounded execution, fixture accounting and cleanup."""

from __future__ import annotations

from dataclasses import replace
import hashlib
import importlib
import json
from types import SimpleNamespace

import pytest

from tests.poe3b_capacity_runner_helpers import (
    facts,
    measured_capture,
    packet_tracer_processes,
    runner,
)


def _factory_types():
    return importlib.import_module(
        "packet_tracer_mcp.infrastructure.execution.factory_module_preparation"
    )


def _factory_results(device_name="SW", *, target_determined=True, verified=True):
    factory = _factory_types()
    target = factory.FactoryModuleTarget(
        container_ordinal=0,
        index=1,
        module_type=4,
    )
    empty = factory.FactoryModuleSlotObservation(
        container_ordinal=0,
        index=1,
        module_type=4,
        state=factory.FactoryModuleSlotState.EMPTY,
    )
    installed = replace(
        empty,
        state=factory.FactoryModuleSlotState.OCCUPIED,
        descriptor_model="AC-POWER-SUPPLY",
        descriptor_model_observed=True,
    )
    before = factory.FactoryModuleObservation(
        operation=factory.FactoryModuleOperation.OBSERVE_MODULE_SLOTS,
        device_name=device_name,
        device_model="3650-24PS",
        packet_tracer_build="9.0.1.0858",
        required_module_model="AC-POWER-SUPPLY",
        required_module_type=4,
        observed=True,
        slots=(empty,),
        candidate_targets=((target,) if target_determined else (target, replace(target, index=2))),
        target_container_ordinal=(0 if target_determined else None),
        target_index=(1 if target_determined else None),
        target_determined=target_determined,
        message=("deterministic" if target_determined else "indistinguishable"),
    )
    installation = factory.FactoryModuleInstallation(
        operation=factory.FactoryModuleOperation.INSTALL_FACTORY_MODULE,
        device_name=device_name,
        device_model="3650-24PS",
        packet_tracer_build="9.0.1.0858",
        requested_identity="AC-POWER-SUPPLY",
        target=target,
        attempted=True,
        acknowledged=True,
        native_ack=True,
        power_was_on=True,
        power_restored=True,
    )
    after = replace(
        before,
        slots=(installed,),
        candidate_targets=(),
        installed_targets=(target,),
        already_prepared=True,
    )
    verification = factory.FactoryModuleVerification(
        operation=factory.FactoryModuleOperation.VERIFY_FACTORY_MODULE,
        device_name=device_name,
        device_model="3650-24PS",
        packet_tracer_build="9.0.1.0858",
        required_module_model="AC-POWER-SUPPLY",
        required_module_type=4,
        expected_available_watts_before=0.0,
        expected_available_watts=390.0,
        before=before,
        installation=installation,
        after=after,
        slot_container_effect=verified,
        inventory_coherent=verified,
        installed_identity_observed=("AC-POWER-SUPPLY" if verified else None),
        installed_identity_matches=(True if verified else None),
        verified=verified,
        message="verified" if verified else "not verified",
    )
    return before, installation, verification


def _capacity_capture(runner, plan, label, switch_name, *, available, powered):
    target_ports = {binding.switch_port for binding in plan.bindings}
    mode = "never" if label == "NEVER" else "auto"
    rows = []
    for index in range(1, 25):
        interface = f"Gig1/0/{index}"
        long_name = f"GigabitEthernet1/0/{index}"
        if mode == "never" and long_name in target_ports:
            continue
        delivering = powered and long_name in target_ports
        rows.append(
            f"{interface:<9} {'auto':<6} "
            f"{('on' if delivering else 'off'):<10} "
            f"{('10.0' if delivering else '0.0'):<7} "
            f"{('IP Phone 7960' if delivering else 'n/a'):<19} "
            f"{('3' if delivering else 'n/a'):<5} 30.0"
        )
    used = 110.0 if powered else 0.0
    raw = (
        "show power inline\n"
        f"Available:{available:.1f}(w)  Used:{used:.1f}(w)  "
        f"Remaining:{available - used:.1f}(w)\n\n"
        "Interface Admin  Oper       Power   Device              Class Max\n"
        "                            (Watts)\n"
        "--------- ------ ---------- ------- ------------------- ----- ----\n"
        + "\n".join(rows)
        + "\nSwitch#\nSwitch#"
    )
    table = runner.parse_show_power_inline(raw)
    ports = []
    for binding in plan.bindings:
        row = table.row_for(binding.switch_port)
        ports.append({
            "port": binding.switch_port,
            "row": (
                dict(
                    interface=row.interface,
                    admin=row.admin,
                    oper=row.oper,
                    power_watts=row.power_watts,
                    device=row.device,
                    power_class=row.power_class,
                    max_watts=row.max_watts,
                )
                if row is not None else None
            ),
            "delivery": runner.classify_poe_inline_delivery(
                raw,
                binding.switch_port,
                capture_complete=True,
            ).value,
        })
    dispatch = dict(
        output=raw,
        pager_continuation="not_encountered",
        pager_pages_captured=1,
        expected_prompt="Switch#",
        session_state="exec_prompt_ready",
        truncated_by_pager=False,
        observed_device_name=switch_name,
        device_identity_provenance="confirmed_unique",
        dispatch_classification="dispatched",
        echo_observed="show power inline",
        query_id="qualification_show_power_inline",
        executed=True,
        fresh_output_observed=True,
    )
    observation = dict(
        ports=ports,
        raw_output=raw,
        command_result=dispatch,
        capture_complete=True,
        device_identity_provenance="confirmed_unique",
        observed_device_name=switch_name,
        switch_identity=switch_name,
        fresh_output_observed=True,
        status="observed",
        refusal_reason="",
    )

    class Capture(SimpleNamespace):
        def model_dump(self, **_kwargs):
            return dict(vars(self))

    return Capture(
        observation=observation,
        repeat_observation=json.loads(json.dumps(observation)),
        expected_prompt="Switch#",
        stable=True,
        raw_file=label.lower() + ".txt",
        raw_sha256=hashlib.sha256(raw.encode()).hexdigest(),
        table_completeness={key: True for key in runner.COMPLETENESS_KEYS},
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


class _Instrumented3650Transport:
    def __init__(self, runner, plan, *, target_determined=True,
                 after_available=390.0, capture_error_label=None,
                 readiness_error_after_install=False) -> None:
        self.runner = runner
        self.plan = plan
        self.target_determined = target_determined
        self.after_available = after_available
        self.capture_error_label = capture_error_label
        self.readiness_error_after_install = readiness_error_after_install
        self.calls = []
        self.names: set[str] = set()
        self.factory = None
        self.installed = False

    def record(self, operation):
        self.calls.append(operation)

    def bridge_healthy(self):
        self.record(self.runner.PoE3BSessionOperation.TRANSPORT_HEALTH)
        return True

    def mailbox_entries(self):
        self.record(self.runner.PoE3BSessionOperation.MAILBOX_OBSERVATION)
        return ()

    def start_control_bridge(self):
        self.record(self.runner.PoE3BSessionOperation.CONTROL_BRIDGE_START)
        return {"authenticated_status": 200, "unauthenticated_status": 401}

    def stop_control_bridge(self):
        self.record(self.runner.PoE3BSessionOperation.CONTROL_BRIDGE_STOP)

    def environment(self):
        self.record(self.runner.PoE3BSessionOperation.ENVIRONMENT_OBSERVATION)
        return dict(
            devices=len(self.names),
            links=0,
            saved_filename="",
            simulation_mode=False,
            pt_version=self.plan.packet_tracer_build,
        )

    def inventory_fingerprint(self):
        self.record(self.runner.PoE3BSessionOperation.INVENTORY_OBSERVATION)
        return "a" * 64 + "|"

    def device_names(self):
        self.record(self.runner.PoE3BSessionOperation.DEVICE_NAMES_OBSERVATION)
        return frozenset(self.names)

    def create_device(self, model, name, required_ports, *, arm):
        self.record(self.runner.PoE3BSessionOperation.FIXTURE_DEVICE_CREATE)
        self.names.add(name)

        class Dump(SimpleNamespace):
            def model_dump(self, **_kwargs):
                return dict(vars(self))

        return Dump(name=name, model=model, observed_ports=list(required_ports))

    def create_link(self, switch, switch_port, endpoint, endpoint_port):
        self.record(self.runner.PoE3BSessionOperation.FIXTURE_LINK_CREATE)

        class Dump(SimpleNamespace):
            def model_dump(self, **_kwargs):
                return dict(vars(self))

        return Dump(first=switch_port, second=endpoint_port)

    def wait_until_ready(self, switch_name, *, timeout_seconds):
        self.record(self.runner.PoE3BSessionOperation.DEVICE_READINESS)
        if self.installed and self.readiness_error_after_install:
            raise TimeoutError("device never reported ready after the mutation")

        class Dump(SimpleNamespace):
            def model_dump(self, **_kwargs):
                return dict(vars(self))

        return Dump(state="operational_ready", attempts=1)

    def observe_factory_module(self, device_name, device_model):
        self.record(self.runner.PoE3BSessionOperation.OBSERVE_MODULE_SLOTS)
        self.factory = _factory_results(
            device_name,
            target_determined=self.target_determined,
        )
        return self.factory[0]

    def install_factory_module(self, observation):
        self.record(self.runner.PoE3BSessionOperation.INSTALL_FACTORY_MODULE)
        assert self.factory is not None and observation is self.factory[0]
        self.installed = True
        return self.factory[1]

    def verify_factory_module(self, observation, installation):
        self.record(self.runner.PoE3BSessionOperation.VERIFY_FACTORY_MODULE)
        assert self.factory is not None
        assert observation is self.factory[0]
        assert installation is self.factory[1]
        return self.factory[2]

    def apply_inline_mode(self, switch_name, switch_ports, mode):
        self.record(self.runner.PoE3BSessionOperation.INLINE_MODE_APPLY)

    def capture_inline_status(self, switch_name, switch_ports, label):
        self.record(self.runner.PoE3BSessionOperation.INLINE_CAPTURE)
        if label == self.capture_error_label:
            raise ValueError("synthetic typed capture refusal")
        available = (
            0.0 if label == "PSU_BEFORE"
            else self.after_available if label == "PSU_AFTER"
            else 390.0
        )
        endpoints_created = len(self.names) > 1
        powered = label in {"AUTO_1", "AUTO_2", "RESTORE"} and endpoints_created
        return _capacity_capture(
            self.runner,
            self.plan,
            label,
            switch_name,
            available=available,
            powered=powered,
        )

    def delete_device(self, name):
        self.record(self.runner.PoE3BSessionOperation.FIXTURE_DEVICE_DELETE)
        existed = name in self.names
        self.names.discard(name)
        return existed

    def retire_session_residue(self, preexisting):
        self.record(self.runner.PoE3BSessionOperation.RESIDUE_RETIRE)
        return ()

    def wait_for_inventory_fingerprint(self, expected):
        self.record(self.runner.PoE3BSessionOperation.INVENTORY_RESTORATION)
        return expected

    def collect_completed(self):
        self.record(self.runner.PoE3BSessionOperation.IPC_DRAIN)

    def transport_problems(self):
        self.record(self.runner.PoE3BSessionOperation.TRANSPORT_PROBLEMS)
        return ()


def _execute_3650(runner, tmp_identity, *, target_determined=True,
                  after_available=390.0, capture_error_label=None,
                  readiness_error_after_install=False):
    plan = runner.governed_plan("3650-24PS")
    baseline, _restoration, _final = facts()
    artifacts = runner.reserve_artifacts(tmp_identity)
    transport = _Instrumented3650Transport(
        runner,
        plan,
        target_determined=target_determined,
        after_available=after_available,
        capture_error_label=capture_error_label,
        readiness_error_after_install=readiness_error_after_install,
    )
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
    return execution, session, transport


def test_3650_confirms_factory_power_delta_before_creating_any_phone(
    runner,
) -> None:
    execution, session, transport = _execute_3650(runner, "offline-3650-positive")

    observed = tuple(record.operation for record in session.dispatches)
    install_index = observed.index(
        runner.PoE3BSessionOperation.INSTALL_FACTORY_MODULE,
    )
    first_phone_index = observed.index(
        runner.PoE3BSessionOperation.FIXTURE_DEVICE_CREATE,
        install_index + 1,
    )
    readiness_index = observed.index(
        runner.PoE3BSessionOperation.DEVICE_READINESS,
        install_index + 1,
    )
    verification_index = observed.index(
        runner.PoE3BSessionOperation.VERIFY_FACTORY_MODULE,
        install_index + 1,
    )
    after_capture_index = observed.index(
        runner.PoE3BSessionOperation.INLINE_CAPTURE,
        install_index + 1,
    )
    assert execution.problems == []
    assert execution.snapshot is not None
    assert execution.psu_hypothesis["confirmed"] is True
    assert execution.psu_hypothesis["available_before_watts"] == 0.0
    assert execution.psu_hypothesis["available_after_watts"] == 390.0
    assert execution.psu_hypothesis["available_delta_watts"] == 390.0
    assert install_index < readiness_index < verification_index
    assert verification_index < after_capture_index < first_phone_index
    assert observed.count(
        runner.PoE3BSessionOperation.INSTALL_FACTORY_MODULE,
    ) == 1
    assert observed.count(
        runner.PoE3BSessionOperation.FIXTURE_DEVICE_CREATE,
    ) == 12
    assert observed == tuple(transport.calls)
    assert set(execution.raw_files) >= {"psu_before.txt", "psu_after.txt"}


def test_3650_retains_the_irreversible_mutation_record_when_boot_fails(
    runner,
) -> None:
    """A post-mutation boot failure must never erase the PSU attempt."""

    execution, session, _transport = _execute_3650(
        runner,
        "offline-3650-boot-timeout",
        readiness_error_after_install=True,
    )

    observed = tuple(record.operation for record in session.dispatches)
    assert observed.count(
        runner.PoE3BSessionOperation.INSTALL_FACTORY_MODULE,
    ) == 1
    assert runner.PoE3BSessionOperation.VERIFY_FACTORY_MODULE not in observed
    assert any("TimeoutError" in problem for problem in execution.problems)
    # The attempt that actually reached Packet Tracer stays enumerable.
    installation = execution.factory_preparation.get("installation")
    assert installation is not None
    assert installation["attempted"] is True
    assert installation["requested_identity"] == "AC-POWER-SUPPLY"
    assert "verification" not in execution.factory_preparation
    assert execution.snapshot is None


def test_3650_ambiguous_target_stops_before_module_or_phone_mutation(
    runner,
) -> None:
    execution, session, _transport = _execute_3650(
        runner,
        "offline-3650-ambiguous",
        target_determined=False,
    )

    observed = tuple(record.operation for record in session.dispatches)
    assert execution.snapshot is None
    assert any("not one new deterministic insertion" in item for item in execution.problems)
    assert runner.PoE3BSessionOperation.INSTALL_FACTORY_MODULE not in observed
    assert runner.PoE3BSessionOperation.VERIFY_FACTORY_MODULE not in observed
    assert observed.count(
        runner.PoE3BSessionOperation.FIXTURE_DEVICE_CREATE,
    ) == 1
    assert execution.restoration["inventory_restored"] is True


def test_3650_wrong_power_delta_stops_after_one_install_and_before_phones(
    runner,
) -> None:
    execution, session, _transport = _execute_3650(
        runner,
        "offline-3650-wrong-delta",
        after_available=389.0,
    )

    observed = tuple(record.operation for record in session.dispatches)
    assert execution.snapshot is None
    assert execution.psu_hypothesis["confirmed"] is False
    assert observed.count(
        runner.PoE3BSessionOperation.INSTALL_FACTORY_MODULE,
    ) == 1
    assert observed.count(
        runner.PoE3BSessionOperation.FIXTURE_DEVICE_CREATE,
    ) == 1


def test_3650_preserves_the_acquired_slot_observation_if_power_capture_refuses(
    runner,
) -> None:
    """Moving persistence after capture would lose the causal pre-mutation fact."""

    execution, session, _transport = _execute_3650(
        runner,
        "offline-3650-capture-refusal",
        capture_error_label="PSU_BEFORE",
    )

    observed = tuple(record.operation for record in session.dispatches)
    assert execution.snapshot is None
    assert execution.factory_preparation["before"]["target_determined"] is True
    assert execution.factory_preparation["before"]["target_index"] == 1
    assert "power_before" not in execution.factory_preparation
    assert runner.PoE3BSessionOperation.INSTALL_FACTORY_MODULE not in observed
