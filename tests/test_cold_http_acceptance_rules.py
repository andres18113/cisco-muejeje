"""Pure rules of the cold-HTTP acceptance envelope.

The grant parser, the process and manifest bindings, the closure comparison,
the ordering oracle and the recomputed budget arithmetic are unit-tested here
against values, without a route. The closure fixtures are captured from one
real run of the production composition, then altered one field at a time.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from cold_http_acceptance_harness import (
    INCARNATION,
    PC1,
    PC2,
    build_harness,
    grant_document,
    paired_process,
)

from packet_tracer_mcp.application.use_cases.service_access_readiness_gate import (
    READINESS_EPISODE_CALLS,
    READINESS_GROUP_DEADLINE_SECONDS,
    READINESS_GROUP_INTERVAL_SECONDS,
    READINESS_GROUP_MAX_SAMPLES,
    READINESS_SAMPLE_ALLOWANCE,
    READINESS_SAMPLE_CALLS,
)
from packet_tracer_mcp.domain.enterprise.models.cold_http_acceptance import (
    COLD_HTTP_ARITHMETIC,
    COLD_HTTP_PROPOSAL,
    AcceptanceSubject,
    effect_scope_findings,
    manifest_refusals,
    parse_grant,
    process_refusals,
)
from packet_tracer_mcp.domain.enterprise.models.service_qualification import (
    OperationEntry,
    RefusalKind,
)
from packet_tracer_mcp.domain.enterprise.models.service_run_record import (
    ServiceRunRecord,
)
from packet_tracer_mcp.domain.enterprise.services.cold_http_acceptance_evidence import (
    ordering_findings,
    readiness_findings,
    record_identity_findings,
)


@pytest.fixture(scope="module")
def admitted(tmp_path_factory):
    """One accepted real run: its grant, closure and reloaded record."""
    harness = build_harness(tmp_path_factory.mktemp("admitted"))
    result = harness.run()
    assert result.envelope.http_accepted, result.envelope.reasons
    grant, refusals = parse_grant(harness.grant())
    assert refusals == ()
    record, _path, _digest = harness.record_store.load_evidence(
        result.envelope.product_input["deployment_id"],
        result.envelope.product["run_id"],
    )
    return grant, result.envelope.closure, record, result.envelope


# -- the grant -------------------------------------------------------------------


def _document(tmp_path: Path, **overrides):
    harness = build_harness(tmp_path)
    return harness.grant(**overrides)


def test_the_fixture_grant_parses_without_a_refusal(tmp_path: Path):
    """The positive control of every grant rule below."""
    grant, refusals = parse_grant(_document(tmp_path))

    assert refusals == ()
    assert grant is not None
    assert grant.netmask == "255.255.255.248"
    assert grant.run_label.endswith(grant.attempt_id)
    assert [item.name for item in grant.endpoints][1:] == [PC1, PC2]


@pytest.mark.parametrize(
    ("overrides", "subject", "kind"),
    [
        ({"schema_version": 2}, AcceptanceSubject.GRANT, RefusalKind.MISMATCH),
        (
            {"authorization_id": " padded"},
            AcceptanceSubject.AUTHORIZATION_ID,
            RefusalKind.MALFORMED,
        ),
        ({"attempt_id": "A" * 32}, AcceptanceSubject.ATTEMPT, RefusalKind.MALFORMED),
        ({"tree": "0" * 39}, AcceptanceSubject.SOURCE, RefusalKind.MALFORMED),
        ({"build": "9.0.1"}, AcceptanceSubject.BUILD, RefusalKind.MALFORMED),
        ({"channel": "http"}, AcceptanceSubject.CHANNEL, RefusalKind.NOT_PERMITTED),
        (
            {"deployment_id": "../escape"},
            AcceptanceSubject.DEPLOYMENT,
            RefusalKind.MALFORMED,
        ),
        ({"manifest_hash": "abc"}, AcceptanceSubject.MANIFEST, RefusalKind.MALFORMED),
        ({"intent_sha256": "X" * 64}, AcceptanceSubject.INTENT, RefusalKind.MALFORMED),
        ({"vlan_id": 4095}, AcceptanceSubject.SELECTION, RefusalKind.MALFORMED),
        ({"vlan_id": True}, AcceptanceSubject.SELECTION, RefusalKind.MALFORMED),
        ({"prefix_length": 31}, AcceptanceSubject.SELECTION, RefusalKind.MALFORMED),
        ({"max_operations": 1014}, AcceptanceSubject.BUDGET, RefusalKind.NOT_PERMITTED),
        (
            {"reserve_operations": 3},
            AcceptanceSubject.BUDGET,
            RefusalKind.NOT_PERMITTED,
        ),
        ({"reserve_seconds": 30}, AcceptanceSubject.BUDGET, RefusalKind.NOT_PERMITTED),
        ({"process_id": 0}, AcceptanceSubject.PROCESS, RefusalKind.MALFORMED),
        (
            {"reserve_operations": 0},
            AcceptanceSubject.BUDGET,
            RefusalKind.NOT_PERMITTED,
        ),
        ({"reserve_seconds": 0}, AcceptanceSubject.BUDGET, RefusalKind.NOT_PERMITTED),
        ({"max_operations": 0}, AcceptanceSubject.BUDGET, RefusalKind.NOT_PERMITTED),
        ({"max_seconds": 0}, AcceptanceSubject.BUDGET, RefusalKind.NOT_PERMITTED),
        ({"vlan_id": 0}, AcceptanceSubject.SELECTION, RefusalKind.MALFORMED),
        ({"prefix_length": 0}, AcceptanceSubject.SELECTION, RefusalKind.MALFORMED),
        ({"schema_version": 0}, AcceptanceSubject.GRANT, RefusalKind.MISMATCH),
        (
            {"gateway": "198.18.160.9"},
            AcceptanceSubject.SELECTION,
            RefusalKind.MALFORMED,
        ),
        (
            {"gateway": "198.18.160.2"},
            AcceptanceSubject.SELECTION,
            RefusalKind.MALFORMED,
        ),
        ({"gateway": "gateway"}, AcceptanceSubject.SELECTION, RefusalKind.MALFORMED),
        ({"process_incarnation": ""}, AcceptanceSubject.PROCESS, RefusalKind.MALFORMED),
        (
            {"exclusive_disposable_lab": "yes"},
            AcceptanceSubject.LABORATORY,
            RefusalKind.MALFORMED,
        ),
    ],
)
def test_each_malformed_grant_field_is_named(tmp_path: Path, overrides, subject, kind):
    """C1: a defect is named by its subject and kind, never parsed away."""
    grant, refusals = parse_grant(_document(tmp_path, **overrides))

    assert grant is None
    assert (subject, kind) in {(item.subject, item.kind) for item in refusals}


@pytest.mark.parametrize(
    "missing", ["sha", "clients", "server", "marker", "url", "gateway"]
)
def test_a_missing_grant_field_is_missing_not_defaulted(tmp_path: Path, missing):
    """C1: nothing a grant must bind is ever filled in for it."""
    document = _document(tmp_path)
    del document[missing]

    grant, refusals = parse_grant(document)

    assert grant is None
    assert refusals


@pytest.mark.parametrize(
    "mutate",
    [
        lambda doc: doc["clients"].append(dict(doc["clients"][0], name="PC-3")),
        lambda doc: doc["clients"][1].update(switch_port="FastEthernet1/1"),
        lambda doc: doc["clients"][1].update(ipv4="198.18.160.3"),
        lambda doc: doc["clients"][1].update(ipv4="198.18.161.4"),
        lambda doc: doc["clients"][1].update(ipv4="198.18.160.7"),
        lambda doc: doc["clients"][1].update(name=doc["server"]["name"]),
    ],
    ids=[
        "three_clients",
        "shared_port",
        "shared_address",
        "other_segment",
        "broadcast",
        "shared_name",
    ],
)
def test_the_granted_selection_must_be_one_segment_of_distinct_endpoints(
    tmp_path: Path, mutate
):
    """C1: two clients, distinct names, ports and host addresses, one segment."""
    document = _document(tmp_path)
    mutate(document)

    grant, refusals = parse_grant(document)

    assert grant is None
    assert AcceptanceSubject.SELECTION in {item.subject for item in refusals}


def test_a_document_that_is_not_an_object_is_malformed():
    """C1: the grant is a JSON object or it is nothing."""
    grant, refusals = parse_grant(["not", "an", "object"])

    assert grant is None
    assert refusals[0].subject is AcceptanceSubject.GRANT


# -- process and manifest ----------------------------------------------------------


def test_the_granted_incarnation_pairs_and_nothing_else_does(tmp_path: Path):
    """C2: PID, path, build and creation identity together name the process."""
    grant, _ = parse_grant(_document(tmp_path))

    assert process_refusals(grant, paired_process()) == ()
    changed = process_refusals(
        grant, paired_process(process_incarnation=INCARNATION + "X")
    )
    assert changed[0].kind is RefusalKind.MISMATCH


def test_a_manifest_differing_in_any_bound_value_refuses(tmp_path: Path):
    """C2: deployment, manifest hash, topology hash and build are all bound."""
    grant, _ = parse_grant(_document(tmp_path))
    values = {
        "deployment_id": grant.deployment_id,
        "semantic_hash": grant.manifest_hash,
        "physical_topology_hash": grant.physical_topology_hash,
        "backend_version": grant.build,
    }

    assert manifest_refusals(grant, **values) == ()
    for key in values:
        altered = dict(values, **{key: "other"})
        assert len(manifest_refusals(grant, **altered)) == 1


# -- the closure -----------------------------------------------------------------


def test_the_admitted_closure_has_no_finding(admitted):
    """The positive control: the real compiled closure is the granted one."""
    grant, closure, _record, _envelope = admitted

    assert effect_scope_findings(grant, closure) == ()
    assert len(closure.e5_actions) == 7
    assert [item.action_type for item in closure.excluded_actions] == [
        "configure_hostname"
    ]


def _altered(closure, **update):
    return closure.model_copy(update=update)


@pytest.mark.parametrize(
    ("alter", "finding"),
    [
        (
            lambda c: _altered(c, retained=["cfg/vlan/x"]),
            "retained_e5_actions:cfg/vlan/x",
        ),
        (lambda c: _altered(c, source_tree=""), "source_tree_absent"),
        (lambda c: _altered(c, source_dirty=True), "source_tree_dirty"),
        (lambda c: _altered(c, transport="http"), "transport_mismatch"),
        (lambda c: _altered(c, observed_build="9.0.0.0810"), "observed_build_mismatch"),
        (
            lambda c: _altered(c, e5_actions=c.e5_actions[:-1]),
            "e5_closure_differs_from_grant",
        ),
        (
            lambda c: _altered(
                c,
                e5_actions=[
                    item.model_copy(update={"interface": "FastEthernet1/4"})
                    if item.action_type == "configure_access_port"
                    else item
                    for item in c.e5_actions
                ],
            ),
            "e5_closure_differs_from_grant",
        ),
        (
            lambda c: _altered(
                c,
                excluded_actions=[
                    *c.excluded_actions,
                    c.e5_actions[0].model_copy(update={"action_id": "cfg/x"}),
                ],
            ),
            "non_hostname_exclusions:cfg/x",
        ),
        (
            lambda c: _altered(
                c,
                checks=[
                    item.model_copy(
                        update={"expected": {**item.expected, "hostname": "www"}}
                    )
                    for item in c.checks
                ],
            ),
            "http_fetch_by_hostname",
        ),
        (
            lambda c: _altered(
                c,
                service_actions=[
                    item.model_copy(update={"parameters": {"service_type": "http"}})
                    for item in c.service_actions
                ],
            ),
            "page_content_lacks_attempt_marker",
        ),
    ],
)
def test_any_material_change_to_the_closure_is_a_finding(admitted, alter, finding):
    """C5: an extra, missing or moved effect needs a revised grant, not a budget."""
    grant, closure, _record, _envelope = admitted

    findings = effect_scope_findings(grant, alter(closure))

    assert any(item.startswith(finding) for item in findings), findings


# -- the durable record --------------------------------------------------------------


def test_a_legacy_record_without_a_tree_loads_but_cannot_pass(admitted):
    """C9: schema-1 without a tree is valid history and never exact provenance."""
    grant, closure, record, _envelope = admitted
    stored = json.loads(record.model_dump_json())
    del stored["source_tree"]["tree"]

    legacy = ServiceRunRecord.model_validate_json(json.dumps(stored))

    assert legacy.schema_version == 1
    assert legacy.source_tree.tree == ""
    assert "record_source_tree_absent" in record_identity_findings(
        grant, legacy, closure
    )
    assert record_identity_findings(grant, record, closure) == []


# -- the ordering oracle --------------------------------------------------------------


def _entry(seq: int, purpose: str) -> OperationEntry:
    return OperationEntry(seq=seq, phase="experiment", call="dispatch", purpose=purpose)


def _sequence(*purposes: str) -> list[OperationEntry]:
    return [_entry(index + 1, purpose) for index, purpose in enumerate(purposes)]


_PC1 = "e6_verify:x1"
_PC2 = "e6_verify:x2"


@pytest.mark.parametrize(
    ("purposes", "finding"),
    [
        (
            (
                "e5_verify",
                "e6_apply",
                _PC1,
                "owned_release:x1",
                "readiness",
                _PC2,
                "owned_release:x2",
            ),
            "request_without_prior_forwarding_observation:" + PC1,
        ),
        (
            (
                "readiness",
                "e6_apply",
                _PC1,
                "owned_release:x1",
                "e5_verify",
                _PC2,
                "owned_release:x2",
            ),
            "request_not_after_e5_readback:" + PC1,
        ),
        (
            (
                "e5_verify",
                "readiness",
                "e6_apply",
                _PC1,
                _PC2,
                "owned_release:x1",
                "owned_release:x2",
            ),
            "request_before_previous_client_finished:" + PC2,
        ),
        (
            ("e5_verify", "readiness", "e6_apply", _PC1, _PC2, "owned_release:x2"),
            "owned_release_dispatches:" + PC1 + ":0",
        ),
        (
            (
                "e5_verify",
                "readiness",
                "",
                "e6_apply",
                _PC1,
                "owned_release:x1",
                _PC2,
                "owned_release:x2",
            ),
            "unlabelled_dispatches:<none>",
        ),
    ],
)
def test_the_oracle_reads_order_from_the_ledger(tmp_path: Path, purposes, finding):
    """C8: the order is judged from dispatch positions, never script text."""
    grant, _ = parse_grant(_document(tmp_path))
    clients = {PC1: "x1", PC2: "x2"}

    found = ordering_findings(grant, clients, _sequence(*purposes))

    assert finding in found, found


def test_the_oracle_accepts_either_product_order(tmp_path: Path):
    """C8: which client the product tests first is its choice, not a finding."""
    grant, _ = parse_grant(_document(tmp_path))
    clients = {PC1: "x1", PC2: "x2"}
    base = ("e5_verify", "readiness", "e6_apply")

    first = _sequence(*base, _PC1, "owned_release:x1", _PC2, "owned_release:x2")
    second = _sequence(*base, _PC2, "owned_release:x2", _PC1, "owned_release:x1")

    assert ordering_findings(grant, clients, first) == []
    assert ordering_findings(grant, clients, second) == []


def test_a_refused_entry_is_never_read_as_a_dispatch(tmp_path: Path):
    """C6: an entry the ledger refused did not reach the channel."""
    grant, _ = parse_grant(_document(tmp_path))
    entries = [
        _entry(1, "e5_verify"),
        OperationEntry(
            seq=0, phase="experiment", call="d", purpose="readiness", refused="time"
        ),
        _entry(2, "e6_apply"),
        _entry(3, _PC1),
        _entry(4, "owned_release:x1"),
    ]

    found = ordering_findings(grant, {PC1: "x1", PC2: "x2"}, entries)

    assert "request_without_prior_forwarding_observation:" + PC1 in found


# -- the recomputed budget --------------------------------------------------------------


def test_the_recomputed_worst_case_fits_the_frozen_ceiling():
    """C6: 1,010 dispatches at worst, under 1,015; ordinary work under 1,013."""
    worst = sum(count for _, count in COLD_HTTP_ARITHMETIC)
    releases = 2

    assert worst == 1010
    assert worst <= COLD_HTTP_PROPOSAL.max_operations
    assert worst - releases <= (
        COLD_HTTP_PROPOSAL.max_operations - COLD_HTTP_PROPOSAL.reserve_operations
    )
    assert COLD_HTTP_PROPOSAL.reserve_operations == releases


def test_the_readiness_line_is_derived_from_the_readiness_constants():
    """C6: a 30-second window at one-second spacing cannot start a 31st sample."""
    samples = min(
        READINESS_GROUP_MAX_SAMPLES,
        int(READINESS_GROUP_DEADLINE_SECONDS / READINESS_GROUP_INTERVAL_SECONDS),
    )
    line = dict(COLD_HTTP_ARITHMETIC)["readiness_30_samples_x6_calls_plus_auxiliary"]

    assert samples == 30
    # The line is the episode allowance the runtime enforces; one sample may
    # borrow more than its six-call share of it to finish a paginated table.
    assert line == READINESS_EPISODE_CALLS
    assert line == samples * READINESS_SAMPLE_ALLOWANCE + 1
    assert READINESS_SAMPLE_CALLS > READINESS_SAMPLE_ALLOWANCE


def test_the_legacy_route_runs_the_product_gate_ceiling(tmp_path: Path):
    """Same product as the MCP tool: the recorded sample ceiling is the gate's."""
    envelope = build_harness(tmp_path).run().envelope

    budgets = {row["sample"]["sample_call_budget"] for row in envelope.readiness}
    assert budgets == {READINESS_SAMPLE_CALLS}


def test_the_wait_lines_are_derived_from_the_runtime_bounds():
    """C6: IOS boot, E5 readback and HTTP polling counts follow their bounds."""
    arithmetic = dict(COLD_HTTP_ARITHMETIC)

    assert arithmetic["e5_ios_boot_wait_90s_at_0_25s"] == int(90.0 / 0.25) + 1
    assert arithmetic["e5_vlan_21_access_port_3_endpoint_3x121_readback"] == (
        int(5.0 / 0.25) + 1 + 3 + 3 * (int(30.0 / 0.25) + 1)
    )
    assert arithmetic["clients_2_x_start_33_inspections_release"] == 2 * (
        1 + int(8.0 / 0.25) + 1 + 1
    )


def test_the_grant_fixture_is_the_frozen_proposal(tmp_path: Path):
    """The fixture never grants a ceiling the proposal does not name."""
    harness = build_harness(tmp_path)
    document = grant_document(harness.manifest, harness.intent_json)

    assert (
        document["max_operations"],
        document["max_seconds"],
        document["reserve_operations"],
        document["reserve_seconds"],
    ) == (1015, 420, 2, 40)


# -- regressions from the independent review ---------------------------------------


def _endpoint_actions(closure, **update):
    return [
        item.model_copy(update=update)
        if item.action_type == "set_endpoint_static"
        else item
        for item in closure.e5_actions
    ]


@pytest.mark.parametrize(
    "alter",
    [
        lambda c: c.model_copy(
            update={"e5_actions": _endpoint_actions(c, gateway="198.18.160.6")}
        ),
        lambda c: c.model_copy(
            update={
                "e5_actions": [
                    item.model_copy(
                        update={
                            "parameters": {**item.parameters, "dns_server": "9.9.9.9"}
                        }
                    )
                    if item.action_type == "set_endpoint_static"
                    else item
                    for item in c.e5_actions
                ]
            }
        ),
    ],
    ids=["ungranted_gateway", "ungranted_dns_server"],
)
def test_every_endpoint_effect_parameter_is_bound_by_the_grant(admitted, alter):
    """C5: an endpoint's gateway and DNS are effects, so they are granted too."""
    grant, closure, _record, _envelope = admitted

    assert "e5_closure_differs_from_grant" in effect_scope_findings(
        grant, alter(closure)
    )


@pytest.mark.parametrize("count", [0, 2])
def test_exactly_one_direct_page_read_is_admitted(admitted, count):
    """C5: the server's direct HTTP read is one check, neither dropped nor doubled."""
    grant, closure, _record, _envelope = admitted
    fetches = [item for item in closure.checks if item.kind == "http_fetch"]
    direct = [item for item in closure.checks if item.kind != "http_fetch"]
    altered = closure.model_copy(update={"checks": fetches + direct[:1] * count})

    assert f"direct_http_state_checks:{count}" in effect_scope_findings(grant, altered)


def test_forwarding_observed_before_the_e5_readback_admits_nothing(tmp_path: Path):
    """C8: a FWD sample of ports not yet read back cannot precede the request."""
    grant, _ = parse_grant(_document(tmp_path))
    entries = _sequence(
        "readiness",
        "e5_verify",
        "e6_apply",
        _PC1,
        "owned_release:x1",
        _PC2,
        "owned_release:x2",
    )

    found = ordering_findings(grant, {PC1: "x1", PC2: "x2"}, entries)

    assert "forwarding_observed_before_e5_readback_finished" in found


def _with_sample(record, **sample_update):
    row = json.loads(json.dumps(record.operational_readiness[0]))
    row["sample"].update(sample_update)
    return record.model_copy(update={"operational_readiness": [row]})


@pytest.mark.parametrize(
    ("update", "finding"),
    [
        (
            {"observed_device_name": "HQ-OTHER"},
            "readiness_observed_device_is_not_the_switch",
        ),
        (
            {"device_identity_provenance": "ambiguous"},
            "readiness_device_identity_not_confirmed_unique",
        ),
        ({"executed": False}, "readiness_executed_not_true"),
        ({"fresh_output_observed": False}, "readiness_fresh_output_observed_not_true"),
        ({"output_complete": False}, "readiness_output_complete_not_true"),
        ({"vlan_present": False}, "readiness_vlan_present_not_true"),
        ({"vlan_id": 20}, "readiness_sample_vlan_mismatch"),
        (
            {"requested_interfaces": [1, "FastEthernet1/1"]},
            "readiness_sample_interfaces_differ_from_grant",
        ),
    ],
)
def test_an_admitted_readiness_row_is_rechecked_against_its_sample(
    admitted, update, finding
):
    """C8: the admitted flag is necessary; the sample it came from must agree."""
    grant, _closure, record, _envelope = admitted

    found = readiness_findings(grant, _with_sample(record, **update))

    assert finding in found, found
    assert readiness_findings(grant, record) == []


@pytest.mark.parametrize(
    ("update", "finding"),
    [
        (
            {"service_semantic_hash": "0" * 64},
            "record_service_hash_differs_from_closure",
        ),
        ({"selected_action_ids": []}, "record_service_actions_differ_from_closure"),
        ({"selected_service_ids": ["other"]}, "record_services_differ_from_closure"),
    ],
)
def test_the_reloaded_record_is_bound_to_the_admitted_service_closure(
    admitted, update, finding
):
    """C9: the E6 identity of the stored run is the one that was admitted."""
    grant, closure, record, _envelope = admitted

    found = record_identity_findings(grant, record.model_copy(update=update), closure)

    assert finding in found
