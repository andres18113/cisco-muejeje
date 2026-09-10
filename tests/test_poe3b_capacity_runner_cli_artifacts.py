"""PoE-3B CLI derivation and canonical artifact boundaries."""

from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import pytest

from tests.poe3b_capacity_runner_helpers import (
    facts,
    qualification_inputs,
    runner,
)


@pytest.mark.parametrize(
    "argv",
    [
        [],
        ["--execute"],
        ["--model", "3560-24PS"],
        ["--execute", "--model", "3560-24PS"],
        ["--model", "3560-24PS", "--qualification-id", "offline"],
        ["--execute", "--model", "unknown", "--qualification-id", "offline"],
        [
            "--execute",
            "--model",
            "3560-24PS",
            "--qualification-id",
            "../escape",
        ],
        [
            "--execute",
            "--model",
            "3560-24PS",
            "--qualification-id",
            "x",
            "--ios",
            "show run",
        ],
    ],
)
def test_parser_refuses_incomplete_or_ungoverned_requests(runner, argv):
    with pytest.raises((SystemExit, ValueError)):
        runner.parse_args(argv)


@pytest.mark.parametrize(
    "model,count,first,last",
    [
        ("3560-24PS", 21, "FastEthernet0/1", "FastEthernet0/21"),
        ("3650-24PS", 11, "GigabitEthernet1/0/2", "GigabitEthernet1/0/13"),
    ],
)
def test_plan_is_derived_with_exact_count_and_order(
    runner,
    model,
    count,
    first,
    last,
):
    args = runner.parse_args(
        ["--execute", "--model", model, "--qualification-id", "offline"]
    )
    plan = runner.governed_plan(args.model)
    assert plan.simultaneous_active_ports == count == len(plan.bindings)
    assert (
        plan.bindings[0].switch_port,
        plan.bindings[-1].switch_port,
    ) == (first, last)


@pytest.mark.parametrize("length", [69, 99, 100, 101])
def test_qualification_metadata_cannot_displace_unique_run_suffix(
    runner,
    length,
):
    with pytest.raises(ValueError):
        runner.parse_args(
            [
                "--execute",
                "--model",
                "3560-24PS",
                "--qualification-id",
                "x" * length,
            ]
        )


def test_boundary_length_run_names_keep_timestamp_nonce_and_final_id_character(
    runner,
    monkeypatch,
):
    monkeypatch.setattr(runner, "token_hex", lambda size: "1234abcd")
    names = []
    for suffix in ("a", "b"):
        identifier = "x" * 67 + suffix
        runner.parse_args(
            [
                "--execute",
                "--model",
                "3560-24PS",
                "--qualification-id",
                identifier,
            ]
        )
        run_id = runner.qualification_run_id(identifier)
        assert len(run_id) == 100
        assert run_id == runner.safe_name_component(run_id)
        assert run_id.startswith("poe3b-" + identifier + "-")
        assert run_id.endswith("Z-1234abcd")
        names.append(run_id)
    assert names[0] != names[1]
    monkeypatch.setattr(runner, "token_hex", lambda size: "8765dcba")
    retry = runner.qualification_run_id("x" * 67 + "a")
    assert retry != names[0] and retry.endswith("Z-8765dcba")


def test_artifact_destination_is_reserved_exclusively_before_any_fixture_mutation(
    runner,
    monkeypatch,
):
    monkeypatch.setattr(
        runner,
        "qualification_run_id",
        lambda _: "poe3b-fixed-identity",
    )
    first = runner.reserve_artifacts("offline")
    assert first.directory.is_dir()
    assert first.directory.name == first.run_id
    with pytest.raises(FileExistsError):
        runner.reserve_artifacts("offline")
    assert list(first.directory.iterdir()) == []

    plan = runner.governed_plan("3560-24PS")

    def forbidden(*args, **kwargs):
        pytest.fail("Fixture mutation preceded destination safety")

    session = runner.PacketTracerPoE3BSession(
        "offline-unreserved",
        switch_ports=tuple(binding.switch_port for binding in plan.bindings),
        transport=SimpleNamespace(bridge_healthy=forbidden),
    )
    with pytest.raises(ValueError):
        runner.execute_governed_qualification(
            session=session,
            plan=plan,
            baseline=facts()[0],
            artifacts=None,
            process_probe=forbidden,
            source_state_probe=forbidden,
        )


@pytest.mark.parametrize(
    "failure",
    ["missing", "removed", "scope_mismatch", "replacement"],
)
def test_snapshot_build_requires_original_exact_artifact_reservation(
    runner,
    monkeypatch,
    failure,
):
    inputs = qualification_inputs(runner)
    artifacts = inputs["artifacts"]
    if failure == "missing":
        inputs["artifacts"] = None
    elif failure == "removed":
        artifacts.directory.rmdir()
    elif failure == "scope_mismatch":
        inputs["scope"] = replace(
            inputs["scope"],
            experiment_id="different-run",
        )
    else:
        artifacts.directory.rename(
            artifacts.directory.with_name("previous-reservation")
        )
        artifacts.directory.mkdir()

    def forbidden(*args, **kwargs):
        pytest.fail("Positive result preceded destination safety")

    monkeypatch.setattr(runner, "CapabilityProbeResult", forbidden)
    with pytest.raises(ValueError):
        runner.build_qualification_snapshot(**inputs)
