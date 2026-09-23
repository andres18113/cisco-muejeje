"""Raw bridge answers join exactly to acceptance purpose and episode rows."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from packet_tracer_mcp.domain.enterprise.models.cold_http_acceptance import (
    AcceptanceBudget,
    ColdHttpAcceptanceEnvelope,
)
from packet_tracer_mcp.domain.enterprise.models.service_qualification import (
    OperationEntry,
)


def _envelope():
    return ColdHttpAcceptanceEnvelope(
        attempt_id="0f1e2d3c4b5a69788796a5b4c3d2e1f0",
        started_at=datetime(2026, 9, 23, tzinfo=UTC),
        budget=AcceptanceBudget(
            max_operations=7849,
            max_seconds=2792,
            reserve_operations=30,
            reserve_seconds=40,
            used_operations=1,
            entries=[
                OperationEntry(
                    seq=1,
                    phase="experiment",
                    call="send_and_wait",
                    purpose="readiness:group#2",
                )
            ],
        ),
    )


def test_original_answer_is_indexed_by_exact_ledger_purpose_and_episode(tmp_path: Path):
    """An independently inspectable index cites raw bytes without replacing them."""
    from packet_tracer_mcp.infrastructure.persistence.server_pt_raw_archive import (
        build_raw_answer_index,
    )

    path = tmp_path / "raw-acceptance.jsonl"
    original = "show interfaces trunk\nSwitch#"
    events = [
        {
            "event": "attempt",
            "sequence": 1,
            "phase": "acceptance",
            "at_utc": "2026-09-23T00:00:00Z",
            "request_js": "show interfaces trunk",
        },
        {
            "event": "answer",
            "sequence": 1,
            "phase": "acceptance",
            "at_utc": "2026-09-23T00:00:01Z",
            "raw_answer": original,
        },
    ]
    path.write_text(
        "".join(json.dumps(item) + "\n" for item in events), encoding="utf-8"
    )

    indexed = build_raw_answer_index(path, _envelope())

    assert indexed["entries"][0]["purpose"] == "readiness:group#2"
    assert indexed["entries"][0]["episode"] == 2
    assert (
        indexed["entries"][0]["raw_answer_sha256"]
        == hashlib.sha256(original.encode("utf-8")).hexdigest()
    )
    assert indexed["journal_sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()


def test_missing_raw_answer_cannot_be_called_complete(tmp_path: Path):
    """A ledger row without its original response is an archive failure."""
    from packet_tracer_mcp.infrastructure.persistence.server_pt_raw_archive import (
        build_raw_answer_index,
    )

    path = tmp_path / "raw-acceptance.jsonl"
    path.write_text(
        json.dumps({"event": "attempt", "sequence": 1, "request_js": "query"}) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="original answer"):
        build_raw_answer_index(path, _envelope())
