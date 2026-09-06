"""Portability contract for synthetic governed PoE safety evidence."""

from __future__ import annotations

from pathlib import Path, PurePosixPath, PureWindowsPath

import pytest

from src.packet_tracer_mcp.domain.enterprise.models.discovery import (
    ActiveWorkspaceBindingEvidence,
    ActiveWorkspaceIdentityMethod,
    LivePathIdentitySemantics,
    LiveSessionSafetyEvidence,
)
from src.packet_tracer_mcp.domain.enterprise.rules import live_session_safety
from src.packet_tracer_mcp.domain.enterprise.rules.live_session_safety import (
    validate_live_session_positive_admission,
)
from tests.poe_session_safety import healthy_live_session_safety


def test_healthy_live_session_safety_uses_host_absolute_pts_identities() -> None:
    evidence = healthy_live_session_safety()

    canonical = Path(evidence.canonical_path or "")
    disposable = Path(evidence.disposable_path or "")

    assert canonical.is_absolute()
    assert disposable.is_absolute()
    assert canonical.suffix.casefold() == ".pts"
    assert disposable.suffix.casefold() == ".pts"
    assert canonical != disposable
    assert validate_live_session_positive_admission(evidence).is_valid


def _healthy_evidence(
    *,
    semantics: LivePathIdentitySemantics,
    canonical: str,
    disposable: str,
    active: str | None = None,
) -> LiveSessionSafetyEvidence:
    stable_sha256 = "a" * 64
    binding = None
    if active is not None:
        binding = ActiveWorkspaceBindingEvidence(
            method=ActiveWorkspaceIdentityMethod.SCRIPT_MODULE_SELF_COMMAND_LINE,
            pre_qualification_path=active,
            post_integrity_path=active,
            pre_qualification_instance_id="instance-1",
            post_integrity_instance_id="instance-1",
            pre_qualification_module_id="module-1",
            post_integrity_module_id="module-1",
            pre_qualification_module_name="Packet Tracer MCP",
            post_integrity_module_name="Packet Tracer MCP",
        )
    return LiveSessionSafetyEvidence(
        path_identity_semantics=semantics,
        canonical_path=canonical,
        canonical_pre_run_sha256=stable_sha256,
        canonical_observed_post_run_sha256=stable_sha256,
        canonical_verified_sha256=stable_sha256,
        disposable_path=disposable,
        disposable_pre_run_sha256=stable_sha256,
        disposable_post_run_sha256=stable_sha256,
        active_workspace_binding=binding,
        unexpected_canonical_modification=False,
        disposable_modified=False,
        runtime_healthy=True,
        crash_detected=False,
        integrity_verified=True,
        session_reusable=True,
        positive_claim_allowed=True,
    )


@pytest.mark.parametrize(
    ("evaluator", "evidence"),
    [
        (
            PurePosixPath,
            _healthy_evidence(
                semantics=LivePathIdentitySemantics.WINDOWS,
                canonical=r"C:\PacketTracer\V5.pts",
                disposable=r"C:\PacketTracer\sessions\run-1\packet-tracer-live.pts",
                active=r"C:\PacketTracer\sessions\run-1\packet-tracer-live.pts",
            ),
        ),
        (
            PureWindowsPath,
            _healthy_evidence(
                semantics=LivePathIdentitySemantics.POSIX,
                canonical="/opt/packet-tracer/V5.pts",
                disposable="/tmp/packet-tracer/run-1/packet-tracer-live.pts",
                active="/tmp/packet-tracer/run-1/packet-tracer-live.pts",
            ),
        ),
    ],
)
def test_persisted_path_admission_is_independent_of_evaluator_os(
    monkeypatch: pytest.MonkeyPatch,
    evaluator: type[PurePosixPath] | type[PureWindowsPath],
    evidence: LiveSessionSafetyEvidence,
) -> None:
    # On 820b7d6, replacing the host Path with the opposite evaluator semantics
    # changes the verdict. Persisted evidence must carry its own semantics.
    monkeypatch.setattr(live_session_safety, "Path", evaluator, raising=False)

    assert validate_live_session_positive_admission(evidence).is_valid


@pytest.mark.parametrize(
    ("semantics", "canonical", "disposable"),
    [
        (LivePathIdentitySemantics.WINDOWS, r"relative\V5.pts", r"C:\live\run.pts"),
        (LivePathIdentitySemantics.WINDOWS, r"C:relative\V5.pts", r"C:\live\run.pts"),
        (LivePathIdentitySemantics.WINDOWS, r"C:\bad?name\V5.pts", r"C:\live\run.pts"),
        (LivePathIdentitySemantics.WINDOWS, r"C:\bad:name\V5.pts", r"C:\live\run.pts"),
        (LivePathIdentitySemantics.POSIX, "relative/V5.pts", "/tmp/live/run.pts"),
        (LivePathIdentitySemantics.POSIX, "/opt/../V5.pts", "/tmp/live/run.pts"),
        (LivePathIdentitySemantics.POSIX, "/opt/V5.pts\x00", "/tmp/live/run.pts"),
    ],
)
def test_relative_or_malformed_persisted_paths_remain_rejected(
    semantics: LivePathIdentitySemantics,
    canonical: str,
    disposable: str,
) -> None:
    evidence = _healthy_evidence(
        semantics=semantics,
        canonical=canonical,
        disposable=disposable,
        active=disposable,
    )

    assert not validate_live_session_positive_admission(evidence).is_valid


@pytest.mark.parametrize(
    ("semantics", "identity"),
    [
        (LivePathIdentitySemantics.WINDOWS, r"C:\PacketTracer\V5.pts"),
        (LivePathIdentitySemantics.POSIX, "/opt/packet-tracer/V5.pts"),
    ],
)
def test_canonical_and_disposable_same_identity_remains_rejected(
    semantics: LivePathIdentitySemantics,
    identity: str,
) -> None:
    evidence = _healthy_evidence(
        semantics=semantics,
        canonical=identity,
        disposable=identity,
        active=identity,
    )

    assert not validate_live_session_positive_admission(evidence).is_valid


@pytest.mark.parametrize(
    "evidence",
    [
        _healthy_evidence(
            semantics=LivePathIdentitySemantics.WINDOWS,
            canonical=r"C:\PacketTracer\V5.pts",
            disposable=r"C:\PacketTracer\sessions\run-1\packet-tracer-live.pts",
            active=r"C:\PacketTracer\sessions\run-1\packet-tracer-live.pts",
        ),
        _healthy_evidence(
            semantics=LivePathIdentitySemantics.POSIX,
            canonical="/opt/packet-tracer/V5.pts",
            disposable="/tmp/packet-tracer/run-1/packet-tracer-live.pts",
            active="/tmp/packet-tracer/run-1/packet-tracer-live.pts",
        ),
    ],
)
def test_serialized_safety_admission_is_runner_independent(
    monkeypatch: pytest.MonkeyPatch,
    evidence: LiveSessionSafetyEvidence,
) -> None:
    serialized = evidence.model_dump_json()
    restored = LiveSessionSafetyEvidence.model_validate_json(serialized)
    verdicts: list[bool] = []
    for evaluator in (PureWindowsPath, PurePosixPath):
        monkeypatch.setattr(live_session_safety, "Path", evaluator, raising=False)
        verdicts.append(validate_live_session_positive_admission(restored).is_valid)

    assert verdicts == [True, True]


@pytest.mark.parametrize(
    "active",
    [
        r"C:\PacketTracer\V5.pts",
        r"C:\PacketTracer\sessions\other\packet-tracer-live.pts",
        None,
    ],
)
def test_positive_admission_requires_exact_disposable_workspace_binding(
    active: str | None,
) -> None:
    disposable = r"C:\PacketTracer\sessions\run-1\packet-tracer-live.pts"
    evidence = _healthy_evidence(
        semantics=LivePathIdentitySemantics.WINDOWS,
        canonical=r"C:\PacketTracer\V5.pts",
        disposable=disposable,
        active=active,
    )

    assert not validate_live_session_positive_admission(evidence).is_valid


def test_old_positive_snapshot_without_path_semantics_or_workspace_binding_fails_closed() -> None:
    stable_sha256 = "a" * 64
    historical = LiveSessionSafetyEvidence(
        canonical_path=r"C:\PacketTracer\V5.pts",
        canonical_pre_run_sha256=stable_sha256,
        canonical_observed_post_run_sha256=stable_sha256,
        canonical_verified_sha256=stable_sha256,
        disposable_path=r"C:\PacketTracer\sessions\run-1\packet-tracer-live.pts",
        disposable_pre_run_sha256=stable_sha256,
        disposable_post_run_sha256=stable_sha256,
        unexpected_canonical_modification=False,
        disposable_modified=False,
        runtime_healthy=True,
        crash_detected=False,
        integrity_verified=True,
        session_reusable=True,
        positive_claim_allowed=True,
    )

    assert not validate_live_session_positive_admission(historical).is_valid


def test_workspace_instance_discontinuity_fails_closed() -> None:
    evidence = _healthy_evidence(
        semantics=LivePathIdentitySemantics.WINDOWS,
        canonical=r"C:\PacketTracer\V5.pts",
        disposable=r"C:\PacketTracer\sessions\run-1\packet-tracer-live.pts",
        active=r"C:\PacketTracer\sessions\run-1\packet-tracer-live.pts",
    )
    assert evidence.active_workspace_binding is not None
    evidence.active_workspace_binding.post_integrity_instance_id = "instance-2"

    assert not validate_live_session_positive_admission(evidence).is_valid
