"""Scalable acceptance re-derives each client's permission from raw evidence.

The evidence here is what one real attempt produced: the production
coordinator, product, readiness gate, ledger and stores over the SIMULATED
30-client campus (two access switches, two distribution switches, five
compiled trunk links of which spanning tree forwards three). Each fault is then
injected into a copy of that evidence and judged by the real evaluator, or
injected into the product's own rows so the whole envelope judges it. A label,
a summary or a count is never permission; only a raw observation bound to the
episode, revision and ledger positions the gate used is.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest
from campus_product_simulation import campus_payload, compose_campus
from cold_http_acceptance_harness import MARKER
from scalable_http_acceptance_harness import build_scalable_harness

from packet_tracer_mcp.application.use_cases import (
    accept_cold_http,
    service_access_readiness_gate,
)
from packet_tracer_mcp.domain.enterprise.models.service_qualification import (
    OperationEntry,
)
from packet_tracer_mcp.domain.enterprise.services import (
    scalable_http_acceptance_evidence as evidence_module,
)
from packet_tracer_mcp.domain.enterprise.services.readiness_evidence import (
    row_group_key,
)

CLIENTS = 30
SW1 = "HQ-DEFAULT-ACCESS-SW-01"
SW2 = "HQ-DEFAULT-ACCESS-SW-02"
READINESS = "readiness:"


@pytest.fixture(scope="module")
def campus30():
    """Compile the 30-client, two-access-switch campus once."""
    return compose_campus(campus_payload(CLIENTS, marker=MARKER))


def _capture(harness) -> dict[str, Any]:
    """Run one attempt and keep exactly what its evaluator was given."""
    captured: dict[str, Any] = {}
    real = accept_cold_http.evaluate_scalable_attempt

    def spy(grant, scope, **kwargs):
        captured.update(copy.deepcopy(kwargs), grant=grant, scope=scope)
        return real(grant, scope, **kwargs)

    patch = pytest.MonkeyPatch()
    patch.setattr(accept_cold_http, "evaluate_scalable_attempt", spy)
    try:
        captured["result"] = harness.run()
    finally:
        patch.undo()
    return captured


@pytest.fixture(scope="module")
def immediate(tmp_path_factory, campus30):
    """Evidence of the unchanged campus: every port and trunk forwards at once."""
    harness = build_scalable_harness(
        tmp_path_factory.mktemp("immediate"), CLIENTS, plans=campus30
    )
    return _capture(harness)


@pytest.fixture(scope="module")
def delayed(tmp_path_factory, campus30):
    """Evidence where every access port listens for 26 s before forwarding."""
    harness = build_scalable_harness(
        tmp_path_factory.mktemp("delayed"), CLIENTS, plans=campus30
    )
    harness.terminal.access_forwarding_after = {
        name: 26.0 for name in harness.terminal.network.switches
    }
    return _capture(harness)


def _judge(evidence, *, rows=None, entries=None):
    """Judge a copy of captured evidence with the real evaluator."""
    record = evidence["record"]
    summary = copy.deepcopy(evidence["summary"])
    if rows is not None:
        record = record.model_copy(update={"operational_readiness": rows})
        if summary is not None and "operational_readiness" in summary:
            summary["operational_readiness"] = copy.deepcopy(rows)
    return evidence_module.evaluate_scalable_attempt(
        evidence["grant"],
        evidence["scope"],
        closure=evidence["closure"],
        record=record,
        record_problems=list(evidence["record_problems"]),
        summary=summary,
        record_path=evidence["record_path"],
        entries=list(evidence["entries"] if entries is None else entries),
        answers=evidence["answers"],
        stop_facts=list(evidence["stop_facts"]),
    )


def _rows(evidence) -> list[dict[str, Any]]:
    return copy.deepcopy(
        [dict(item) for item in evidence["record"].operational_readiness]
    )


def _outcomes(evaluation) -> dict[str, Any]:
    return {item.client: item for item in evaluation.clients}


def _clients(evidence, kind: str):
    return [item for item in evidence["scope"].clients if item.path_kind == kind]


def _continuity(rows):
    return next(item for item in rows if item.get("kind") == "trunk_continuity")


def _access(rows, switch: str):
    return next(
        item
        for item in rows
        if "kind" not in item and item.get("switch_device_name") == switch
    )


def _has(outcome, fragment: str) -> bool:
    return any(fragment in item for item in outcome.findings)


def _only_multi_access_refused(evidence, evaluation, fragment: str) -> None:
    outcomes = _outcomes(evaluation)
    multi = _clients(evidence, "l2_multi_access")
    local = _clients(evidence, "local_access")
    assert multi and local
    for client in multi:
        assert not outcomes[client.name].accepted
        assert _has(outcomes[client.name], fragment), outcomes[client.name].findings
    # Independent clients keep their own outcome.
    assert all(outcomes[client.name].accepted for client in local), [
        outcomes[client.name].findings for client in local
    ]


# -- counter-controls: legitimate evidence stays accepted -----------------------------


def test_the_unchanged_campus_is_accepted_with_blocked_redundant_trunks(immediate):
    """Spanning tree blocks two of five trunks; the path still joins every pair."""
    rows = _rows(immediate)
    continuity = _continuity(rows)
    deciding = continuity["sample"]["rounds"][-1]
    links = {item["link_id"] for item in continuity["links"]}
    assert set(deciding["usable_links"]) < links  # some trunk is not forwarding

    evaluation = _judge(immediate)

    assert immediate["result"].envelope.http_accepted is True
    assert all(item.accepted for item in evaluation.clients), [
        item.findings for item in evaluation.clients if not item.accepted
    ]
    assert len(evaluation.clients) == CLIENTS


def test_delayed_forwarding_is_accepted_from_its_admitting_sample(delayed):
    """Listening samples precede the forwarding one inside one episode."""
    access = _access(_rows(delayed), SW2)
    assert access["sample"]["samples"] > 1
    assert all(item.accepted for item in _judge(delayed).clients)


def test_each_decision_names_the_episode_and_revision_the_gate_used(immediate):
    """Every observed row has its episode; every client one decision per group."""
    rows = _rows(immediate)
    for row in rows:
        assert row["episode"] == {"ordinal": 1, "revision": 0, "narrowed": False}
    for client in immediate["scope"].clients:
        for key in client.groups:
            marks = [
                dependent
                for row in rows
                for dependent in row["dependents"]
                if dependent["expectation_id"] == client.expectation_id
                and "decision" in dependent
                and row_group_key(row) == key
            ]
            assert len(marks) == 1
            assert marks[0]["decision"] == {"revision": 0}
    labels = {
        item.purpose
        for item in immediate["entries"]
        if item.purpose.startswith(READINESS)
    }
    assert labels == {
        f"{READINESS}{group.key}#1" for group in immediate["scope"].groups
    }


# -- R1a: a continuity summary is never permission ------------------------------------


def _deciding(row):
    return row["sample"]["rounds"][-1]


def _no_readings(row):
    _deciding(row)["readings"] = []


def _unexecuted(row):
    for reading in _deciding(row)["readings"]:
        reading["executed"] = False


def _foreign(row):
    for reading in _deciding(row)["readings"]:
        reading["observed_device_name"] = "FOREIGN-SW"


def _wrong_vlan(row):
    for reading in _deciding(row)["readings"]:
        for port in reading["ports"]:
            for column in ("allowed_vlans", "active_vlans", "forwarding_vlans"):
                port[column] = [20]


def _repeated_reading(row):
    readings = _deciding(row)["readings"]
    stale = copy.deepcopy(readings[0])
    stale["fresh_output_observed"] = False
    readings.insert(0, stale)


def _missing_switch(row):
    readings = _deciding(row)["readings"]
    del readings[-1]  # still labelled complete


def _stale_but_authoritative_count(row):
    for reading in _deciding(row)["readings"]:
        reading["after_deadline"] = True


def _missing_unused_port(row):
    """Drop one end of a trunk spanning tree blocks; every summary still agrees."""
    deciding = _deciding(row)
    names = dict(zip(row["switch_device_ids"], row["switch_device_names"], strict=True))
    blocked = next(
        link for link in row["links"] if link["link_id"] not in deciding["usable_links"]
    )
    name, interface = names[blocked["switch_a_id"]], blocked["interface_a"]
    reading = next(item for item in deciding["readings"] if item["switch_name"] == name)
    reading["ports"] = [
        port for port in reading["ports"] if port["interface"] != interface
    ]


@pytest.mark.parametrize(
    ("fault", "fragment"),
    [
        (_no_readings, "continuity_readings_absent"),
        (_unexecuted, "continuity_summary_contradicts_readings"),
        (_foreign, "continuity_summary_contradicts_readings"),
        (_wrong_vlan, "continuity_summary_contradicts_readings"),
        (_repeated_reading, "continuity_reading_repeated"),
        (_missing_switch, "continuity_completeness_contradicted"),
        (_stale_but_authoritative_count, "continuity_summary_contradicts_readings"),
        (_missing_unused_port, "continuity_ports_not_the_trunks"),
    ],
)
def test_a_positive_continuity_summary_over_bad_readings_refuses(
    immediate, fault, fragment
):
    """R1a: the labels say joined; the raw readings do not."""
    rows = _rows(immediate)
    fault(_continuity(rows))

    evaluation = _judge(immediate, rows=rows)

    _only_multi_access_refused(immediate, evaluation, fragment)


def test_a_link_that_is_not_in_the_derived_scope_refuses(immediate):
    """R1a: a recorded edge the compiled component does not have joins nothing."""
    rows = _rows(immediate)
    continuity = _continuity(rows)
    ids = continuity["switch_device_ids"]
    continuity["links"].append(
        {
            "link_id": "link/forged",
            "switch_a_id": ids[0],
            "interface_a": "GigabitEthernet0/9",
            "switch_b_id": ids[1],
            "interface_b": "GigabitEthernet0/9",
        }
    )
    _deciding(continuity)["usable_links"] = ["link/forged"]

    evaluation = _judge(immediate, rows=rows)

    _only_multi_access_refused(
        immediate, evaluation, "continuity_links_differ_from_scope"
    )


# -- R1b: the access sample must agree with its own history ---------------------------


def _history_not_fresh(row):
    row["sample"]["sample_history"][-1]["fresh_output_observed"] = False


def _history_foreign(row):
    row["sample"]["sample_history"][-1]["observed_device_name"] = "FOREIGN-SW"


def _history_absent(row):
    row["sample"]["sample_history"] = []


def _samples_miscounted(row):
    row["sample"]["samples"] = row["sample"]["samples"] + 1


def _interface_repeated(row):
    rows = row["sample"]["rows"]
    blocked = dict(rows[0], state="BLK")
    rows.insert(0, blocked)
    row["sample"]["sample_history"][-1]["rows"].insert(0, dict(blocked))


def _labels_contradict(row):
    row["sample"]["admitted"] = False
    row["sample"]["dimension"] = "NON_FORWARDING"


def _field_missing(row):
    del row["sample"]["vlan_present"]


@pytest.mark.parametrize(
    ("fault", "fragment"),
    [
        (_history_not_fresh, "access_history_disagrees:fresh_output_observed"),
        (_history_foreign, "access_history_disagrees:observed_device_name"),
        (_history_absent, "access_history_disagrees:samples"),
        (_samples_miscounted, "access_history_disagrees:samples"),
        (_interface_repeated, "access_interface_rows_repeated"),
        (_labels_contradict, "access_sample_labels_contradict"),
        (_field_missing, "access_sample_malformed:vlan_present"),
    ],
)
def test_an_access_sample_that_its_history_does_not_support_refuses(
    immediate, fault, fragment
):
    """R1b: every client of the faulted switch is refused, every other kept."""
    rows = _rows(immediate)
    fault(_access(rows, SW1))

    evaluation = _judge(immediate, rows=rows)

    outcomes = _outcomes(evaluation)
    for client in immediate["scope"].clients:
        outcome = outcomes[client.name]
        if client.switch == SW1:
            assert not outcome.accepted
            assert _has(outcome, fragment), outcome.findings
        else:
            assert outcome.accepted, outcome.findings


# -- R1c: permission is the episode that decided, before the request -------------------


def _move_before(entries, purposes: set[str], index: int) -> list[OperationEntry]:
    moved = [item for item in entries if item.purpose in purposes]
    rest = [item for item in entries if item.purpose not in purposes]
    return rest[:index] + moved + rest[index:]


def test_a_request_between_listening_and_forwarding_samples_is_refused(delayed):
    """R1c: early LIS, then the request, then the FWD sample that admitted it."""
    scope = delayed["scope"]
    entries = list(delayed["entries"])
    key = f"access:{SW2}:10"
    episode = [
        position
        for position, item in enumerate(entries)
        if item.purpose.startswith(READINESS + key)
    ]
    assert len(episode) > 10  # listening samples, then forwarding
    first = next(
        item
        for item in entries
        if item.purpose.startswith("e6_verify:svc/verify-http-ip/")
    )
    victim = next(
        item for item in scope.clients if item.expectation_id in first.purpose
    )
    purposes = {
        f"e6_verify:{victim.expectation_id}",
        f"owned_release:{victim.expectation_id}",
    }
    moved = _move_before(entries, purposes, episode[1])

    evaluation = _judge(delayed, entries=moved)

    outcomes = _outcomes(evaluation)
    assert not outcomes[victim.name].accepted
    assert _has(outcomes[victim.name], f"readiness_episode_not_before_request:{key}")
    assert all(
        item.accepted for name, item in outcomes.items() if name != victim.name
    ), [item.findings for name, item in outcomes.items() if name != victim.name]


def test_a_second_admitting_row_for_the_same_decision_is_ambiguous(immediate):
    """R1c: a duplicated group row never lets the evaluator pick a favourite."""
    rows = _rows(immediate)
    rows.append(copy.deepcopy(_access(rows, SW1)))

    outcomes = _outcomes(_judge(immediate, rows=rows))

    for client in immediate["scope"].clients:
        if client.switch == SW1:
            assert _has(outcomes[client.name], "readiness_decision_ambiguous")
            assert not outcomes[client.name].accepted


def test_a_client_listed_twice_in_one_row_is_refused(immediate):
    """R1c: duplicate dependent entries inside one row are ambiguous."""
    rows = _rows(immediate)
    access = _access(rows, SW1)
    duplicate = dict(access["dependents"][0], admitted=False, cause="x")
    duplicate.pop("decision", None)
    access["dependents"].append(duplicate)
    victim = duplicate["expectation_id"]

    evaluation = _judge(immediate, rows=rows)

    outcome = next(item for item in evaluation.clients if item.expectation_id == victim)
    assert not outcome.accepted
    assert _has(outcome, "readiness_dependent_repeated")


def test_a_client_without_a_decision_is_refused(immediate):
    """R1c: admitted by a row, but the gate never recorded deciding with it."""
    rows = _rows(immediate)
    dependent = _access(rows, SW1)["dependents"][0]
    del dependent["decision"]

    evaluation = _judge(immediate, rows=rows)

    outcome = next(
        item
        for item in evaluation.clients
        if item.expectation_id == dependent["expectation_id"]
    )
    assert not outcome.accepted
    assert _has(outcome, "readiness_decision_absent")


def test_an_older_record_without_episode_identity_cannot_be_accepted(immediate):
    """An older record stays readable; it acquires no new acceptance claim."""
    rows = _rows(immediate)
    for row in rows:
        row.pop("episode", None)
        for dependent in row["dependents"]:
            dependent.pop("decision", None)

    evaluation = _judge(immediate, rows=rows)

    assert len(evaluation.clients) == CLIENTS
    assert not any(item.accepted for item in evaluation.clients)
    assert all(_has(item, "readiness_decision_absent") for item in evaluation.clients)


# -- R1d: a later revision supersedes an earlier permission ----------------------------


def test_a_decision_older_than_its_group_revision_is_stale(immediate):
    """R1d: the gate decided at revision 1 with an episode observed at 0."""
    rows = _rows(immediate)
    access = _access(rows, SW1)
    for dependent in access["dependents"]:
        dependent["decision"] = {"revision": 1}

    outcomes = _outcomes(_judge(immediate, rows=rows))

    for client in immediate["scope"].clients:
        if client.switch == SW1:
            assert _has(outcomes[client.name], "readiness_permission_stale")
            assert not outcomes[client.name].accepted


def test_a_later_revision_dispatched_before_a_request_supersedes_it(immediate):
    """R1d: re-observation after invalidation precedes some requests only.

    Clients whose requests came before the re-observation keep their earlier,
    correct permission; later valid work does not invalidate it.
    """
    rows = _rows(immediate)
    entries = list(immediate["entries"])
    key = f"access:{SW1}:10"
    first = _access(rows, SW1)
    later = copy.deepcopy(first)
    later["episode"] = {"ordinal": 2, "revision": 1, "narrowed": False}
    for dependent in later["dependents"]:
        dependent.pop("decision", None)
    rows.append(later)
    sw1 = [item for item in immediate["scope"].clients if item.switch == SW1]
    requests = {
        client.name: next(
            position
            for position, item in enumerate(entries)
            if item.purpose == f"e6_verify:{client.expectation_id}"
        )
        for client in sw1
    }
    ordered = sorted(requests, key=requests.get)
    cut = requests[ordered[len(ordered) // 2]]
    template = next(
        item for item in entries if item.purpose.startswith(READINESS + key)
    )
    entries.insert(cut, template.model_copy(update={"purpose": f"{READINESS}{key}#2"}))

    outcomes = _outcomes(_judge(immediate, rows=rows, entries=entries))

    before = ordered[: len(ordered) // 2]
    after = ordered[len(ordered) // 2 :]
    assert all(outcomes[name].accepted for name in before), [
        outcomes[name].findings for name in before
    ]
    for name in after:
        assert not outcomes[name].accepted
        assert _has(outcomes[name], "readiness_permission_superseded_before_request")


# -- the whole envelope ---------------------------------------------------------------


@pytest.mark.parametrize("fault", [_no_readings, _missing_unused_port])
def test_the_whole_envelope_refuses_incomplete_continuity_evidence(
    tmp_path: Path, campus30, monkeypatch: pytest.MonkeyPatch, fault
):
    """R1a end to end: an incomplete continuity reading is never permission.

    The product records a joined summary without its readings, or without one
    port of a trunk that spanning tree blocks.
    """
    gate = service_access_readiness_gate.ServiceAccessReadinessGate
    real_rows = gate.rows

    def faulted(self):
        rendered = real_rows(self)
        for row in rendered:
            if row.get("kind") == "trunk_continuity" and row["sample"].get("rounds"):
                fault(row)
        return rendered

    monkeypatch.setattr(gate, "rows", faulted)
    harness = build_scalable_harness(tmp_path, CLIENTS, plans=campus30)

    result = harness.run()

    envelope = result.envelope
    assert result.product_summary["status"] == "verified"
    assert envelope.http_accepted is False
    scope = harness.prepared.scope
    rows = {item.client: item for item in envelope.clients}
    for client in scope.clients:
        if client.path_kind == "l2_multi_access":
            assert not rows[client.name].accepted
        else:
            assert rows[client.name].accepted, rows[client.name].findings


def test_legitimate_narrowing_is_bound_to_the_narrowed_episode(
    tmp_path: Path, campus30
):
    """One port never forwards: its neighbours are admitted by the narrowed episode."""
    harness = build_scalable_harness(tmp_path, CLIENTS, plans=campus30)
    scope = harness.prepared.scope
    victim = next(item for item in scope.clients if item.switch == SW1)
    harness.terminal.network.blocked_access.add((SW1, victim.port))
    captured = _capture(harness)

    evaluation = _judge(captured)

    outcomes = _outcomes(evaluation)
    assert not outcomes[victim.name].accepted
    assert all(
        item.accepted for name, item in outcomes.items() if name != victim.name
    ), [item.findings for name, item in outcomes.items() if name != victim.name]
    narrowed = [
        row
        for row in _rows(captured)
        if row.get("narrowed_from_group") and row.get("switch_device_name") == SW1
    ]
    assert len(narrowed) == 1
    assert narrowed[0]["episode"] == {"ordinal": 2, "revision": 0, "narrowed": True}
    decided = [item for item in narrowed[0]["dependents"] if "decision" in item]
    assert decided and all(item["admitted"] for item in decided)
    assert victim.expectation_id not in {item["expectation_id"] for item in decided}
