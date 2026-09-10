"""PoE-3B process cohort and frozen-source preflight boundaries."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from tests.poe3b_capacity_runner_helpers import (
    empty_file_ledger,
    facts,
    packet_tracer_processes,
    runner,
)


def test_one_primary_packet_tracer_and_its_exact_helper_are_one_runtime_cohort(
    runner,
    monkeypatch,
) -> None:
    observed = packet_tracer_processes()
    monkeypatch.setattr(runner, "processes", lambda: observed)

    acquired = runner.prove_processes()

    assert acquired == observed
    assert runner.packet_tracer_primary_pids(acquired) == (42,)


@pytest.mark.parametrize(
    "mutation",
    ["second-primary", "wrong-parent", "wrong-executable"],
)
def test_packet_tracer_process_cohort_rejects_unrelated_same_name_processes(
    runner,
    monkeypatch,
    mutation,
) -> None:
    observed = packet_tracer_processes()
    if mutation == "second-primary":
        observed.append(dict(observed[0], ProcessId=44))
    elif mutation == "wrong-parent":
        observed[1]["ParentProcessId"] = 999
    else:
        observed[1]["ExecutablePath"] = r"C:\Other\PacketTracer.exe"
    monkeypatch.setattr(runner, "processes", lambda: observed)

    with pytest.raises(RuntimeError, match="Packet Tracer process cohort"):
        runner.prove_processes()


def test_source_baseline_uses_the_tree_of_the_coherent_captured_sha(
    runner,
    monkeypatch,
) -> None:
    head = "1" * 40
    tree = "2" * 40
    source = {
        "source_branch": runner.BRANCH,
        "source_head": head,
        "source_tree": tree,
        "upstream": runner.UPSTREAM,
        "upstream_head": head,
        "worktree_clean": True,
    }
    monkeypatch.setattr(runner, "current_source_state", lambda: dict(source))
    calls: list[tuple[str, ...]] = []

    def command(*arguments: str) -> str:
        calls.append(arguments)
        if arguments[:3] == ("git", "merge-base", "--is-ancestor"):
            return ""
        if arguments[:2] == ("gh", "run"):
            return json.dumps(
                [
                    {
                        "databaseId": 7,
                        "name": "tests",
                        "headSha": head,
                        "status": "completed",
                        "conclusion": "success",
                        "url": "https://example.test/run/7",
                    }
                ]
            )
        if arguments[-1].endswith("/jobs"):
            return json.dumps(
                {
                    "jobs": [
                        {
                            "name": f"job-{index}",
                            "conclusion": "success",
                            "head_sha": head,
                            "html_url": f"https://example.test/job/{index}",
                        }
                        for index in range(4)
                    ]
                }
            )
        if arguments[:2] == ("gh", "api"):
            return json.dumps({"object": {"sha": head}})
        raise AssertionError(arguments)

    monkeypatch.setattr(runner, "command", command)

    observed = runner.source_baseline(runner.governed_plan("3560-24PS"))

    assert observed["local_head"] == head
    assert observed["source_tree"] == tree
    assert observed["upstream_head"] == head
    assert not any("rev-parse" in call for call in calls)


@pytest.mark.parametrize(
    "field,value",
    [
        ("source_branch", "other"),
        ("source_head", "d" * 40),
        ("source_tree", "e" * 40),
        ("upstream", "other/branch"),
        ("upstream_head", "f" * 40),
        ("worktree_clean", False),
    ],
)
def test_frozen_source_revalidation_rejects_every_changed_git_boundary(
    runner,
    field,
    value,
) -> None:
    baseline, _restoration, final = facts()
    final[field] = value

    with pytest.raises(RuntimeError, match="Frozen LIVE source changed"):
        runner._require_frozen_source(baseline, final)


def test_head_movement_before_first_fixture_mutation_fails_closed(
    runner,
) -> None:
    plan = runner.governed_plan("3560-24PS")
    baseline, _restoration, _final = facts()
    artifacts = runner.reserve_artifacts("offline-source-freeze")
    mutations: list[str] = []
    ledger = empty_file_ledger(runner)

    class PreMutationSession:
        switch_ports = tuple(binding.switch_port for binding in plan.bindings)
        dispatches = ()
        attempted_device_names = ()
        created_device_names = ()

        def file_operation_ledger(self):
            return ledger

        def bridge_healthy(self):
            return True

        def mailbox_entries(self):
            return ()

        def start_control_bridge(self):
            return {}

        def stop_control_bridge(self):
            return None

        def environment(self):
            return dict(baseline["environment"])

        def inventory_fingerprint(self):
            return baseline["inventory_fingerprint"]

        def device_names(self):
            return frozenset()

        def create_fixture(self, *_args, **_kwargs):
            mutations.append("create_fixture")
            raise AssertionError("fixture mutation must not start")

        def apply_inline_mode(self, *_args, **_kwargs):
            return None

        def capture_inline_status(self, *_args, **_kwargs):
            raise RuntimeError("no fixture exists")

        def cleanup_fixture(self):
            return SimpleNamespace(deleted=(), problems=())

        def retire_session_residue(self, _preexisting):
            return ()

        def wait_for_inventory_fingerprint(self, expected):
            return expected

        def collect_completed(self):
            return None

        def transport_problems(self):
            return ()

    moved = {
        "source_branch": baseline["source_branch"],
        "source_head": "d" * 40,
        "source_tree": "e" * 40,
        "upstream": baseline["upstream"],
        "upstream_head": "d" * 40,
        "worktree_clean": True,
    }
    execution = runner.execute_governed_qualification(
        session=PreMutationSession(),
        plan=plan,
        baseline=baseline,
        artifacts=artifacts,
        process_probe=packet_tracer_processes,
        source_state_probe=lambda: dict(moved),
    )

    assert mutations == []
    assert execution.problems == ["RuntimeError: Frozen LIVE source changed"]
