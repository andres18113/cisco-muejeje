"""Atomic CP-LIVE persistence, rooted explicitly by the composition adapter."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from ...application.use_cases.qualify_cp_scale_live import archive_cp_scale_canonical_evidence
from ...application.cp_scale_live.run_contracts import CPScaleRunReport, CPScaleCleanupAttestation
from .cp_scale_run_evidence import run_evidence, attestation_evidence


class CPScaleLivePersistence:
    def __init__(self, governed_root: Path) -> None:
        self.root = governed_root.resolve()
        self.evidence_path = self.root / "data" / "cp-scale" / "live-canonical-progress.json"
        self.checkpoint_path = self.evidence_path.parent / "live-canonical-checkpoint.json"
        self.final_checkpoint_path = self.root / "docs" / "reference" / "cp-scale" / "live_canonical_checkpoint.json"
        self.archive_dir = self.final_checkpoint_path.parent / "canonical-live-evidence"

    def archive(self, phase: str, payload: object, *, run_identity: str):
        if isinstance(payload, CPScaleRunReport):
            payload = run_evidence(payload)
        elif isinstance(payload, CPScaleCleanupAttestation):
            payload = attestation_evidence(payload)
        return archive_cp_scale_canonical_evidence(
            payload, base_dir=self.archive_dir, run_identity=run_identity, phase=phase,
        )

    def write_progress(self, report: CPScaleRunReport) -> None:
        self.write_evidence(run_evidence(report))

    def checkpoint(self, stage: str, report: CPScaleRunReport, *, final: bool = False) -> None:
        self.write_checkpoint_summary(stage, run_evidence(report), destination=(
            self.final_checkpoint_path if final else self.checkpoint_path
        ))

    def write_evidence(self, evidence: dict[str, object]) -> None:
        self.evidence_path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(evidence, ensure_ascii=False, indent=2) + "\n"
        temporary = self.evidence_path.with_suffix(".json.tmp")
        with temporary.open("w", encoding="utf-8", newline="\n") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, self.evidence_path)

    def write_checkpoint_summary(
        self,
        stage: str,
        evidence: dict[str, object],
        *,
        destination: Path | None = None,
    ) -> None:
        destination = destination if destination is not None else self.checkpoint_path
        stages = evidence.get("stages", [])
        latest = stages[-1] if isinstance(stages, list) and stages else {}
        if stage == "full-qualification":
            latest = evidence.get("full_qualification", latest)
        if not isinstance(latest, dict):
            latest = {}
        plan = latest.get("plan", {})
        physical = latest.get("physical", {})
        raw_digest = hashlib.sha256(self.evidence_path.read_bytes()).hexdigest()
        summary = {
            "schema": "cp-scale-live-checkpoint-v1",
            "checkpoint": stage,
            "checkpoint_at": evidence.get("checkpoint_at", ""),
            "packet_tracer_version": evidence.get("packet_tracer_version", ""),
            "live_devices": evidence.get("live_devices", 0),
            "live_links": evidence.get("live_links", 0),
            "physical_topology_hash": (
                plan.get("topology_hash", "")
                if isinstance(plan, dict) and plan.get("topology_hash")
                else physical.get("physical_topology_hash", "")
                if isinstance(physical, dict) else ""
            ),
            "configuration_status": (
                latest.get("configuration", {}).get("status", "")
                if isinstance(latest.get("configuration"), dict) else ""
            ),
            "control_plane_status": (
                latest.get("control_plane", {}).get("status", "")
                if isinstance(latest.get("control_plane"), dict) else ""
            ),
            "verification_scope": latest.get("verification_scope", ""),
            "workspace_verified_twice": latest.get("workspace_verified_twice", False),
            "raw_evidence_sha256": raw_digest,
        }
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(".json.tmp")
        payload = json.dumps(summary, ensure_ascii=False, indent=2) + "\n"
        with temporary.open("w", encoding="utf-8", newline="\n") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
