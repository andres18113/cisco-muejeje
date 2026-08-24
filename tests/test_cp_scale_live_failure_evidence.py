"""A failed CP-SCALE stage must keep the evidence it already gathered.

The Floor-1 run died with a 43-identifier failure string and nothing else. The
per-field read-backs that would have named the root cause existed at the moment
of the raise -- `_execute_stage` had already written the full typed
`ConfigurationApplicationResult` into its local journal three lines earlier --
but the local dict escapes only through the success return, and the outer loop
appends it only after the call returns. An exception threw away the exact
evidence and kept the summary.

Diagnosing that cost a full offline reconstruction of what the run had already
seen. A stage that fails is exactly the stage whose evidence is worth keeping.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.packet_tracer_mcp.domain.enterprise.models.physical_deployment import (
    PhysicalDeploymentStatus,
)
from tools.cp_scale_canonical_live import CanonicalLiveFailure, _execute_stage


def _projection(stage: str = "floor1"):
    return SimpleNamespace(
        stage=SimpleNamespace(value=stage),
        topology=SimpleNamespace(
            physical_identity_hash="topology-hash",
            devices=[1, 2, 3],
            modules=[],
            links=[1, 2],
        ),
        configuration=SimpleNamespace(semantic_hash="config-hash", actions=[1]),
        control_plane=SimpleNamespace(
            semantic_hash="control-hash",
            actions=[],
            verification_expectations=[],
        ),
    )


def _unverified_deployment():
    return SimpleNamespace(
        status=PhysicalDeploymentStatus.FAILED,
        manifest=None,
        errors=["exact physical binding was refused"],
        model_dump=lambda mode="json": {"status": "failed"},
    )


def test_canonical_live_failure_carries_the_stage_evidence_it_had():
    failure = CanonicalLiveFailure("boom", stage_evidence={"stage": "floor1"})

    assert failure.stage_evidence == {"stage": "floor1"}
    assert str(failure) == "boom"


def test_canonical_live_failure_without_evidence_still_behaves_as_before():
    failure = CanonicalLiveFailure("boom")

    assert failure.stage_evidence is None
    assert isinstance(failure, RuntimeError)


def test_a_failed_stage_raises_with_the_journal_it_had_already_written():
    with pytest.raises(CanonicalLiveFailure) as caught:
        _execute_stage(
            _projection(),
            composition=SimpleNamespace(capabilities={}),
            deployment=_unverified_deployment(),
            delta_deployment=None,
            physical=None,
            configuration_runtime=None,
            control_runtime=None,
            transport=None,
            fingerprint=None,
            packet_tracer_version="9.0.1.0858",
        )

    evidence = caught.value.stage_evidence
    assert evidence is not None, "the stage journal was thrown away again"
    assert evidence["stage"] == "floor1"
    assert evidence["plan"]["configuration_hash"] == "config-hash"
    assert evidence["physical"] == {"status": "failed"}
