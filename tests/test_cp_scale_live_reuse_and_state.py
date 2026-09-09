"""Test-only reuse and bounded-state measurements; never product admission."""
from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass, replace
from datetime import datetime, timezone
import inspect
import json
from pathlib import Path

import pytest

from src.packet_tracer_mcp.application.cp_scale_live.sequence import execute_stage_sequence, StageStepResult


@dataclass(frozen=True)
class DocumentAuditTarget:
    stages: tuple[str, ...]
    max_errors: int
    journal_operations: tuple[str, ...] = ("read", "check", "check", "seal")


@dataclass(frozen=True)
class Cursor:
    ordinal: int
    token: str


@dataclass(frozen=True)
class DocumentReceipt:
    name: str
    errors: int
    journal: tuple[tuple[int, str], ...]
    warnings: tuple[str, ...]


class MemoryDocumentReader:
    def __init__(self, receipts, events):
        self.receipts = receipts
        self.events = events
        self.index = 0

    def read(self, name, cursor):
        self.events.append(("read", name, cursor))
        value = self.receipts[self.index]
        assert value.name == name
        self.index += 1
        return value


class AuditReceiptAdapter:
    def __init__(self, events):
        self.events = events

    def seal(self, receipt, cursor):
        self.events.append(("seal", receipt.name, receipt.journal))
        return Cursor(cursor.ordinal + 1, f"receipt-{cursor.ordinal + 1}")


class MaximumErrorPolicy:
    def __init__(self, maximum, events):
        self.maximum = maximum
        self.events = events

    def accepts(self, receipt):
        self.events.append(("accept", receipt.name, receipt.errors))
        return receipt.errors <= self.maximum


def _document_sequence(target, errors=None):
    receipts = tuple(DocumentReceipt(name, (errors or {}).get(index, 0),
        tuple(enumerate(target.journal_operations, 1)), (f"{name}:warning", f"{name}:warning"))
        for index, name in enumerate(target.stages))
    events = []
    acquired = []
    reader = MemoryDocumentReader(receipts, events)
    audit = AuditReceiptAdapter(events)
    policy = MaximumErrorPolicy(target.max_errors, events)
    initial = Cursor(0, "initial")
    def step(name, cursor):
        receipt = reader.read(name, cursor)
        following = audit.seal(receipt, cursor)
        result = StageStepResult(receipt, following, policy.accepts(receipt), receipt.warnings)
        acquired.append(result)
        return result
    result = execute_stage_sequence(target.stages, initial, step)
    return result, tuple(acquired), receipts, events, initial


def _assert_sequence_integrity(result, acquired, receipts):
    assert len(result.steps) == len(acquired)
    for actual, expected, receipt in zip(result.steps, acquired, receipts):
        assert actual is expected
        assert actual.value is receipt
        assert actual.value.journal is receipt.journal
        assert actual.value.journal == ((1, "read"), (2, "check"), (3, "check"), (4, "seal"))
    assert result.continuity is acquired[-1].continuity
    assert result.secondary_failures == tuple(warning for receipt in receipts[:len(acquired)] for warning in receipt.warnings)


@pytest.mark.parametrize("defect", ["drop", "duplicate", "copy", "continuity", "truncate_journal", "secondaries"])
def test_sequence_assertions_detect_corrupted_snapshots(defect):
    target = DocumentAuditTarget(("capture", "inspect", "seal"), 0)
    result, acquired, receipts, _, _ = _document_sequence(target)
    if defect == "drop":
        broken = replace(result, steps=result.steps[:-1])
    elif defect == "duplicate":
        broken = replace(result, steps=(*result.steps, result.steps[-1]))
    elif defect == "copy":
        broken = replace(result, steps=(replace(result.steps[0], value=replace(receipts[0])), *result.steps[1:]))
    elif defect == "continuity":
        broken = replace(result, continuity=replace(result.continuity))
    elif defect == "truncate_journal":
        # Keep identity intact: this control must fail for missing journal data,
        # not merely because another receipt/step object was substituted.
        object.__setattr__(receipts[0], "journal", receipts[0].journal[:-1])
        broken = result
    else:
        broken = replace(result, secondary_failures=result.secondary_failures[::-1])
    with pytest.raises(AssertionError):
        _assert_sequence_integrity(broken, acquired, receipts)


@pytest.mark.parametrize("maximum,expected_count", [(0, 2), (2, 3)])
def test_noncanonical_target_uses_injected_policy_and_stops_at_first_failure(maximum, expected_count):
    target = DocumentAuditTarget(("capture", "inspect", "seal"), maximum)
    result, acquired, receipts, events, initial = _document_sequence(target, {1: 2})
    _assert_sequence_integrity(result, acquired, receipts)
    assert len(result.steps) == expected_count
    assert result.succeeded is (maximum == 2)
    assert [item[:2] for item in events] == [
        ("read", "capture"), ("seal", "capture"), ("accept", "capture"),
        ("read", "inspect"), ("seal", "inspect"), ("accept", "inspect"),
    ] + ([("read", "seal"), ("seal", "seal"), ("accept", "seal")] if maximum == 2 else [])
    reads = [item[2] for item in events if item[0] == "read"]
    assert reads[0] is initial
    assert all(reads[index] is acquired[index - 1].continuity for index in range(1, expected_count))
    assert result.secondary_failures == ("capture:warning", "capture:warning", "inspect:warning", "inspect:warning") + (
        ("seal:warning", "seal:warning") if maximum == 2 else ())


def test_opaque_duplicate_stage_ids_are_executed_in_order_without_deduplication():
    target = DocumentAuditTarget(("capture", "capture", "seal"), 0)
    result, acquired, receipts, events, _ = _document_sequence(target)
    _assert_sequence_integrity(result, acquired, receipts)
    assert [item[1] for item in events if item[0] == "read"] == ["capture", "capture", "seal"]
    assert result.steps[0].value is not result.steps[1].value


@pytest.mark.parametrize("count", [1, 2, 4])
def test_mechanism_snapshot_is_linear_and_has_no_completed_history(count):
    target = DocumentAuditTarget(("load", "parse", "inspect", "seal")[:count], 0)
    result, acquired, receipts, _, _ = _document_sequence(target)
    _assert_sequence_integrity(result, acquired, receipts)
    assert len(result.steps) == len(target.stages)
    assert len({id(item.value) for item in result.steps}) == count
    assert sum(len(item.value.journal) for item in result.steps) == len(target.journal_operations) * count
    assert tuple(field.name for field in fields(result.continuity)) == ("ordinal", "token")
    for step in result.steps:
        assert step.value.journal == ((1, "read"), (2, "check"), (3, "check"), (4, "seal"))
        assert not any(isinstance(getattr(step.continuity, field.name), (DocumentReceipt, tuple, list))
                       for field in fields(step.continuity))


@pytest.mark.parametrize("failed_at", [None, 257])
def test_large_sequence_reuses_local_accumulators_and_freezes_once(failed_at):
    stages = tuple(f"stage-{index % 11}" for index in range(512))
    initial = Cursor(0, "initial")
    acquired = []
    calls = []
    accumulator_ids = []

    def step(stage, continuity):
        frame = inspect.currentframe()
        assert frame is not None and frame.f_back is not None
        caller = frame.f_back
        try:
            accumulator_ids.append((
                id(caller.f_locals["completed"]),
                id(caller.f_locals["secondaries"]),
            ))
        finally:
            del caller
            del frame
        ordinal = len(calls)
        calls.append(stage)
        following = Cursor(ordinal + 1, f"cursor-{ordinal + 1}")
        result = StageStepResult(
            DocumentReceipt(stage, 0, ((1, "read"),), ()),
            following,
            ordinal != failed_at,
            (f"secondary-{ordinal % 7}", f"secondary-{ordinal % 7}"),
        )
        acquired.append(result)
        return result

    result = execute_stage_sequence(stages, initial, step)
    expected_count = len(stages) if failed_at is None else failed_at + 1

    assert len(set(item[0] for item in accumulator_ids)) == 1
    assert len(set(item[1] for item in accumulator_ids)) == 1
    assert isinstance(result.steps, tuple)
    assert isinstance(result.secondary_failures, tuple)
    assert result.steps == tuple(acquired)
    assert all(actual is expected for actual, expected in zip(result.steps, acquired))
    assert calls == list(stages[:expected_count])
    assert len(result.steps) == expected_count
    assert result.continuity is acquired[-1].continuity
    assert result.succeeded is (failed_at is None)
    assert result.secondary_failures == tuple(
        value
        for ordinal in range(expected_count)
        for value in (f"secondary-{ordinal % 7}", f"secondary-{ordinal % 7}")
    )


@dataclass(frozen=True)
class MeasurementPlan:
    required_reads: tuple[str, ...] = ("before", "after")
    diagnostic_attempts: tuple[str, ...] = ("diagnostic",)
    archive_phases: tuple[str, ...] = ("precleanup", "cleanup-incomplete")
    journal_operations: tuple[str, ...] = ("first", "second", "first")
    preflight_checks: tuple[str, ...] = ("request", "imports", "repository", "process")
    envelope_bytes: int = 8192
    bytes_per_stage: int = 16384


MEASUREMENT_PLAN = MeasurementPlan()
FIXED_TIME = datetime(2026, 9, 9, tzinfo=timezone.utc)


def _cp_snapshot(count):
    from src.packet_tracer_mcp.application.cp_scale_live.contracts import (
        CPScaleLiveStageResult, CPScaleStageContinuity, CPScaleStageReport, CPScaleMutationScope,
        CPScaleObservationRecord, CPScaleDiagnosticRecord,
    )
    from src.packet_tracer_mcp.application.cp_scale_live.run_contracts import CPScaleStageProgress
    from src.packet_tracer_mcp.application.cp_scale_live.run_state import (
        CPScaleQualificationState, CPScaleProgressState, CPScaleTerminalState, publication_snapshot,
    )
    from src.packet_tracer_mcp.application.use_cases.compose_cp_scale_canonical import CPScaleCanonicalStageProjection
    from src.packet_tracer_mcp.application.use_cases.qualify_cp_scale_live import CPScaleEvidenceArchive
    from src.packet_tracer_mcp.domain.models.plans import TopologyPlan
    from src.packet_tracer_mcp.domain.enterprise.models.configuration import ConfigurationPlan
    from src.packet_tracer_mcp.domain.enterprise.models.control_plane import ControlPlanePlan
    from src.packet_tracer_mcp.domain.enterprise.models.configuration_runtime import ConfigurationApplicationResult, ConfigurationApplicationStatus
    from src.packet_tracer_mcp.domain.enterprise.models.control_plane_runtime import ControlPlaneApplicationResult
    from src.packet_tracer_mcp.domain.enterprise.models.physical_deployment import PhysicalDeploymentResult, PhysicalDeploymentStatus
    from src.packet_tracer_mcp.domain.enterprise.models.deployment import EnvironmentFingerprint
    from src.packet_tracer_mcp.domain.enterprise.models.voice_plan import (
        VoicePlan, EnableCallControl, VoicePhase, VoiceCapabilityDimension,
    )
    from src.packet_tracer_mcp.domain.enterprise.models.execution import (
        ApplicationExecutionJournal, ExecutionJournalEntry, OperationSemantics, MutationDisposition,
    )
    from tests.test_cp_scale_live_local_preflight import _service, _request

    preflight = _service().inspect(_request(target_stage="router0-branch"), run_identity="measurement", started_at=FIXED_TIME)
    journals = []
    def journal(name):
        value = ApplicationExecutionJournal(plan_id=name, entries=[ExecutionJournalEntry(
            ordinal=ordinal, action_id=operation, operation=OperationSemantics.SET_VALUE,
            disposition=MutationDisposition.NO_OP, message="OFFLINE_MEASUREMENT_ONLY")
            for ordinal, operation in enumerate(MEASUREMENT_PLAN.journal_operations, 1)])
        journals.append(value)
        return value
    completed = []
    for ordinal, stage in enumerate(preflight.target.build_stages[:count], 1):
        topology = TopologyPlan(id=f"net-{ordinal}", semantic_hash="physical")
        configuration = ConfigurationPlan(id=f"cfg-{ordinal}", source_topology_id=topology.id,
            source_topology_hash="physical", semantic_hash="configuration")
        control = ControlPlanePlan(id=f"ctl-{ordinal}", source_topology_id=topology.id, source_topology_hash="physical",
            source_configuration_id=configuration.id, source_configuration_hash="configuration", semantic_hash="control")
        # A controlled plan, not canonical composition or executable authority:
        # one declared Voice action permits one diagnostic under the real cap.
        voice = VoicePlan(id=f"voice-{ordinal}", source_topology_id=topology.id,
            source_topology_hash="physical", source_configuration_id=configuration.id,
            source_configuration_hash="configuration", actions=[EnableCallControl(
                id="measure-call-control", phase=VoicePhase.CALL_CONTROL, call_control_id="measure",
                host_device_id="measure", host_device_name="Measure", host_model="2811", site_id="measure",
                required_capability=VoiceCapabilityDimension.CALL_CONTROL_CONFIG,
                max_phones=1, max_extensions=1)])
        projection = CPScaleCanonicalStageProjection(stage, topology, configuration, control, {}, voice=voice)
        deployed = PhysicalDeploymentResult(topology_id=topology.id, physical_topology_hash="physical",
            deployment_id="measurement", environment_fingerprint=EnvironmentFingerprint(),
            status=PhysicalDeploymentStatus.PARTIAL, execution_journal=journal(f"phy-{ordinal}"))
        configured = ConfigurationApplicationResult(config_plan_id=configuration.id, config_semantic_hash="configuration",
            source_topology_hash="physical", status=ConfigurationApplicationStatus.PARTIAL,
            execution_journal=journal(configuration.id))
        controlled = ControlPlaneApplicationResult(control_plane_plan_id=control.id, control_plane_semantic_hash="control",
            source_topology_hash="physical", source_configuration_hash="configuration",
            status=ConfigurationApplicationStatus.PARTIAL, execution_journal=journal(control.id))
        required = tuple(CPScaleObservationRecord("network_state", stage, "offline-measurement", "observed",
            {"boundary": boundary, "rows": ["same", "same"]}) for boundary in MEASUREMENT_PLAN.required_reads)
        diagnostics = tuple(CPScaleDiagnosticRecord(stage, {"attempt": attempt, "records": ["same", "same"]})
            for attempt in MEASUREMENT_PLAN.diagnostic_attempts)
        result = CPScaleLiveStageResult(stage, "failed", projection, deployed, None, None, None,
            configured, False, (configured,), controlled, None, None, None, required, diagnostics,
            "measurement", "OFFLINE_MEASUREMENT_ONLY", CPScaleStageContinuity(previous_projection=projection,
                previous_configuration=configured),
            CPScaleStageReport(CPScaleMutationScope((), (), (), (), (), ()), None, None, (), None,
                None, "", None, None, None, None, ()))
        completed.append(CPScaleStageProgress(projection, result=result))
    archives = tuple(CPScaleEvidenceArchive(run_identity="measurement", phase=phase,
        path=Path(phase + ".json"), sha256="a" * 64) for phase in MEASUREMENT_PLAN.archive_phases)
    progress = CPScaleProgressState(stages=tuple(completed))
    terminal = CPScaleTerminalState(failure="OFFLINE_MEASUREMENT_ONLY", archives=archives)
    report = publication_snapshot(preflight, "measurement", FIXED_TIME, "9.0.1.0858",
        CPScaleQualificationState(), progress, terminal)
    return report, progress, tuple(journals)


def _unique_objects(value):
    """Follow typed value edges once; an alias is not a copied journal/history."""
    from pydantic import BaseModel
    seen = set()
    def visit(item):
        if id(item) in seen:
            return
        seen.add(id(item))
        yield item
        if is_dataclass(item):
            children = (getattr(item, field.name) for field in fields(item))
        elif isinstance(item, BaseModel):
            children = (getattr(item, name) for name in type(item).model_fields)
        elif isinstance(item, dict):
            children = item.values()
        elif isinstance(item, (tuple, list, frozenset)):
            children = item
        else:
            children = ()
        for child in children:
            yield from visit(child)
    return tuple(visit(value))


def _json_bytes(report):
    from src.packet_tracer_mcp.infrastructure.persistence.cp_scale_run_evidence import run_evidence
    return (json.dumps(run_evidence(report), ensure_ascii=False, indent=2) + "\n").encode("utf-8")


@pytest.mark.parametrize("count", [1, 2, 4])
def test_measured_bytes_are_the_exact_public_writer_bytes(tmp_path, count):
    from src.packet_tracer_mcp.infrastructure.persistence.cp_scale_live import CPScaleLivePersistence
    report, _, _ = _cp_snapshot(count)
    persistence = CPScaleLivePersistence(tmp_path)
    persistence.write_progress(report)
    assert _json_bytes(report) == persistence.evidence_path.read_bytes()


def _json_stage_count(payload):
    if isinstance(payload, dict):
        return int({"stage", "plan", "physical"} <= payload.keys()) + sum(_json_stage_count(value) for value in payload.values())
    return sum(_json_stage_count(value) for value in payload) if isinstance(payload, list) else 0


@pytest.mark.parametrize("count", [1, 2, 4])
def test_public_cp_snapshot_keeps_complete_journals_with_plan_bounded_linear_size(count):
    from dataclasses import FrozenInstanceError
    from src.packet_tracer_mcp.application.cp_scale_live.contracts import CPScaleLiveStageResult, CPScaleStageExecutionInput
    from src.packet_tracer_mcp.application.use_cases.compose_enterprise_reference import EnterpriseReferenceComposition
    from src.packet_tracer_mcp.application.cp_scale_live.run_contracts import CPScaleLiveFinalResult, CPScaleRunOutcome
    from src.packet_tracer_mcp.domain.enterprise.models.execution import ApplicationExecutionJournal

    report, progress, journals = _cp_snapshot(count)
    with pytest.raises(FrozenInstanceError):
        progress.stages = ()
    with pytest.raises(FrozenInstanceError):
        report.stages = ()
    final = CPScaleLiveFinalResult.from_report(CPScaleRunOutcome.FAILED, report)
    assert len(report.stages) == len(final.progress.completed_stages) == count
    assert count <= len(report.preflight.target.build_stages)
    assert report.stages is progress.stages
    assert len(report.archives) == len(MEASUREMENT_PLAN.archive_phases) == report.archive_phase_limit
    assert tuple(item.phase for item in report.archives) == MEASUREMENT_PLAN.archive_phases
    assert len(report.preflight.issues) <= len(MEASUREMENT_PLAN.preflight_checks)
    objects = _unique_objects(report)
    assert sum(isinstance(item, CPScaleLiveStageResult) for item in objects) == count
    actual_journals = tuple(item for item in objects if isinstance(item, ApplicationExecutionJournal))
    assert len(actual_journals) == 3 * count
    assert all(any(actual is original for actual in actual_journals) for original in journals)
    for index, stage in enumerate(report.stages):
        result = stage.result
        assert final.progress.completed_stages[index] is result
        assert len(result.required_observations) == len(MEASUREMENT_PLAN.required_reads)
        assert len(result.diagnostics) == len(MEASUREMENT_PLAN.diagnostic_attempts)
        limits = CPScaleStageExecutionInput(result.projection, EnterpriseReferenceComposition(),
            result.deployment, None, result.deployment.environment_fingerprint, report.packet_tracer_version)
        assert len(result.configuration_attempts) <= limits.configuration_attempt_limit
        assert len(result.required_observations) <= limits.required_observation_limit
        assert len(result.diagnostics) <= limits.diagnostic_attempt_limit
        assert len(result.secondary_failures) <= limits.secondary_failure_limit
        assert all(item.authority == "DIAGNOSTIC_ONLY" for item in result.diagnostics)
        assert not any(isinstance(item, CPScaleLiveStageResult) for item in _unique_objects(result.continuity))
    for journal in actual_journals:
        assert tuple(item.action_id for item in journal.entries) == MEASUREMENT_PLAN.journal_operations
        assert tuple(item.ordinal for item in journal.entries) == (1, 2, 3)
    encoded = _json_bytes(report)
    assert encoded == _json_bytes(_cp_snapshot(count)[0])
    assert len(encoded) <= MEASUREMENT_PLAN.envelope_bytes + count * MEASUREMENT_PLAN.bytes_per_stage
    payload = json.loads(encoded)
    assert _json_stage_count(payload) == count
    for item in payload["stages"]:
        serialized_journals = (item["physical"]["execution_journal"],
            item["configuration_attempts"][0]["execution_journal"], item["control_plane"]["execution_journal"])
        assert all([entry["action_id"] for entry in journal["entries"]] == ["first", "second", "first"]
                   for journal in serialized_journals)
        assert len(item["network_state_timeline"]) == len(MEASUREMENT_PLAN.required_reads)
        assert item["post_failure_simulation"]["records"] == ["same", "same"]
    print(json.dumps({"stages": count, "results": count, "journals": len(actual_journals),
        "journal_entries": sum(len(item.entries) for item in actual_journals),
        "required_observations": count * len(MEASUREMENT_PLAN.required_reads),
        "diagnostics": count * len(MEASUREMENT_PLAN.diagnostic_attempts), "archives": len(report.archives),
        "issues": len(report.preflight.issues), "utf8_bytes": len(encoded)}, sort_keys=True))


def test_public_size_is_fixed_envelope_plus_one_bounded_entry_per_stage():
    envelopes = []
    for count in (1, 2, 4):
        report, _, _ = _cp_snapshot(count)
        encoded = _json_bytes(report)
        envelope = _json_bytes(replace(report, stages=()))
        envelopes.append(envelope)
        entries = json.loads(encoded)["stages"]
        sizes = [len("\n".join("    " + line for line in json.dumps(item, ensure_ascii=False, indent=2).splitlines()).encode("utf-8"))
                 for item in entries]
        assert len(entries) == count
        assert len(envelope) <= MEASUREMENT_PLAN.envelope_bytes
        assert all(size <= MEASUREMENT_PLAN.bytes_per_stage for size in sizes)
        assert len(encoded) == len(envelope) + sum(sizes) + 4 + 2 * (count - 1)
    assert envelopes[0] == envelopes[1] == envelopes[2]
