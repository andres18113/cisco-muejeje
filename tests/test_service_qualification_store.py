"""The qualification record store: containment, write-ahead order, immutability."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path

import pytest

from packet_tracer_mcp.application.ports.service_run_record import (
    RunRecordPersistenceError,
)
from packet_tracer_mcp.domain.enterprise.models.service_qualification import (
    BudgetRecord,
    ExecutionMode,
    QualificationRecord,
    QualificationStage,
)
from packet_tracer_mcp.infrastructure.persistence import (
    service_qualification_store as store_module,
)
from packet_tracer_mcp.infrastructure.persistence.service_qualification_store import (
    QualificationRecordStore,
)


def _record(run_id: str = "2026-09-18T10-00-00Z-abcd1234") -> QualificationRecord:
    return QualificationRecord(
        run_id=run_id,
        stage=QualificationStage.Q0,
        execution_mode=ExecutionMode.OFFLINE_SIMULATION,
        created_at=datetime(2026, 9, 18, tzinfo=UTC),
        budget=BudgetRecord(
            max_operations=20,
            max_seconds=300,
            reserve_operations=5,
            reserve_seconds=60,
            planned_minimum_operations=19,
        ),
    )


def test_begin_is_create_only_and_advance_requires_a_begun_record(tmp_path):
    """A run never overwrites another run's record, and never skips `begin`."""
    store = QualificationRecordStore(tmp_path)
    record = _record()
    with pytest.raises(RunRecordPersistenceError):
        store.advance(record)
    path = Path(store.begin(record))
    assert path.parent == (tmp_path / "q0").resolve()
    assert path.name == f"q0-{record.run_id}.json"
    with pytest.raises(RunRecordPersistenceError):
        store.begin(record)
    record.persisted_step = "admitted"
    store.advance(record)
    assert store.load(path).persisted_step == "admitted"


def test_a_completed_record_is_immutable(tmp_path):
    """Historical evidence is never rewritten once terminal."""
    store = QualificationRecordStore(tmp_path)
    record = _record()
    store.begin(record)
    with pytest.raises(RunRecordPersistenceError):
        store.complete(record)
    record.completed_at = datetime(2026, 9, 18, 1, tzinfo=UTC)
    path = store.complete(record)
    record.persisted_step = "tampered"
    with pytest.raises(RunRecordPersistenceError):
        store.advance(record)
    with pytest.raises(RunRecordPersistenceError):
        store.complete(record)
    assert store.load(path).persisted_step == ""


def test_hostile_run_ids_stay_inside_the_store(tmp_path):
    """Sanitization first, then containment decides."""
    store = QualificationRecordStore(tmp_path / "records")
    path = Path(store.begin(_record(run_id="../../escape")))
    assert path.is_relative_to((tmp_path / "records").resolve())
    with pytest.raises(RunRecordPersistenceError):
        store.load(tmp_path / "outside.json")


def test_a_failed_replace_keeps_the_previous_record_and_is_typed(tmp_path, monkeypatch):
    """A failed atomic rewrite leaves the last durable record in place."""
    store = QualificationRecordStore(tmp_path)
    record = _record()
    path = store.begin(record)

    def refuse(*_args):
        raise OSError("disk full")

    monkeypatch.setattr(store_module.os, "replace", refuse)
    record.persisted_step = "admitted"
    with pytest.raises(RunRecordPersistenceError):
        store.advance(record)
    monkeypatch.setattr(store_module.os, "replace", os.replace)
    assert store.load(path).persisted_step == ""
    assert not list(tmp_path.rglob("*.tmp"))
