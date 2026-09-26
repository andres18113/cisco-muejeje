"""The exact raw Server-PT evidence archive is never modified to satisfy Ruff."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from scripts import quality_gate

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = Path("docs/reference/server-pt/evidence/dhcp-autonomy-02/e1")
SOURCES = (
    ARCHIVE / "lead/launch_owned_lab.py",
    ARCHIVE / "lead/run_qualification.py",
)


def test_exact_archive_is_exempt_and_other_python_stays_gated() -> None:
    """Only both hash-bound raw scripts leave the Ruff selection."""
    classify = getattr(quality_gate, "classify_immutable_evidence", None)
    assert classify is not None
    ordinary = ROOT / "src/packet_tracer_mcp/application/use_cases/apply_services.py"
    selected = [ROOT / path for path in SOURCES]
    selected.append(ordinary)
    gated, exempt = classify(selected, ROOT)
    assert gated == (ordinary,)
    assert exempt == SOURCES


@pytest.mark.parametrize("tamper", ["change", "extra"])
def test_changed_or_unindexed_archive_fails_closed(tmp_path: Path, tamper: str) -> None:
    """A matching filename cannot launder modified or unmanifested source."""
    classify = getattr(quality_gate, "classify_immutable_evidence", None)
    assert classify is not None
    copy = tmp_path / ARCHIVE
    shutil.copytree(ROOT / ARCHIVE, copy)
    if tamper == "change":
        with (copy / "lead/launch_owned_lab.py").open("ab") as stream:
            stream.write(b"# changed\n")
    else:
        (copy / "lead/unindexed.py").write_text("VALUE = 1\n", encoding="utf-8")
    with pytest.raises(quality_gate.QualityGateError, match="immutable evidence"):
        classify(tuple(tmp_path / path for path in SOURCES), tmp_path)


def test_symlink_alias_cannot_inherit_registered_evidence_exemption(
    tmp_path: Path,
) -> None:
    """Git names the selected path; a resolved alias has no archive authority."""
    copy = tmp_path / ARCHIVE
    shutil.copytree(ROOT / ARCHIVE, copy)
    alias = tmp_path / "alias.py"
    try:
        alias.symlink_to(copy / "lead/launch_owned_lab.py")
    except OSError as exc:
        pytest.skip(f"symlink creation unavailable: {exc}")
    with pytest.raises(quality_gate.QualityGateError, match=r"symlink|alias"):
        quality_gate._existing_python_files(tmp_path, {"alias.py"})
    with pytest.raises(quality_gate.QualityGateError, match=r"symlink|alias"):
        quality_gate.classify_immutable_evidence((alias,), tmp_path)


def test_resolved_alias_cannot_replace_the_selected_git_path(
    tmp_path: Path, monkeypatch
) -> None:
    """The alias refusal is testable even where Windows disallows symlinks."""
    copy = tmp_path / ARCHIVE
    shutil.copytree(ROOT / ARCHIVE, copy)
    alias = tmp_path / "alias.py"
    alias.write_text("VALUE = 1\n", encoding="utf-8")
    target = copy / "lead/launch_owned_lab.py"
    original_resolve = Path.resolve

    def redirect_alias(self, *args, **kwargs):
        if self == alias:
            return target
        return original_resolve(self, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", redirect_alias)
    with pytest.raises(quality_gate.QualityGateError, match=r"symlink|alias"):
        quality_gate._existing_python_files(tmp_path, {"alias.py"})
    with pytest.raises(quality_gate.QualityGateError, match=r"symlink|alias"):
        quality_gate.classify_immutable_evidence((alias,), tmp_path)


def test_unrelated_python_change_still_checks_existing_archive(tmp_path: Path) -> None:
    """A later change cannot hide drift in the committed raw evidence set."""
    copy = tmp_path / ARCHIVE
    shutil.copytree(ROOT / ARCHIVE, copy)
    ordinary = tmp_path / "ordinary.py"
    ordinary.write_text("VALUE = 1\n", encoding="utf-8")
    with (copy / "lead/launch_owned_lab.py").open("ab") as stream:
        stream.write(b"# drift\n")
    with pytest.raises(quality_gate.QualityGateError, match="immutable evidence"):
        quality_gate.classify_immutable_evidence((ordinary,), tmp_path)


def test_missing_tracked_archive_fails_on_unrelated_change(tmp_path: Path) -> None:
    """Removing the entire tracked evidence directory cannot disable its check."""
    copy = tmp_path / ARCHIVE
    shutil.copytree(ROOT / ARCHIVE, copy)
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "add", "--", (ARCHIVE / "MANIFEST.sha256").as_posix()],
        cwd=tmp_path,
        check=True,
    )
    assert copy.resolve().is_relative_to(tmp_path.resolve())
    shutil.rmtree(copy)
    ordinary = tmp_path / "ordinary.py"
    ordinary.write_text("VALUE = 1\n", encoding="utf-8")
    with pytest.raises(quality_gate.QualityGateError, match="immutable evidence"):
        quality_gate.classify_immutable_evidence((ordinary,), tmp_path)


def test_committed_archive_deletion_cannot_remove_its_registration(
    tmp_path: Path, monkeypatch
) -> None:
    """A clean commit deleting all evidence still fails the full gate."""
    copy = tmp_path / ARCHIVE
    shutil.copytree(ROOT / ARCHIVE, copy)
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "config", "user.email", "archive@example.invalid"],
        cwd=tmp_path,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Archive Test"], cwd=tmp_path, check=True
    )
    # Archive paths overflow MAX_PATH under a Windows temp root; Git for
    # Windows needs this setting even where the OS allows long paths.
    subprocess.run(
        ["git", "config", "core.longpaths", "true"], cwd=tmp_path, check=True
    )
    subprocess.run(["git", "add", "--", ARCHIVE.as_posix()], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "commit", "-qm", "archive baseline"], cwd=tmp_path, check=True
    )
    assert copy.resolve().is_relative_to(tmp_path.resolve())
    shutil.rmtree(copy)
    subprocess.run(["git", "add", "-u"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "delete archive"], cwd=tmp_path, check=True)
    ordinary = tmp_path / "ordinary.py"
    ordinary.write_text("VALUE = 1\n", encoding="utf-8")
    monkeypatch.setattr(quality_gate, "REPOSITORY_ROOT", tmp_path)
    with pytest.raises(quality_gate.QualityGateError, match="immutable evidence"):
        quality_gate.classify_immutable_evidence((ordinary,), tmp_path)


def test_internal_archive_directory_alias_is_refused(
    tmp_path: Path, monkeypatch
) -> None:
    """Byte-identical alternate files do not replace registered archive paths."""
    archive = tmp_path / ARCHIVE
    alternate = tmp_path / "alternate-archive"
    shutil.copytree(ROOT / ARCHIVE, archive)
    shutil.copytree(ROOT / ARCHIVE, alternate)
    original_resolve = Path.resolve

    def redirect_archive(self, *args, **kwargs):
        if self == archive:
            return alternate
        return original_resolve(self, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", redirect_archive)
    with pytest.raises(quality_gate.QualityGateError, match="immutable evidence"):
        quality_gate.classify_immutable_evidence(
            tuple(tmp_path / path for path in SOURCES), tmp_path
        )
