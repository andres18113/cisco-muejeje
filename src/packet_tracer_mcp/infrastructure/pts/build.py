"""Validate and identify Muejeje build inputs without building a module.

This module is the facade: it orchestrates the audit and owns no rules of its
own. The rules live where they belong —

``build_state``
    the five-state model, its precedence, and blocker accumulation.
``manifest``
    the schema-2 document and its declarative fields.
``inventory``
    which paths may be declared, and what those files are.
``references``
    the untracked, ignored, hash-pinned material we do not own.
``provenance``
    Git identity, file hashes and recipe identity.

The public API is unchanged: `inspect_build`, `recipe_id`, `artifact_sha256`,
`classify_build_state` and the five state names are re-exported here, because
callers and tests address them through `build` (MJ-018).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import inventory, manifest as manifest_schema, references
from .build_state import (
    BUILD_AUTOMATION_UNPROVEN,
    BUILD_INPUT_INVALID,
    BUILD_SOURCE_INVALID,
    BUILD_STATES,
    BUILD_TOOLCHAIN_BLOCKED,
    PACKAGING_MANUAL_AVAILABLE,
    PACKAGING_MANUAL_UNAVAILABLE,
    Findings,
    base_report,
    classify_build_state,
    packaging_state,
)
from .provenance import (
    SourceIdentity,
    artifact_sha256,
    hash_file,
    inspect_source,
    recipe_id,
    working_blob_matches_head,
)

__all__ = [
    "BUILD_AUTOMATION_UNPROVEN",
    "BUILD_INPUT_INVALID",
    "BUILD_SOURCE_INVALID",
    "BUILD_STATES",
    "BUILD_TOOLCHAIN_BLOCKED",
    "PACKAGING_MANUAL_AVAILABLE",
    "PACKAGING_MANUAL_UNAVAILABLE",
    "artifact_sha256",
    "classify_build_state",
    "inspect_build",
    "recipe_id",
]


def inspect_build(
    root: Path,
    manifest_path: Path,
    *,
    builder_path: Path | None = None,
) -> dict[str, Any]:
    """Inspect a Git checkout and aggregate all available build blockers."""
    root = Path(root).resolve()
    findings = Findings()
    report = _empty_report(findings)
    manifest = _read_manifest(root, manifest_path, findings)
    if manifest is None:
        return report

    findings.extend(manifest_schema.check_declared_identity(root, manifest))
    source, git_failed = _identify_source(root, findings, report)
    _check_manifest_identity(root, source.tracked, findings, report)
    _collect_inputs(root, manifest, source.tracked, findings, report)
    report["builder"] = inventory.check_builder(
        manifest, builder_path, findings=findings,
    )
    declared = _check_declared_fields(manifest, findings)
    inventory.check_declared_orders(declared.options, findings=findings)

    _finalise(report, findings, git_failed=git_failed, declared=declared)
    _attach_recipe(
        root, manifest_path, report, findings,
        manifest=manifest, declared=declared,
    )
    return report


def _empty_report(findings: Findings) -> dict[str, Any]:
    return base_report(
        BUILD_INPUT_INVALID,
        findings.blockers,
        unresolved_build_options=list(manifest_schema.EXPECTED_OPTIONS),
        unresolved_automation_prerequisites=list(
            manifest_schema.AUTOMATION_PREREQUISITES
        ),
    )


def _read_manifest(
    root: Path, manifest_path: Path, findings: Findings,
) -> dict[str, Any] | None:
    """Read and shape-check the manifest. `None` means the audit ends here."""
    try:
        manifest = manifest_schema.read_manifest(root, manifest_path)
    except (OSError, UnicodeError, ValueError) as exc:
        findings.block(f"invalid manifest: {exc}")
        return None
    fatal = manifest_schema.schema_blocker(manifest)
    if fatal is not None:
        findings.block(fatal)
        return None
    return manifest


@dataclass(frozen=True)
class _DeclaredFields:
    """The manifest's declarative fields, and what is still unresolved in them."""

    options: dict[str, Any]
    packaging: Any
    unresolved_options: list[str]
    unresolved_automation: list[str]

    @property
    def recipe_complete(self) -> bool:
        return not self.unresolved_options


def _check_declared_fields(
    manifest: dict[str, Any], findings: Findings,
) -> _DeclaredFields:
    options, unresolved_options, option_blockers = (
        manifest_schema.check_build_options(manifest)
    )
    findings.extend(option_blockers)
    packaging, unresolved_automation, packaging_blockers = (
        manifest_schema.check_packaging(manifest)
    )
    findings.extend(packaging_blockers)
    return _DeclaredFields(
        options=options, packaging=packaging,
        unresolved_options=unresolved_options,
        unresolved_automation=unresolved_automation,
    )


def _identify_source(
    root: Path, findings: Findings, report: dict[str, Any],
) -> tuple[SourceIdentity, bool]:
    """Identify the checkout, or record that Git could not."""
    try:
        source = inspect_source(root)
    except ValueError as exc:
        findings.block(str(exc))
        return SourceIdentity(commit="", tree="", clean=False), True
    report["source"] = source.as_report()
    if not source.clean:
        findings.block("dirty tracked source")
    return source, False


def _check_manifest_identity(
    root: Path,
    tracked: frozenset[str],
    findings: Findings,
    report: dict[str, Any],
) -> None:
    """The manifest must be tracked, and its bytes must be the ones at HEAD."""
    logical = manifest_schema.MANIFEST_LOGICAL
    if logical not in tracked:
        findings.block("manifest must be tracked")
        return
    try:
        if not working_blob_matches_head(root, logical):
            findings.block("manifest bytes differ from HEAD")
            report["source"]["clean"] = False
    except ValueError as exc:
        findings.block(f"invalid manifest Git identity: {exc}")


def _collect_inputs(
    root: Path,
    manifest: dict[str, Any],
    tracked: frozenset[str],
    findings: Findings,
    report: dict[str, Any],
) -> None:
    """Measure the three input categories and the completeness of the owned root."""
    artifact = inventory.measure_declared_inputs(
        root, manifest, section="artifact_inputs", label="artifact",
        expected=inventory.EXPECTED_ARTIFACT_INPUTS, tracked=tracked,
        findings=findings,
    )
    tooling = inventory.measure_declared_inputs(
        root, manifest, section="tooling_inputs", label="tooling",
        expected=inventory.EXPECTED_TOOLING_INPUTS, tracked=tracked,
        findings=findings,
    )
    report["inputs"]["artifact"] = artifact.evidence
    report["inputs"]["tooling"] = tooling.evidence
    if artifact.dirty or tooling.dirty:
        report["source"]["clean"] = False

    # A path cannot both ship inside the artifact and decide how it was audited.
    for logical in sorted(artifact.paths & tooling.paths):
        findings.block(
            f"invalid input {logical}: a path may not be both artifact content "
            "and tooling"
        )
    for logical in inventory.sweep_owned_sources(tracked):
        findings.block(
            f"tracked owned source omitted from artifact_inputs: {logical}"
        )
    report["inputs"]["reference"] = references.measure_reference_inputs(
        root, manifest, tracked=tracked, findings=findings,
    )


def _finalise(
    report: dict[str, Any],
    findings: Findings,
    *,
    git_failed: bool,
    declared: _DeclaredFields,
) -> None:
    report["status"] = classify_build_state(
        source_unidentifiable=git_failed,
        input_invalid=findings.input_invalid,
        source_dirty=findings.source_dirty,
        toolchain_unusable=findings.toolchain_unusable,
        recipe_complete=declared.recipe_complete,
    )
    blocked = (
        git_failed
        or findings.input_invalid
        or findings.source_dirty
        or findings.toolchain_unusable
    )
    report["packaging_state"] = packaging_state(
        manual=(
            PACKAGING_MANUAL_UNAVAILABLE if blocked else PACKAGING_MANUAL_AVAILABLE
        ),
        manual_blockers=findings.manual_blockers,
        recipe_complete=declared.recipe_complete,
        unresolved_build_options=declared.unresolved_options,
        unresolved_automation_prerequisites=declared.unresolved_automation,
    )


def _attach_recipe(
    root: Path,
    manifest_path: Path,
    report: dict[str, Any],
    findings: Findings,
    *,
    manifest: dict[str, Any],
    declared: _DeclaredFields,
) -> None:
    """Compose the recipe, and give it an id only when the inventory is complete."""
    manifest_hash = hash_file(
        Path(manifest_path).resolve(), max_bytes=manifest_schema.MAX_MANIFEST_BYTES,
    )
    report["recipe"] = {
        "source": {
            "commit": report["source"]["commit"], "tree": report["source"]["tree"],
        },
        "manifest": {"sha256": manifest_hash},
        "extension": manifest.get("extension"),
        "output": manifest.get("output"),
        "artifact_inputs": report["inputs"]["artifact"],
        "tooling_inputs": report["inputs"]["tooling"],
        "reference_inputs": report["inputs"]["reference"],
        "builder": report["builder"],
        "build_options": declared.options,
        "packaging": declared.packaging,
    }
    # A complete input inventory earns a recipe id; an incomplete one never
    # does. The artifact hash stays external and is never derived from here.
    if report["status"] != PACKAGING_MANUAL_AVAILABLE:
        return
    try:
        report["build_recipe_id"] = recipe_id(report["recipe"])
    except (TypeError, ValueError) as exc:
        findings.block(f"invalid recipe for identity: {exc}")
        report["status"] = BUILD_INPUT_INVALID
        report["packaging_state"]["manual"] = PACKAGING_MANUAL_UNAVAILABLE
