"""The row contract, the row-to-facts mapping, and the verification facts.

Every expected value here comes from the contract, not from the reported row:
the point of the row validator is that a row can be wrong, and a test that
read the row to decide what to expect would agree with any row at all.
"""

from __future__ import annotations

import json

import pytest

from packet_tracer_mcp.domain.enterprise.models.configuration_runtime import (
    ActionExecutionStatus,
    ConfigurationFailureCode,
)
from packet_tracer_mcp.domain.enterprise.models.execution import (
    DispatchFact,
    FootprintFact,
    PostconditionFact,
    ResultFact,
    TransitionFact,
)
from packet_tracer_mcp.domain.enterprise.models.service_plan import (
    AddDnsRecord,
    EnableDnsService,
    EnableHttpService,
    PublishTftpFile,
    ServiceEvidenceKind,
    ServicePhase,
    ServiceType,
    ServiceVerificationExpectation,
    ServiceVerificationKind,
    SetHttpContent,
)
from packet_tracer_mcp.domain.enterprise.models.service_runtime import ObservationFact
from packet_tracer_mcp.infrastructure.execution.enterprise_service_runtime import (
    BridgeObservationKind,
    PacketTracerEnterpriseServiceRuntime,
)
from packet_tracer_mcp.infrastructure.execution.transport_outcome import (
    BridgeDispatchOutcome,
)


def _common(service_id="service/hq/dns", service_type=ServiceType.DNS):
    return dict(
        service_id=service_id,
        service_type=service_type,
        host_device_id="srv-1",
        host_device_name="__MCP_E6_SERVER",
        host_model="Server-PT",
        site_id="hq",
        required_capability=f"service_{service_type.value}_application",
    )


def _row(identifier="enable", **overrides):
    """One admissible row of the item 4 contract, before any override."""
    row = {
        "id": identifier,
        "attempted": True,
        "skip_reason": "",
        "call_error": "",
        "call_result": None,
        "pre_read": True,
        "post_read": True,
        "ok": True,
        "changed": True,
        "pre": "0",
        "post": "1",
    }
    row.update(overrides)
    return row


def _enable(identifier="enable"):
    return EnableDnsService(id=identifier, phase=ServicePhase.ENABLE, **_common())


def _add_record(identifier="record"):
    return AddDnsRecord(
        id=identifier,
        phase=ServicePhase.CONTENT,
        hostname="safe.example.local",
        address="198.18.160.10",
        **_common(),
    )


def _apply(actions, payload, *, dispatch_and_wait=None):
    """Run one batch against a canned response and return the mutations."""
    if dispatch_and_wait is not None:
        runtime = PacketTracerEnterpriseServiceRuntime(
            lambda: [],
            lambda js, timeout: None,
            dispatch_and_wait=dispatch_and_wait,
        )
    else:
        runtime = PacketTracerEnterpriseServiceRuntime(
            lambda: [],
            lambda js, timeout: payload,
        )
    return runtime.apply_actions(actions)


# -- 1. the row contract is enforced strictly ----------------------------


@pytest.mark.parametrize(
    ("overrides", "check"),
    [
        # Flags must be actual booleans. These are the cases an equality-based
        # membership test would have admitted.
        ({"attempted": 1}, "attempted_type"),
        ({"pre_read": 1}, "pre_read_type"),
        ({"post_read": 1}, "post_read_type"),
        ({"ok": 1}, "ok_type"),
        ({"changed": 0}, "changed_type"),
        ({"ok": "true"}, "ok_type"),
        ({"call_result": 1}, "call_result_type"),
        ({"pre": 0}, "pre_type"),
        ({"post": {"digest": "x"}}, "post_type"),
        ({"call_error": None}, "call_error_type"),
        ({"skip_reason": None}, "skip_reason_type"),
        # A completed post-read requires a boolean `ok`.
        ({"ok": None}, "post_read_requires_ok"),
        # `changed` requires BOTH reads, and null otherwise.
        ({"pre_read": False, "changed": True}, "incomplete_reads_require_null_changed"),
        ({"changed": None}, "complete_reads_require_changed"),
        # A failed post-read cannot carry a postcondition or a transition.
        (
            {"post_read": False, "ok": True, "changed": None},
            "post_read_false_requires_null",
        ),
        (
            {"post_read": False, "ok": None, "changed": True},
            "post_read_false_requires_null",
        ),
        # A skipped row must name a registered reason and made no call.
        ({"attempted": False, "skip_reason": "because"}, "skip_reason_unknown"),
        ({"attempted": False, "skip_reason": ""}, "skip_reason_unknown"),
        (
            {
                "attempted": False,
                "skip_reason": "already_satisfied",
                "call_result": True,
            },
            "skipped_requires_no_call_result",
        ),
        (
            {
                "attempted": False,
                "skip_reason": "already_satisfied",
                "call_error": "boom",
            },
            "skipped_requires_no_call_error",
        ),
        (
            {
                "attempted": False,
                "skip_reason": "already_satisfied",
                "pre_read": False,
                "changed": None,
            },
            "already_satisfied_requires_pre_read",
        ),
        # The skip said the record was there and the post-read says it is not.
        (
            {"attempted": False, "skip_reason": "already_satisfied", "ok": False},
            "already_satisfied_contradicted",
        ),
        (
            {
                "attempted": False,
                "skip_reason": "family_not_implemented",
                "pre_read": True,
                "post_read": False,
                "ok": None,
                "changed": None,
            },
            "declined_requires_no_reads",
        ),
        # An attempted row cannot also claim it was skipped.
        ({"skip_reason": "already_satisfied"}, "attempted_requires_empty_skip_reason"),
    ],
)
def test_an_inadmissible_row_is_named_and_produces_row_seven(overrides, check):
    """A row the contract refuses states nothing, and says which check failed."""
    payload = json.dumps({"results": [_row(**overrides)]})

    mutation = _apply([_enable()], payload)[0]

    assert mutation.dispatch is DispatchFact.ACCEPTED
    assert mutation.result is ResultFact.CORRELATED
    assert mutation.postcondition is PostconditionFact.UNOBSERVED
    assert mutation.transition is TransitionFact.UNOBSERVED
    assert mutation.footprint is FootprintFact.NOT_APPLICABLE
    assert mutation.attempted is None
    assert mutation.cause == f"row_invalid:{check}"


@pytest.mark.parametrize(
    "key",
    [
        "attempted",
        "skip_reason",
        "call_error",
        "call_result",
        "pre_read",
        "post_read",
        "ok",
        "changed",
        "pre",
        "post",
    ],
)
def test_an_omitted_key_is_invalid_rather_than_null(key):
    """An absent key is not an observation of `null`.

    Reading a missing `ok` as null would silently turn an engine that reported
    nothing into a row whose post-read simply did not complete.
    """
    row = _row()
    del row[key]

    mutation = _apply([_enable()], json.dumps({"results": [row]}))[0]

    assert mutation.cause == f"row_invalid:absent_{key}"


def test_a_missing_row_inside_a_correlated_batch_is_row_seven():
    """TD-12.2: the adapter DOES hold the envelope, so acceptance is proven."""
    payload = json.dumps({"results": [_row("enable")]})

    mutations = {
        item.action_id: item for item in _apply([_enable(), _add_record()], payload)
    }

    assert mutations["record"].dispatch is DispatchFact.ACCEPTED
    assert mutations["record"].result is ResultFact.CORRELATED
    assert mutations["record"].applied is True
    assert mutations["record"].cause == "row_missing"
    assert mutations["record"].attempted is None


def test_duplicate_ids_make_the_whole_batch_malformed():
    """Two rows for one action means no row can be attributed to it."""
    payload = json.dumps({"results": [_row("enable"), _row("enable")]})

    mutations = _apply([_enable()], payload)

    assert mutations[0].result is ResultFact.MALFORMED
    assert mutations[0].postcondition is PostconditionFact.UNOBSERVED
    assert mutations[0].attempted is None


def test_a_non_list_results_field_makes_the_whole_batch_malformed():
    """The envelope shape is part of the contract."""
    payload = json.dumps({"results": {"enable": _row()}})

    mutations = _apply([_enable()], payload)

    assert mutations[0].result is ResultFact.MALFORMED


def test_a_foreign_id_is_ignored_and_named_in_the_message():
    """An unexpected row is discarded, never attributed to a requested action."""
    payload = json.dumps({"results": [_row("enable"), _row("someone-elses-action")]})

    mutation = _apply([_enable()], payload)[0]

    assert mutation.postcondition is PostconditionFact.SATISFIED
    assert "someone-elses-action" in mutation.message


# -- 2. row to facts ------------------------------------------------------


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        (
            {"ok": True, "changed": False, "pre": "1", "post": "1"},
            (
                PostconditionFact.SATISFIED,
                TransitionFact.UNCHANGED,
                FootprintFact.COVERED,
            ),
        ),
        (
            {"ok": True, "changed": True},
            (
                PostconditionFact.SATISFIED,
                TransitionFact.CHANGED,
                FootprintFact.COVERED,
            ),
        ),
        (
            {"ok": False, "changed": False},
            (
                PostconditionFact.UNSATISFIED,
                TransitionFact.UNCHANGED,
                FootprintFact.COVERED,
            ),
        ),
        (
            {"ok": False, "changed": True},
            (
                PostconditionFact.UNSATISFIED,
                TransitionFact.CHANGED,
                FootprintFact.COVERED,
            ),
        ),
        (
            {"pre_read": False, "changed": None, "pre": None},
            (
                PostconditionFact.SATISFIED,
                TransitionFact.UNOBSERVED,
                FootprintFact.COVERED,
            ),
        ),
        (
            {"post_read": False, "ok": None, "changed": None, "post": None},
            (
                PostconditionFact.UNOBSERVED,
                TransitionFact.UNOBSERVED,
                FootprintFact.COVERED,
            ),
        ),
    ],
)
def test_a_covered_family_maps_its_readings_to_facts(overrides, expected):
    """The postcondition comes from `ok`, the transition from `changed`."""
    mutation = _apply([_enable()], json.dumps({"results": [_row(**overrides)]}))[0]

    assert (
        mutation.postcondition,
        mutation.transition,
        mutation.footprint,
    ) == expected


def test_an_attempted_dns_add_has_a_partial_footprint_and_names_it():
    """The read covers one record's membership; the setter changes a table."""
    payload = json.dumps({"results": [_row("record", call_result=True)]})

    mutation = _apply([_add_record()], payload)[0]

    assert mutation.footprint is FootprintFact.PARTIAL
    assert mutation.cause == "footprint_partial:dns_a_record_table"


def test_a_skipped_dns_add_has_a_covered_footprint():
    """No call was made, and the absence of a call is the stronger proof.

    A skipped add cannot have written a different record for the same name,
    because it did not write anything.
    """
    payload = json.dumps(
        {
            "results": [
                _row(
                    "record",
                    attempted=False,
                    skip_reason="already_satisfied",
                    changed=False,
                    pre="1",
                    post="1",
                )
            ]
        }
    )

    mutation = _apply([_add_record()], payload)[0]

    assert mutation.attempted is False
    assert mutation.footprint is FootprintFact.COVERED
    assert mutation.postcondition is PostconditionFact.SATISFIED
    assert mutation.transition is TransitionFact.UNCHANGED


def test_a_declined_family_reports_row_twenty_and_keeps_its_failed_outcome():
    """`PublishTftpFile` is declined, with no reads and no call."""
    action = PublishTftpFile(
        id="publish",
        phase=ServicePhase.CONTENT,
        filename="x.cfg",
        content="startup-config",
        content_sha256="hash",
        **_common("service/hq/tftp", ServiceType.TFTP),
    )
    payload = json.dumps(
        {
            "results": [
                {
                    "id": "publish",
                    "attempted": False,
                    "skip_reason": "family_not_implemented",
                    "call_error": "",
                    "call_result": None,
                    "pre_read": False,
                    "post_read": False,
                    "ok": None,
                    "changed": None,
                    "pre": None,
                    "post": None,
                }
            ]
        }
    )

    mutation = _apply([action], payload)[0]

    assert mutation.attempted is False
    assert mutation.postcondition is PostconditionFact.UNOBSERVED
    assert mutation.transition is TransitionFact.NOT_APPLICABLE
    assert mutation.footprint is FootprintFact.NOT_APPLICABLE


def test_the_generated_script_never_calls_the_declined_family():
    """A declined action emits no process lookup and no reads at all."""
    captured = []
    action = PublishTftpFile(
        id="publish",
        phase=ServicePhase.CONTENT,
        filename="x.cfg",
        content="startup-config",
        content_sha256="hash",
        **_common("service/hq/tftp", ServiceType.TFTP),
    )
    PacketTracerEnterpriseServiceRuntime(
        lambda: [],
        lambda js, timeout: captured.append(js) or json.dumps({"results": []}),
    ).apply_actions([action])

    assert "TftpServer" not in captured[0]
    assert "family_not_implemented" in captured[0]


# -- 3. whole-batch outcomes ---------------------------------------------


@pytest.mark.parametrize(
    ("dispatch", "result", "expected_postcondition", "expected_applied"),
    [
        (
            DispatchFact.NOT_SUBMITTED,
            ResultFact.NOT_APPLICABLE,
            PostconditionFact.NOT_APPLICABLE,
            False,
        ),
        (
            DispatchFact.REJECTED,
            ResultFact.NOT_APPLICABLE,
            PostconditionFact.NOT_APPLICABLE,
            False,
        ),
        (
            DispatchFact.ACCEPTANCE_UNKNOWN,
            ResultFact.NOT_OBSERVED,
            PostconditionFact.UNOBSERVED,
            False,
        ),
        (
            DispatchFact.ACCEPTED,
            ResultFact.NOT_OBSERVED,
            PostconditionFact.UNOBSERVED,
            True,
        ),
        (DispatchFact.ACCEPTED, ResultFact.LOST, PostconditionFact.UNOBSERVED, True),
    ],
)
def test_a_batch_wide_outcome_reaches_every_action_identically(
    dispatch, result, expected_postcondition, expected_applied
):
    """No action in a batch gets a better fact than the batch supports."""
    outcome = BridgeDispatchOutcome(
        dispatch=dispatch, result=result, detail="synthetic"
    )

    mutations = _apply(
        [_enable(), _add_record()],
        None,
        dispatch_and_wait=lambda js, timeout: outcome,
    )

    assert len(mutations) == 2
    for mutation in mutations:
        assert mutation.dispatch is dispatch
        assert mutation.result is result
        assert mutation.postcondition is expected_postcondition
        assert mutation.footprint is FootprintFact.NOT_APPLICABLE
        assert mutation.attempted is None
        assert mutation.applied is expected_applied


def test_an_engine_error_body_is_an_engine_error_not_an_empty_payload():
    """`PT_ERROR:` is a fact about the engine, and `{}` hid it."""
    mutations = _apply(
        [_enable()], "PT_ERROR: TypeError: p.setEnable is not a function"
    )

    assert mutations[0].result is ResultFact.ENGINE_ERROR
    assert mutations[0].applied is True
    assert mutations[0].postcondition is PostconditionFact.UNOBSERVED


def test_a_non_json_body_is_malformed_not_an_empty_payload():
    """A body that is not a JSON object states nothing about any action."""
    mutations = _apply([_enable()], "<html>not json</html>")

    assert mutations[0].result is ResultFact.MALFORMED


def test_the_legacy_wrapper_never_claims_the_payload_stayed_in_the_process():
    """`send_and_wait` returning `None` cannot prove NOT_SUBMITTED."""
    runtime = PacketTracerEnterpriseServiceRuntime(lambda: [], lambda js, timeout: None)

    mutations = runtime.apply_actions([_enable()])

    assert mutations[0].dispatch is DispatchFact.ACCEPTANCE_UNKNOWN
    assert mutations[0].result is ResultFact.NOT_OBSERVED
    assert mutations[0].applied is False


def test_a_batch_targeting_two_hosts_is_a_local_contract_error():
    """Nothing was dispatched, so the legacy definite failure is preserved."""
    other = EnableHttpService(
        id="http",
        phase=ServicePhase.ENABLE,
        **{
            **_common("service/hq/http", ServiceType.HTTP),
            "host_device_name": "OTHER-HOST",
        },
    )

    mutations = _apply([_enable(), other], json.dumps({"results": []}))

    assert all(item.applied is False for item in mutations)
    assert all(
        item.failure_code is ConfigurationFailureCode.APPLICATION_FAILED
        for item in mutations
    )
    assert all(item.dispatch is DispatchFact.UNSPECIFIED for item in mutations)


# -- 4. the generated script's shape -------------------------------------


def test_the_batch_script_brackets_every_setter_with_typed_reads():
    """Pre-read, setter and unconditional post-read, each in its own guard."""
    captured = []
    PacketTracerEnterpriseServiceRuntime(
        lambda: [],
        lambda js, timeout: captured.append(js) or json.dumps({"results": []}),
    ).apply_actions([_enable()])
    script = captured[0]

    assert script.count("catch(e){}") >= 2
    assert "r.pre_read=true" in script
    assert "r.post_read=true" in script
    assert "r.ok=(qv===true)" in script
    assert "r.changed=(pv!==qv)" in script
    # The post-read is not inside the setter's guard, so a throwing setter
    # cannot suppress it.
    assert script.index("r.attempted=true") < script.index("r.post_read=true")


def test_the_batch_script_computes_ok_from_the_value_never_from_a_digest():
    """No comparison in the generated script reads `pre` or `post`."""
    captured = []
    action = SetHttpContent(
        id="content",
        phase=ServicePhase.CONTENT,
        content="MARKER",
        content_sha256="hash",
        **_common("service/hq/http", ServiceType.HTTP),
    )
    PacketTracerEnterpriseServiceRuntime(
        lambda: [],
        lambda js, timeout: captured.append(js) or json.dumps({"results": []}),
    ).apply_actions([action])
    script = captured[0]

    assert 'r.ok=(qv==="MARKER")' in script
    assert "r.pre===" not in script
    assert "r.post===" not in script
    assert "r.pre!==" not in script


def test_the_batch_script_has_no_newlines_and_no_line_comments():
    """A pasted `executeCode()` source loses newlines, and `//` would eat it."""
    captured = []
    PacketTracerEnterpriseServiceRuntime(
        lambda: [],
        lambda js, timeout: captured.append(js) or json.dumps({"results": []}),
    ).apply_actions([_enable(), _add_record()])

    assert "\n" not in captured[0]
    assert "//" not in captured[0]


def test_the_digest_helper_is_defined_once_per_batch():
    """One definition, however many actions the batch carries."""
    captured = []
    PacketTracerEnterpriseServiceRuntime(
        lambda: [],
        lambda js, timeout: captured.append(js) or json.dumps({"results": []}),
    ).apply_actions([_enable(), _add_record()])

    assert captured[0].count("function __dg(") == 1
    assert captured[0].count("function __er(") == 1


def test_the_dns_add_is_skipped_when_the_pre_read_already_shows_the_record():
    """The skip is decided in the script, from the pre-read, before any call."""
    captured = []
    PacketTracerEnterpriseServiceRuntime(
        lambda: [],
        lambda js, timeout: captured.append(js) or json.dumps({"results": []}),
    ).apply_actions([_add_record()])
    script = captured[0]

    assert (
        'if(r.pre_read&&pv===true){r.skip_reason="already_satisfied";}else{' in script
    )
    assert script.index("already_satisfied") < script.index("addARecordToNameServerDb")


# -- 5. verification observation facts -----------------------------------


def _expectation(kind, evidence_kind, expected, identifier="verify"):
    return ServiceVerificationExpectation(
        id=identifier,
        service_id="service/hq/dns",
        action_id="a",
        kind=kind,
        evidence_kind=evidence_kind,
        host_device_id="srv-1",
        host_device_name="__MCP_E6_SERVER",
        client_device_id="pc-1",
        client_device_name="__MCP_E6_PC",
        expected=expected,
    )


def test_a_direct_read_that_cannot_find_its_subject_is_unobservable():
    """`found=false` did not contradict anything: it observed nothing."""
    runtime = PacketTracerEnterpriseServiceRuntime(
        lambda: [],
        lambda js, timeout: json.dumps({"found": False, "enabled": False}),
    )

    row = runtime.verify(
        _expectation(
            ServiceVerificationKind.DIRECT_SERVICE_STATE,
            ServiceEvidenceKind.DIRECT_STATE,
            {"service_type": "dns", "records_json": "{}"},
        )
    )

    assert row.status is ActionExecutionStatus.UNOBSERVABLE
    assert row.observation is ObservationFact.SUBJECT_NOT_FOUND
    assert row.fresh_evidence is False


def test_a_direct_read_with_a_wrong_shaped_payload_is_unobservable():
    """A payload that is not the typed shape decides nothing."""
    runtime = PacketTracerEnterpriseServiceRuntime(
        lambda: [],
        lambda js, timeout: json.dumps({"found": 1, "enabled": "yes"}),
    )

    row = runtime.verify(
        _expectation(
            ServiceVerificationKind.DIRECT_SERVICE_STATE,
            ServiceEvidenceKind.DIRECT_STATE,
            {"service_type": "dns", "records_json": "{}"},
        )
    )

    assert row.status is ActionExecutionStatus.UNOBSERVABLE
    assert row.observation is ObservationFact.MALFORMED


def test_a_direct_read_that_never_arrived_is_unknown_not_failed():
    """A transport that delivered nothing is not evidence about the device."""
    runtime = PacketTracerEnterpriseServiceRuntime(lambda: [], lambda js, timeout: None)

    row = runtime.verify(
        _expectation(
            ServiceVerificationKind.DIRECT_SERVICE_STATE,
            ServiceEvidenceKind.DIRECT_STATE,
            {"service_type": "dns", "records_json": "{}"},
        )
    )

    assert row.status is ActionExecutionStatus.UNKNOWN
    assert row.observation is ObservationFact.ACCEPTANCE_UNKNOWN
    assert row.fresh_evidence is False


def test_an_incomplete_dns_window_is_inconclusive_not_a_contradiction():
    """Output with no terminal line decides neither direction."""
    responses = [
        json.dumps({"started": True, "before": "C:\\>"}),
        json.dumps({"found": True, "output": "C:\\>ping web.e6.example.local\n"}),
    ]
    runtime = PacketTracerEnterpriseServiceRuntime(
        lambda: [],
        lambda js, timeout: responses.pop(0),
        dns_timeout_seconds=0.0,
        convergence_interval_seconds=0.0,
    )

    row = runtime.verify(
        _expectation(
            ServiceVerificationKind.DNS_RESOLUTION,
            ServiceEvidenceKind.BEHAVIORAL,
            {"hostname": "web.e6.example.local", "address": "198.18.160.10"},
        )
    )

    assert row.status is ActionExecutionStatus.UNKNOWN
    assert row.observation is ObservationFact.INCONCLUSIVE
    assert row.cause == "incomplete_window"


def test_a_blocked_pager_is_inconclusive_not_a_failure():
    """The command was refused, so the service was never exercised."""
    runtime = PacketTracerEnterpriseServiceRuntime(
        lambda: [],
        lambda js, timeout: json.dumps(
            {"started": False, "blocked": True, "before": ""}
        ),
        dns_timeout_seconds=0.0,
        convergence_interval_seconds=0.0,
    )

    row = runtime.verify(
        _expectation(
            ServiceVerificationKind.DNS_RESOLUTION,
            ServiceEvidenceKind.BEHAVIORAL,
            {"hostname": "web.e6.example.local", "address": "198.18.160.10"},
        )
    )

    assert row.status is ActionExecutionStatus.UNKNOWN
    assert row.observation is ObservationFact.INCONCLUSIVE
    assert row.cause == "pager_active"


def test_a_marker_present_before_the_request_is_inconclusive():
    """The real marker-before-request path, which the baseline fixture missed.

    `tests/test_service_runtime.py` cannot reach it: its dispatcher answers
    any script containing "deleteClient", and the start script contains that
    call. Here the start answer is bound to the start script instead.
    """
    marker = "MCP_E6_HTTP_OK_FRESH"
    calls = []

    def send_and_wait(js, timeout):
        calls.append(js)
        if "createClient()" in js:
            return json.dumps({"started": True, "content_before": marker})
        return json.dumps({"released": True})

    runtime = PacketTracerEnterpriseServiceRuntime(
        lambda: [],
        send_and_wait,
        http_timeout_seconds=0.0,
        convergence_interval_seconds=0.0,
    )

    row = runtime.verify(
        _expectation(
            ServiceVerificationKind.HTTP_FETCH,
            ServiceEvidenceKind.BEHAVIORAL,
            {"address": "198.18.160.10", "marker": marker},
            identifier="verify-http",
        )
    )

    assert row.status is ActionExecutionStatus.UNKNOWN
    assert row.observation is ObservationFact.INCONCLUSIVE
    assert row.cause == "marker_present_before_request"
    assert row.observed["released"] == "released"
    assert "deleteClient" in calls[-1]


def test_no_content_change_by_the_deadline_is_inconclusive():
    """Nothing was retrieved, so nothing about the server was observed."""
    responses = [
        json.dumps({"started": True, "content_before": ""}),
        json.dumps({"found": True, "content": ""}),
        json.dumps({"released": True}),
    ]
    runtime = PacketTracerEnterpriseServiceRuntime(
        lambda: [],
        lambda js, timeout: responses.pop(0),
        http_timeout_seconds=0.0,
        convergence_interval_seconds=0.0,
    )

    row = runtime.verify(
        _expectation(
            ServiceVerificationKind.HTTP_FETCH,
            ServiceEvidenceKind.BEHAVIORAL,
            {"address": "198.18.160.10", "marker": "M"},
            identifier="verify-http",
        )
    )

    assert row.status is ActionExecutionStatus.UNKNOWN
    assert row.observation is ObservationFact.INCONCLUSIVE
    assert row.cause == "no_response_within_deadline"


def test_a_client_that_did_not_start_is_inconclusive_and_is_released():
    """`go()` false means no request was made, and the client is still owned."""
    calls = []

    def send_and_wait(js, timeout):
        calls.append(js)
        if "createClient()" in js:
            return json.dumps({"started": False, "content_before": ""})
        return json.dumps({"released": True})

    runtime = PacketTracerEnterpriseServiceRuntime(
        lambda: [],
        send_and_wait,
        http_timeout_seconds=0.0,
        convergence_interval_seconds=0.0,
    )

    row = runtime.verify(
        _expectation(
            ServiceVerificationKind.HTTP_FETCH,
            ServiceEvidenceKind.BEHAVIORAL,
            {"address": "198.18.160.10", "marker": "M"},
            identifier="verify-http",
        )
    )

    assert row.observation is ObservationFact.INCONCLUSIVE
    assert row.cause == "client_go_false"
    assert "deleteClient" in calls[-1]


def test_an_https_mode_the_client_denies_is_a_contradiction():
    """`setHttps(true)` then `isHttps()` false is an observed contradiction."""
    calls = []

    def send_and_wait(js, timeout):
        calls.append(js)
        if "createClient()" in js:
            return json.dumps(
                {"started": True, "content_before": "", "https_mode": False}
            )
        return json.dumps({"released": True})

    runtime = PacketTracerEnterpriseServiceRuntime(
        lambda: [],
        send_and_wait,
        http_timeout_seconds=0.0,
        convergence_interval_seconds=0.0,
    )

    row = runtime.verify(
        _expectation(
            ServiceVerificationKind.HTTPS_FETCH,
            ServiceEvidenceKind.BEHAVIORAL,
            {"address": "198.18.160.10", "marker": "M", "scheme": "https"},
            identifier="verify-https",
        )
    )

    assert row.status is ActionExecutionStatus.FAILED
    assert row.observation is ObservationFact.CONTRADICTED
    assert row.cause == "https_mode_not_confirmed"
    assert row.fresh_evidence is True


def test_an_absent_https_mode_is_malformed_because_missing_is_not_false():
    """A payload that did not report the mode observed nothing about it."""
    calls = []

    def send_and_wait(js, timeout):
        calls.append(js)
        if "createClient()" in js:
            return json.dumps({"started": True, "content_before": ""})
        return json.dumps({"released": True})

    runtime = PacketTracerEnterpriseServiceRuntime(
        lambda: [],
        send_and_wait,
        http_timeout_seconds=0.0,
        convergence_interval_seconds=0.0,
    )

    row = runtime.verify(
        _expectation(
            ServiceVerificationKind.HTTPS_FETCH,
            ServiceEvidenceKind.BEHAVIORAL,
            {"address": "198.18.160.10", "marker": "M", "scheme": "https"},
            identifier="verify-https",
        )
    )

    assert row.status is ActionExecutionStatus.UNOBSERVABLE
    assert row.observation is ObservationFact.MALFORMED
    assert row.cause == "https_mode_absent"


def test_a_release_that_did_not_come_back_is_recorded_as_failed():
    """A leaked owned client must be visible, not reported as released."""
    state = {"calls": 0}

    def send_and_wait(js, timeout):
        state["calls"] += 1
        if "createClient()" in js:
            return json.dumps({"started": True, "content_before": ""})
        if "getLastPageContent" in js:
            return json.dumps({"found": True, "content": "PAGE"})
        return None

    runtime = PacketTracerEnterpriseServiceRuntime(
        lambda: [],
        send_and_wait,
        http_timeout_seconds=0.0,
        convergence_interval_seconds=0.0,
    )

    row = runtime.verify(
        _expectation(
            ServiceVerificationKind.HTTP_FETCH,
            ServiceEvidenceKind.BEHAVIORAL,
            {"address": "198.18.160.10", "marker": ""},
            identifier="verify-http",
        )
    )

    assert row.observed["released"] == "release_failed"


def test_a_reader_exception_is_unknown_and_names_the_type():
    """A crashed reader observed nothing, and the plan is not a session failure."""

    def send_and_wait(js, timeout):
        raise RuntimeError("synthetic reader failure")

    runtime = PacketTracerEnterpriseServiceRuntime(lambda: [], send_and_wait)

    row = runtime.verify(
        _expectation(
            ServiceVerificationKind.DIRECT_SERVICE_STATE,
            ServiceEvidenceKind.DIRECT_STATE,
            {"service_type": "dns", "records_json": "{}"},
        )
    )

    assert row.status is ActionExecutionStatus.UNKNOWN
    assert row.observation is ObservationFact.INCONCLUSIVE
    assert row.cause == "exception:RuntimeError"


def test_ntp_and_tftp_state_explicitly_that_nothing_was_attempted():
    """NOT_ATTEMPTED is a fact; UNSPECIFIED would be silence."""
    runtime = PacketTracerEnterpriseServiceRuntime(lambda: [], lambda js, timeout: "{}")

    for kind in (
        ServiceVerificationKind.NTP_SYNC,
        ServiceVerificationKind.TFTP_RETRIEVE,
    ):
        row = runtime.verify(
            _expectation(
                kind, ServiceEvidenceKind.BEHAVIORAL, {}, identifier=kind.value
            )
        )

        assert row.status is ActionExecutionStatus.UNOBSERVABLE
        assert row.observation is ObservationFact.NOT_ATTEMPTED
        assert row.fresh_evidence is False


# -- 6. golden scripts ----------------------------------------------------

#: The vendor-call surface of every read the baseline already performed. These
#: strings are frozen, so a refactor cannot quietly change which documented
#: API the product calls. Equality here preserves the CALL SURFACE only: it is
#: not evidence of classifier equivalence, ownership, provenance or any live
#: capability.
_GOLDEN_DIRECT_DNS = (
    'var d=ipc.network().getDevice("__MCP_E6_SERVER");'
    'var p=d&&d.getProcess("DnsServer");'
    "var out={found:!!p,enabled:false};if(p){out.enabled=!!p.isEnabled();"
    'out.records={};var wanted=JSON.parse("{\\"web.e6.example.local\\":\\"198.18.160.10\\"}");'
    "for(var k in wanted){if(p.getARecordWithAddress(k,wanted[k])){"
    "out.records[k]=wanted[k];}}}reportResult(JSON.stringify(out));"
)

_GOLDEN_HTTP_INSPECT = (
    "var bag=this.__mcpE6HttpClients||{};"
    'var slot=bag["verify-http"];var p=slot&&slot.client;'
    "reportResult(JSON.stringify({found:!!p,"
    "content:p?String(p.getLastPageContent()):''}));"
)


def test_the_direct_dns_read_back_payload_is_byte_identical_to_the_baseline():
    """The documented getter surface of the direct read-back is frozen."""
    calls = []
    PacketTracerEnterpriseServiceRuntime(
        lambda: [], lambda js, timeout: calls.append(js) or None
    ).verify(
        _expectation(
            ServiceVerificationKind.DIRECT_SERVICE_STATE,
            ServiceEvidenceKind.DIRECT_STATE,
            {
                "service_type": "dns",
                "records_json": '{"web.e6.example.local":"198.18.160.10"}',
            },
        )
    )

    assert calls[0] == _GOLDEN_DIRECT_DNS


def test_the_http_inspect_payload_is_byte_identical_to_the_baseline():
    """The owned-client page read is frozen."""
    observed = PacketTracerEnterpriseServiceRuntime._background_http_inspect(
        "verify-http"
    )

    assert observed == _GOLDEN_HTTP_INSPECT


def test_the_https_start_adds_only_the_mode_calls_to_the_http_start():
    """The one intended new script, and nothing else changed with it."""
    url = json.dumps("https://198.18.160.10/")
    http = PacketTracerEnterpriseServiceRuntime._background_http_start("v", url)
    https = PacketTracerEnterpriseServiceRuntime._background_https_start("v", url)

    assert https == http.replace(
        "var started=",
        "if(p){p.setHttps(true);}var https_mode=p?!!p.isHttps():null;var started=",
    )
    assert "p.setHttps(true)" in https
    assert "p.isHttps()" in https
    assert https.index("p.setHttps(true)") < https.index("p.go(")


def test_a_bridge_observation_kind_is_never_silently_a_payload():
    """The four kinds stay distinct values, so none can stand for another."""
    assert len({member.value for member in BridgeObservationKind}) == len(
        BridgeObservationKind
    )
