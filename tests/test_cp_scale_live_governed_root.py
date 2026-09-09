"""The CP-LIVE caller declares the governed tree independently of its package."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import site
import subprocess
import sys

from tests.cp_live_data_integrity import isolated_subprocess_environment
from tests.subprocess_harness import run_isolated_python, subprocess_failure


ROOT = Path(__file__).resolve().parents[1]


def _run(*command: str | Path, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(item) for item in command], cwd=cwd, check=True,
        capture_output=True, text=True,
    )


def _clone_current_source(destination: Path, head: str) -> None:
    _run("git", "clone", "--quiet", "--no-hardlinks", str(ROOT), str(destination), cwd=ROOT)
    _run("git", "checkout", "--quiet", "--detach", head, cwd=destination)
    # TDD must exercise the candidate working tree before it is committed while
    # both checkout identities remain pinned to the same captured Git SHA.
    shutil.copytree(
        ROOT / "src" / "packet_tracer_mcp",
        destination / "src" / "packet_tracer_mcp",
        dirs_exist_ok=True,
    )
    shutil.copy2(
        ROOT / "tools" / "cp_scale_canonical_live.py",
        destination / "tools" / "cp_scale_canonical_live.py",
    )


def _venv_python(root: Path) -> Path:
    return root / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def _build_checkout_environment(root: Path) -> Path:
    environment = root / ".venv"
    _run(sys.executable, "-m", "venv", "--without-pip", str(environment), cwd=root)
    python = _venv_python(root)
    completed = _run(
        python,
        "-c",
        "import site; print(site.getsitepackages()[0])",
        cwd=root,
    )
    target_site = Path(completed.stdout.strip())
    host_sites = [Path(item) for item in site.getsitepackages() if Path(item).is_dir()]
    (target_site / "00-checkout-source.pth").write_text(
        str(root / "src") + "\n",
        encoding="utf-8",
    )
    (target_site / "10-test-dependencies.pth").write_text(
        "".join(str(item) + "\n" for item in host_sites),
        encoding="utf-8",
    )
    return python


def _digest(path: Path) -> tuple[int, str] | None:
    if not path.exists():
        return None
    payload = path.read_bytes()
    return len(payload), hashlib.sha256(payload).hexdigest()


def test_missing_caller_root_rejects_before_assembly() -> None:
    source = r'''
import json
import os
os.environ.pop("PT_MCP_GOVERNED_ROOT", None)
import packet_tracer_mcp.adapters.cli.cp_scale_live as live
calls = []
def forbidden(*args, **kwargs):
    calls.append("assembly")
    raise RuntimeError("ASSEMBLY_MUST_NOT_RUN")
name = "build_coordinator" if hasattr(live, "build_coordinator") else "_build_coordinator"
setattr(live, name, forbidden)
try:
    code = live.run("9.0.1.0858", expected_head="a" * 40,
        retain_on_full_verification=False)
    escaped = ""
except Exception as exc:
    code = None
    escaped = f"{type(exc).__name__}: {exc}"
print(json.dumps({"code": code, "calls": calls, "escaped": escaped}))
'''
    completed = run_isolated_python(source, cwd=ROOT)

    assert completed.returncode == 0, subprocess_failure(completed)
    result = json.loads(completed.stdout.strip().splitlines()[-1])
    assert result == {"code": 2, "calls": [], "escaped": ""}


def test_real_entry_rejects_checkout_a_with_interpreter_and_package_b_before_wrong_tree_writes(
    tmp_path: Path,
) -> None:
    head = _run("git", "rev-parse", "HEAD", cwd=ROOT).stdout.strip()
    checkout_a = tmp_path / "checkout-a"
    checkout_b = tmp_path / "checkout-b"
    _clone_current_source(checkout_a, head)
    _clone_current_source(checkout_b, head)
    python_b = _build_checkout_environment(checkout_b)
    neutral = tmp_path / "neutral"
    machine_state = tmp_path / "machine-state"
    neutral.mkdir()
    machine_state.mkdir()

    assert _run("git", "rev-parse", "HEAD", cwd=checkout_a).stdout.strip() == head
    assert _run("git", "rev-parse", "HEAD", cwd=checkout_b).stdout.strip() == head
    imported = _run(
        python_b,
        "-c",
        "import pathlib, packet_tracer_mcp; print(pathlib.Path(packet_tracer_mcp.__file__).resolve())",
        cwd=neutral,
    ).stdout.strip()
    assert Path(imported).is_relative_to(checkout_b / "src" / "packet_tracer_mcp")

    protected_b = (
        checkout_b / "data" / "cp-scale" / "live-canonical-progress.json",
        checkout_b / "data" / "cp-scale" / "live-canonical-checkpoint.json",
        checkout_b / "docs" / "reference" / "cp-scale" / "live_canonical_checkpoint.json",
    )
    before_b = tuple(_digest(path) for path in protected_b)
    environment = isolated_subprocess_environment(
        machine_state,
        governed_root=checkout_a,
    )
    completed = subprocess.run(
        [
            str(python_b),
            str(checkout_a / "tools" / "cp_scale_canonical_live.py"),
            "--execute",
            "--packet-tracer-version", "9.0.1.0858",
            "--expected-head", head,
        ],
        cwd=neutral,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert completed.returncode == 2, completed.stderr or completed.stdout
    assert tuple(_digest(path) for path in protected_b) == before_b
    assert not (checkout_b / "data" / "capabilities").exists()
    expected_evidence = checkout_a / "data" / "cp-scale" / "live-canonical-progress.json"
    evidence = json.loads(expected_evidence.read_text(encoding="utf-8"))
    assert Path(evidence["package_file"]).is_relative_to(checkout_b / "src" / "packet_tracer_mcp")
    assert evidence["import_isolation"]["state"] in {"FOREIGN_INTERPRETER", "FOREIGN_TREE"}
    assert "http_bridge" not in evidence
    assert "capability_prequalification" not in evidence
    assert not (checkout_a / "data" / "capabilities").exists()
