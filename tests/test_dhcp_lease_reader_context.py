"""The real generated reader retains each index and refuses unqualified ends."""

import subprocess
from types import SimpleNamespace

import pytest

from packet_tracer_mcp.infrastructure.execution.dhcp_lease_reader import (
    LeaseReaderContext,
)
from packet_tracer_mcp.infrastructure.execution.enterprise_service_runtime import (
    PacketTracerEnterpriseServiceRuntime,
)
from tests.service_qualification_engine import require_node


def _read(body, *, context=None, window=4, setup=""):
    require_node()
    header = (
        "var calls=[];var pool={getDhcpPoolName:function(){return 'serverPool';},"
        "getLeaseAt:function(i){calls.push(i);" + body + "}};"
        "var sp={getPool:function(){return pool;},getPoolCount:function(){return 1;},"
        "getPoolAt:function(){return pool;}};"
        "var ipc={network:function(){return {getDevice:function(){return {"
        "getProcess:function(){return {getDhcpServerProcessByPortName:function(){"
        "return sp;}};}};}};}};"
        "function reportResult(x){process.stdout.write(x);}"
    )

    header += setup

    def send(script, _timeout):
        return subprocess.run(
            ["node", "-e", header + 'eval(require("fs").readFileSync(0,"utf8"));'],
            input=script,
            text=True,
            capture_output=True,
            check=True,
        ).stdout

    kwargs = {} if context is None else {"lease_reader_context": context}
    runtime = PacketTracerEnterpriseServiceRuntime(lambda: [], send, **kwargs)
    result = runtime._native_group_snapshot(
        SimpleNamespace(
            host_device_name="Server", expected={"server_interface": "FastEthernet0"}
        ),
        [],
        window,
        "serverPool",
        [],
    )
    return result.payload


def test_unqualified_native_exception_cannot_end_a_scan():
    """Knowing a vendor error text does not establish source/build/channel."""
    result = _read("throw new Error('invalid vector subscript');")
    assert result["termination"] == "error"
    assert result["scan_error"]


@pytest.mark.parametrize(
    "first", ["null", "throw new Error('invalid vector subscript')"]
)
def test_reader_retains_a_row_after_an_alleged_end(first):
    """A stateful later row must be observed and remain non-authorizing."""
    initial = "return null" if first == "null" else first
    body = (
        "if(i===0){" + initial + ";}"
        "if(i===1){return {ipAddress:'192.0.2.100',macAddress:'0011.2233.4455',"
        "leaseTime:3600,port:'FastEthernet0'};}return null;"
    )
    result = _read(body)
    assert result["termination"] == "error"
    assert result["entries"][1]["row"]["ipAddress"] == "192.0.2.100"


@pytest.mark.parametrize("count", [0, 1, 3, 36])
def test_observed_prefix_retains_rows_and_confirming_index(count):
    """The generated reader observes empty, partial and selected full loads."""
    context = LeaseReaderContext("1" * 40, "2" * 40, "9.0.1.0858", "file")
    body = (
        "if(i<" + str(count) + "){return {ipAddress:'192.0.2.'+(100+i),"
        "macAddress:'0011.2233.'+(4096+i).toString(16),leaseTime:3600,"
        "port:'FastEthernet0'};}throw new Error('invalid vector subscript');"
    )
    result = _read(body, context=context, window=count + 2)
    assert result["termination"] == "end_throw", result
    assert len(result["rows"]) == count
    assert result["first_end_index"] == count
    assert result["confirming_index"] == count + 1
    assert result["entries"][count]["error"] == "invalid vector subscript"
    assert result["entries"][count + 1]["end_semantics"] == "observed_native_index_end"
    assert result["reader_provenance"]["source_sha"] == "1" * 40


@pytest.mark.parametrize(
    "context",
    [
        LeaseReaderContext("1" * 40, "2" * 40, "9.0.1.9999", "file"),
        LeaseReaderContext("1" * 40, "2" * 40, "9.0.1.0858", "http"),
        LeaseReaderContext("", "2" * 40, "9.0.1.0858", "file"),
        LeaseReaderContext("1" * 40, "2" * 40, "9.0.1.0858", "file", "legacy-reader"),
    ],
)
def test_unknown_scope_does_not_inherit_native_convention(context):
    """A changed build, channel, source or reader remains unqualified."""
    result = _read("throw new Error('invalid vector subscript');", context=context)
    assert result["termination"] == "error"
    assert result["reader_provenance"] == {}


def test_conflicting_identity_rows_never_authorize_a_prefix():
    """Distinct addresses on one MAC remain visible and non-authorizing."""
    body = (
        "if(i<2){return {ipAddress:'192.0.2.'+(100+i),macAddress:'0011.2233.4455',"
        "leaseTime:3600,port:'FastEthernet0'};}return null;"
    )
    result = _read(body)
    assert result["termination"] == "error"
    assert len(result["rows"]) == 2


@pytest.mark.parametrize("failure", ["index", "lease_time", "field_type"])
def test_terminal_preserves_decoder_refusal(failure):
    """Raw classification cannot erase a backend's invalid observation."""
    from packet_tracer_mcp.domain.enterprise.services.dhcp_lease_evidence import (
        classify_lease_scan,
    )
    from packet_tracer_mcp.domain.enterprise.services.qualification_terminal_evidence import (
        sp2_mixed_scan_complete,
    )
    from packet_tracer_mcp.infrastructure.execution.dhcp_lease_reader import decode_scan

    row = {
        "ipAddress": "192.0.2.100",
        "macAddress": "0011.2233.4455",
        "leaseTime": 3600,
        "port": "FastEthernet0",
        "ipAddress_type": "string",
        "macAddress_type": "string",
        "leaseTime_type": "number",
        "port_type": "string",
    }
    raw = {
        "requested": "serverPool",
        "name": "serverPool",
        "found": True,
        "max": 1,
        "window": 3,
        "error": "",
        "entries": [
            {"index": 0, "return_kind": "object", "error": "", "row": row},
            {"index": 1, "return_kind": "null", "error": "", "row": None},
            {"index": 2, "return_kind": "null", "error": "", "row": None},
        ],
    }
    if failure == "index":
        raw["entries"][1]["index"] = True
    elif failure == "lease_time":
        row["leaseTime"] = -1
    else:
        row["ipAddress_type"] = "number"
    decoded = decode_scan(raw, None)
    assert decoded["scan_error"]
    scan = classify_lease_scan(decoded, pool_name="serverPool")
    assert not sp2_mixed_scan_complete(scan, [("192.0.2.100", "001122334455")])


@pytest.mark.parametrize(
    "kind,error,qualified",
    [
        ("field_throw", "invalid vector subscript", True),
        ("throw", "invalid vector subscript", False),
        ("throw", "reader failed", True),
    ],
)
def test_native_default_rejects_an_unreadable_tail(monkeypatch, kind, error, qualified):
    """Native intended rows cannot hide an unreadable remainder of their scan."""
    import json

    from test_native_dhcp_group_evidence import (
        MAC,
        ActionExecutionStatus,
        _assigned,
        _group_expectations,
        _row,
        _runtime,
        _scan,
        _ScriptedBridge,
        _verify_group,
    )

    expectations, group = _group_expectations()
    readings = {"PC1": _assigned("PC1", 0), "PC2": _assigned("PC2", 1)}
    rows = [_row(readings[name][0], MAC[name]) for name in readings]
    entries = []
    for index, row in enumerate(rows):
        typed = {
            **row,
            **{
                key + "_type": ("number" if key == "leaseTime" else "string")
                for key in row
            },
        }
        entries.append(
            {"index": index, "return_kind": "object", "error": "", "row": typed}
        )
    entries += [
        {"index": index, "return_kind": kind, "error": error, "row": None}
        for index in (2, 3)
    ]
    raw = _scan(group, readings, rows)
    raw.update(window=4, entries=entries)
    runtime = _runtime(monkeypatch, _ScriptedBridge([raw, raw]))
    runtime._lease_reader_context = (
        LeaseReaderContext("a" * 40, "b" * 40, "9.0.1.0858", "file")
        if qualified
        else None
    )
    results = _verify_group(runtime, expectations)
    assert all(
        row.status is not ActionExecutionStatus.VERIFIED for row in results.values()
    )
    trace = json.loads(
        next(
            row.observed["group_trace_json"]
            for row in results.values()
            if row.observed["group_trace_json"]
        )
    )
    assert trace[0]["lease_snapshot"]["scan_error"] == error
    assert trace[0]["lease_snapshot"]["entries"][2]["return_kind"] == kind


@pytest.mark.parametrize("first_native", [True, False])
def test_one_native_failure_and_one_null_are_not_repeated_confirmation(first_native):
    """Different returned outcomes cannot confirm the empirical exception rule."""
    index = 0 if first_native else 1
    body = (
        "if(i==="
        + str(index)
        + "){throw new Error('invalid vector subscript');}return null;"
    )
    context = LeaseReaderContext("1" * 40, "2" * 40, "9.0.1.0858", "file")
    result = _read(body, context=context, window=2)
    assert result["termination"] == "error"
    assert result["scan_error"] == "scan_end_inconsistent"


@pytest.mark.parametrize(
    "body,cause",
    [
        (
            "return {ipAddress:'192.0.2.100',macAddress:'0011.2233.4455',leaseTime:3600,port:'FastEthernet0'};",
            "scan_bound_exhausted",
        ),
        (
            "var r={ipAddress:'192.0.2.100',leaseTime:3600,port:'FastEthernet0'};Object.defineProperty(r,'macAddress',{get:function(){throw new Error('invalid vector subscript');}});return r;",
            "invalid vector subscript",
        ),
        (
            "if(i===0){return {ipAddress:'192.0.2.100',macAddress:'0011.2233.4455',leaseTime:3600,port:''};}return null;",
            "lease_row_malformed",
        ),
    ],
)
def test_stateful_reader_failures_remain_raw_and_non_authorizing(body, cause):
    """Cap exhaustion and failed/malformed fields are distinct raw outcomes."""
    context = LeaseReaderContext("1" * 40, "2" * 40, "9.0.1.0858", "file")
    result = _read(body, context=context)
    assert result["termination"] == "error"
    if cause == "scan_bound_exhausted":
        # Repeated rows are independently invalid even before the cap.
        assert result["scan_error"]
        assert len(result["entries"]) == 4
    else:
        assert result["scan_error"] == cause


def test_composition_does_not_qualify_a_foreign_backend():
    """Matching version text does not establish the native backend identity."""
    from packet_tracer_mcp.infrastructure.execution.dhcp_lease_reader import (
        reader_context,
    )

    assert (
        reader_context(
            {
                "source_sha": "1" * 40,
                "source_tree": "2" * 40,
                "clean": True,
                "build": "9.0.1.0858",
                "channel": "file",
                "backend": "foreign",
            }
        )
        is None
    )


def test_competing_pool_identity_is_observed_from_the_returned_object():
    """A foreign getPool result cannot masquerade as a requested physical pool."""
    from packet_tracer_mcp.infrastructure.execution.enterprise_service_runtime import (
        _competing_pool_rows,
    )

    setup = (
        "var advertised={getDhcpPoolName:function(){return 'competing';}};"
        "var foreign={getDhcpPoolName:function(){return 'foreign';},getMaxUsers:function(){return 1;},getLeaseAt:function(){return null;}};"
        "sp.getPoolCount=function(){return 2;};"
        "sp.getPoolAt=function(i){return i===0?pool:advertised;};"
        "sp.getPool=function(n){return n==='serverPool'?pool:foreign;};"
    )
    result = _read("return null;", setup=setup)
    assert _competing_pool_rows(result, "serverPool", None) is None


@pytest.mark.parametrize("failure", ["lease_time", "field_type", "index", "overflow"])
def test_domain_calibration_preserves_backend_refusal(failure):
    """A second classifier cannot authorize a scan the backend refused."""
    from packet_tracer_mcp.domain.enterprise.services.dhcp_lease_evidence import (
        CalibrationState,
        assess_lease_calibration,
        classify_lease_scan,
    )
    from packet_tracer_mcp.infrastructure.execution.dhcp_lease_reader import decode_scan

    row = {
        "ipAddress": "192.0.2.100",
        "macAddress": "0011.2233.4455",
        "leaseTime": 3600,
        "port": "FastEthernet0",
        "ipAddress_type": "string",
        "macAddress_type": "string",
        "leaseTime_type": "number",
        "port_type": "string",
    }
    empty = {
        "requested": "serverPool",
        "name": "serverPool",
        "found": True,
        "max": 2,
        "window": 3,
        "error": "",
        "entries": [
            {"index": i, "return_kind": "null", "error": "", "row": None}
            for i in range(3)
        ],
    }
    malformed = {
        **empty,
        "entries": [
            {"index": 0, "return_kind": "object", "error": "", "row": row},
            *[dict(item) for item in empty["entries"][1:]],
        ],
    }
    if failure == "lease_time":
        row["leaseTime"] = -1
    elif failure == "overflow":
        row["leaseTime"] = 10**1000
    elif failure == "field_type":
        row["ipAddress_type"] = "number"
    else:
        malformed["entries"][1]["index"] = True
    scans = [
        classify_lease_scan(decode_scan(raw, None), pool_name="serverPool")
        for raw in (empty, malformed)
    ]
    assert not scans[1].clean
    assert not scans[1].observed
    assert scans[1].entries
    calibration = assess_lease_calibration(
        [CalibrationState("empty", scans[0]), CalibrationState("one", scans[1])],
        pool="serverPool",
        capacity=2,
        fixture_macs=["0011.2233.4455"],
    )
    assert calibration.conclusion.value == "inconclusive"
    assert not calibration.null_ends_rows


@pytest.mark.parametrize("kind", ["null", "throw"])
def test_non_object_tail_cannot_carry_a_hidden_lease_row(kind):
    """Contradictory return-kind and field observations remain non-authorizing."""
    from packet_tracer_mcp.infrastructure.execution.dhcp_lease_reader import decode_scan

    raw = {
        "window": 2,
        "entries": [
            {
                "index": i,
                "return_kind": kind,
                "error": "" if kind == "null" else "invalid vector subscript",
                "row": {"ipAddress": "192.0.2.100"},
            }
            for i in range(2)
        ],
    }
    context = LeaseReaderContext("1" * 40, "2" * 40, "9.0.1.0858", "file")
    result = decode_scan(raw, context)
    assert result["termination"] == "error"
    assert result["scan_error"]
    assert result["entries"][0]["row"] == {"ipAddress": "192.0.2.100"}


@pytest.mark.parametrize("kind", ["field_throw", "object", "undefined"])
def test_first_diagnostic_probe_does_not_accept_field_or_shape_failures(kind):
    """The bounded first-probe exception is limited to observed index errors."""
    from packet_tracer_mcp.application.server_service_qualification.workflows.fastloop import (
        _sp2_first_probe_read,
    )
    from packet_tracer_mcp.domain.enterprise.services.dhcp_lease_evidence import (
        LeaseScan,
    )

    scan = LeaseScan(
        "serverPool",
        False,
        "backend_scan_refused",
        entries=(
            {"index": 0, "return_kind": kind, "error": "read failed", "row": None},
        ),
    )
    assert not _sp2_first_probe_read(scan)


def test_incomplete_competing_scan_keeps_positive_counterevidence(tmp_path):
    """A valid wrong-pool row survives a later failure but permits no serving."""
    import json

    from test_sp2_mixed_product_flow import _CompetingRowTransport, _leases, _run

    from packet_tracer_mcp.infrastructure.execution.transport_outcome import (
        BridgeDispatchOutcome,
    )

    class Incomplete(_CompetingRowTransport):
        def dispatch_and_wait(self, script, timeout):
            outcome = super().dispatch_and_wait(script, timeout)
            if "var group=" not in script or not outcome.body:
                return outcome
            payload = json.loads(outcome.body)
            for scan in payload.get("competing", []):
                if scan["pool_name"] == self.pool:
                    scan["entries"][-1].update(
                        return_kind="field_throw", error="field failed", row=None
                    )
            return BridgeDispatchOutcome(
                dispatch=outcome.dispatch,
                result=outcome.result,
                body=json.dumps(payload),
            )

    plans, _physical, result, transport = _run(
        tmp_path,
        "partial-counterevidence",
        transport_factory=lambda engine: Incomplete(
            engine, client="BR1-DEFAULT-PC-01", pool="serverPool"
        ),
    )
    assert transport.planted
    rows = _leases(plans, result.service_result.verification_results)
    assert (
        rows["BR1-DEFAULT-PC-01"].observed["local_failure_cause"]
        == "competing_pool_row"
    )
    assert rows["BR1-DEFAULT-PC-02"].status.value != "verified"
