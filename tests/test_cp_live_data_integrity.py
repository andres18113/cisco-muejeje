"""Test-state isolation is proved independently from Git's tracked status."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from tests.cp_live_data_integrity import (
    ISOLATED_TEST_TOKEN,
    assert_protected_paths_unchanged,
    capture_protected_paths,
    isolated_subprocess_environment,
)
from tests.subprocess_harness import run_isolated_python, subprocess_failure


ROOT = Path(__file__).resolve().parents[1]


def test_pytest_session_uses_isolated_machine_state() -> None:
    isolated = Path(os.environ["PT_MCP_TEST_STATE_ROOT"])
    assert os.environ["PT_MCP_BRIDGE_TOKEN"] == ISOLATED_TEST_TOKEN
    for name in ("LOCALAPPDATA", "APPDATA", "XDG_STATE_HOME", "TEMP", "TMP", "TMPDIR"):
        # Windows runners may spell the same parent once with an 8.3 alias
        # (RUNNER~1) and once with its long name (runneradmin).  This assertion
        # is about filesystem identity, not lexical path spelling.
        assert os.path.samefile(Path(os.environ[name]).parent, isolated)


@pytest.mark.parametrize("change", ["create", "replace", "rewrite_same_bytes", "delete"])
def test_protected_snapshot_detects_ignored_file_changes(tmp_path: Path, change: str) -> None:
    protected = tmp_path / "data" / "cp-scale"
    evidence = protected / "live-canonical-progress.json"
    if change != "create":
        evidence.parent.mkdir(parents=True)
        evidence.write_bytes(b"ORIGINAL_SYNTHETIC_BYTES")
    before = capture_protected_paths((protected,))
    if change == "create":
        evidence.parent.mkdir(parents=True)
        evidence.write_bytes(b"CREATED")
    elif change == "replace":
        evidence.write_bytes(b"REPLACED_WITH_SAME_GIT_STATUS")
    elif change == "rewrite_same_bytes":
        original = evidence.read_bytes()
        previous = evidence.stat().st_mtime_ns
        evidence.write_bytes(original)
        os.utime(evidence, ns=(previous + 2_000_000_000, previous + 2_000_000_000))
    else:
        evidence.unlink()

    with pytest.raises(AssertionError, match="live-canonical-progress.json"):
        assert_protected_paths_unchanged(before)


def test_isolation_and_sentinel_start_before_test_module_collection(tmp_path: Path) -> None:
    protected = tmp_path / "ignored-progress.json"
    protected.write_bytes(b"ORIGINAL")
    observed = tmp_path / "collection-environment.txt"
    probe = tmp_path / "test_collection_probe.py"
    probe.write_text(
        "import os\n"
        "from pathlib import Path\n"
        f"Path({str(observed)!r}).write_text(os.environ.get('PT_MCP_TEST_STATE_ROOT', 'MISSING'), encoding='utf-8')\n"
        f"Path({str(protected)!r}).write_bytes(b'COLLECTION_CONTAMINATION')\n"
        "def test_collected():\n    assert True\n",
        encoding="utf-8",
    )
    environment = isolated_subprocess_environment(tmp_path / "child")
    environment["PT_MCP_TEST_EXTRA_PROTECTED_PATH"] = str(protected)
    inherited_state_root = environment.get("PT_MCP_TEST_STATE_ROOT")

    completed = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "tests.conftest", str(probe)],
        cwd=ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert observed.exists(), subprocess_failure(completed)
    observed_state_root = observed.read_text(encoding="utf-8")
    assert observed_state_root != "MISSING"
    assert observed_state_root != inherited_state_root
    assert completed.returncode != 0
    assert "Protected paths changed" in completed.stdout + completed.stderr


def test_protected_snapshot_detects_symlink_retargeting(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    link = tmp_path / "protected-link"
    first.write_bytes(b"SAME")
    second.write_bytes(b"SAME")
    try:
        link.symlink_to(first)
    except OSError as exc:
        pytest.skip(f"Symlinks are unavailable for this test account: {exc}")
    before = capture_protected_paths((link,))
    link.unlink()
    link.symlink_to(second)

    with pytest.raises(AssertionError, match="protected-link"):
        assert_protected_paths_unchanged(before)


def test_isolated_environment_replaces_every_machine_state_surface(tmp_path: Path) -> None:
    inherited = {
        "PYTHONPATH": "FOREIGN_PATH",
        "PYTHONHOME": "FOREIGN_HOME",
        "PYTHONSTARTUP": "FOREIGN_STARTUP",
        "LOCALAPPDATA": "HOST_LOCAL",
        "APPDATA": "HOST_ROAMING",
        "XDG_STATE_HOME": "HOST_XDG",
        "TEMP": "HOST_TEMP",
        "TMP": "HOST_TMP",
        "TMPDIR": "HOST_TMPDIR",
        "PT_MCP_BRIDGE_TOKEN": "HOST_TOKEN_MUST_NOT_CROSS",
        "PT_MCP_GOVERNED_ROOT": "HOST_ROOT_MUST_NOT_CROSS",
    }

    environment = isolated_subprocess_environment(
        tmp_path,
        governed_root=ROOT,
        inherited=inherited,
    )

    assert all(name not in environment for name in ("PYTHONPATH", "PYTHONHOME", "PYTHONSTARTUP"))
    assert environment["PT_MCP_GOVERNED_ROOT"] == str(ROOT.resolve())
    assert environment["PT_MCP_BRIDGE_TOKEN"] != inherited["PT_MCP_BRIDGE_TOKEN"]
    for name in ("LOCALAPPDATA", "APPDATA", "XDG_STATE_HOME", "TEMP", "TMP", "TMPDIR"):
        assert Path(environment[name]).is_relative_to(tmp_path)


def test_python_harness_child_observes_only_isolated_machine_state() -> None:
    source = r'''
import json, os
print(json.dumps({name: os.environ.get(name) for name in (
    "LOCALAPPDATA", "APPDATA", "XDG_STATE_HOME", "TEMP", "TMP", "TMPDIR",
    "PT_MCP_BRIDGE_TOKEN", "PT_MCP_GOVERNED_ROOT", "PYTHONPATH",
)}))
'''
    completed = run_isolated_python(source, cwd=ROOT, governed_root=ROOT)

    assert completed.returncode == 0, subprocess_failure(completed)
    observed = json.loads(completed.stdout)
    assert observed["PT_MCP_GOVERNED_ROOT"] == str(ROOT.resolve())
    assert observed["PYTHONPATH"] is None
    assert observed["PT_MCP_BRIDGE_TOKEN"] == ISOLATED_TEST_TOKEN
    roots = {Path(observed[name]).parent for name in (
        "LOCALAPPDATA", "APPDATA", "XDG_STATE_HOME", "TEMP", "TMP", "TMPDIR",
    )}
    assert len(roots) == 1
