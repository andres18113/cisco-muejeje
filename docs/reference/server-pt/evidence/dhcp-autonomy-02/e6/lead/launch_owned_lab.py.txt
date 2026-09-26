"""One-use, bounded launch of the episode's disposable Packet Tracer lab."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from dataclasses import asdict
from pathlib import Path

import packet_tracer_mcp
from packet_tracer_mcp.infrastructure.execution.file_bridge import bridge_dir
from packet_tracer_mcp.infrastructure.execution.import_isolation_preflight import (
    ImportIsolationPreflight,
)
from packet_tracer_mcp.infrastructure.execution.server_pt_process_control import (
    PowerShellOwnedProcessControl,
)
from packet_tracer_mcp.infrastructure.persistence.campaign_coordination import (
    FileCampaignCoordinator,
)

ROOT = Path(
    r"C:\Users\Andres\Desktop\Universidad\Uce\Cuarto\Infra\Cisco-MCP-server-services-goal-foundations"
)
EVIDENCE = Path(__file__).resolve().parent
EXE = Path(r"C:\Program Files\Cisco Packet Tracer 9.0.1\bin\PacketTracer.exe")
ids = json.loads((EVIDENCE / "ids.json").read_text(encoding="utf-8"))
attempt = ids["Attempt"]
control = PowerShellOwnedProcessControl()
coordinator = FileCampaignCoordinator()


def save(name: str, value: object) -> None:
    with (EVIDENCE / name).open("x", encoding="utf-8") as stream:
        json.dump(value, stream, sort_keys=True, indent=2)
        stream.write("\n")


def git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=ROOT, check=True, capture_output=True, text=True, timeout=15
    ).stdout.strip()


def mailbox() -> list[str]:
    path = bridge_dir()
    if not path.exists():
        return []
    return sorted(
        entry.name
        for entry in path.iterdir()
        if entry.is_file() and entry.name != "alive.txt"
    )


def census() -> dict[str, object]:
    value = control.packet_tracer_processes()
    return {
        "error": value.error,
        "processes": [asdict(item) for item in value.processes],
        "mailbox_files": mailbox(),
    }


def require_empty(value: dict[str, object]) -> None:
    if value["error"] or value["processes"] or value["mailbox_files"]:
        raise RuntimeError("prelaunch_exclusivity_unestablished")


isolation = ImportIsolationPreflight(ROOT).ensure_isolated()
preflight = {
    "sys_executable": sys.executable,
    "package_file": packet_tracer_mcp.__file__,
    "legacy_loaded": "src.packet_tracer_mcp" in sys.modules,
    "pytest_loaded": "pytest" in sys.modules,
    "isolation_state": isolation.state.value,
    "source_sha": git("rev-parse", "HEAD"),
    "source_tree": git("rev-parse", "HEAD^{tree}"),
    "source_status": git("status", "--porcelain=v1"),
    "before_claim": census(),
}
save("01-prelaunch.json", preflight)
if (
    not isolation.isolated
    or preflight["source_sha"] != ids["Head"]
    or preflight["source_tree"] != ids["Tree"]
    or preflight["source_status"]
    or not EXE.is_file()
):
    raise RuntimeError("prelaunch_source_or_import_identity_unestablished")
require_empty(preflight["before_claim"])

claim = coordinator.claim_lifecycle(attempt_id=attempt)
try:
    checked = census()
    save("02-exclusive-census.json", {**checked, "claim": claim.compact_summary()})
    require_empty(checked)
    if coordinator.verify(claim):
        raise RuntimeError("prelaunch_claim_lost")

    command = (
        "$p = Start-Process -FilePath '"
        + str(EXE).replace("'", "''")
        + "' -PassThru; $p.Id"
    )
    launched = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    pid = int(launched.stdout.strip().splitlines()[-1])
    save(
        "03-start-process.json",
        {"pid": pid, "stdout": launched.stdout, "stderr": launched.stderr},
    )

    observed = None
    deadline = time.monotonic() + 40
    while time.monotonic() < deadline:
        candidate = control.observe(pid)
        if (
            not candidate.error
            and candidate.present
            and candidate.process_path == str(EXE)
            and candidate.process_incarnation
            and candidate.command_line
            and candidate.main_window_title
        ):
            observed = candidate
            break
        time.sleep(1)
    if observed is None or coordinator.verify(claim):
        raise RuntimeError("launch_process_identity_unestablished")
    capture = {
        "pid": pid,
        "process_path": observed.process_path,
        "process_incarnation": observed.process_incarnation,
        "command_line": observed.command_line,
        "main_window_title": observed.main_window_title,
        "created_by_campaign": True,
        "workspace_kind": "disposable_declared",
        "launch_method": "Start-Process",
    }
    save("04-launch-capture.json", capture)
    env = dict(os.environ)
    env["PT_MCP_GOVERNED_ROOT"] = str(ROOT)
    record = subprocess.run(
        [
            sys.executable,
            "-m",
            "packet_tracer_mcp.adapters.cli.server_pt_commissioning",
            "--record-launch",
            "--campaign",
            "dhcp-autonomy",
            "--attempt",
            attempt,
            "--charter",
            str(ROOT / "docs/reference/server-pt/assignments/ServerPT_DHCP_Delegated_Autonomy_Mandate.md"),
            "--launch-evidence",
            str(EVIDENCE / "04-launch-capture.json"),
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=90,
    )
    save(
        "05-record-launch.json",
        {
            "exit_code": record.returncode,
            "stdout": record.stdout,
            "stderr": record.stderr,
        },
    )
    if record.returncode != 0:
        raise RuntimeError("campaign_launch_record_refused")
finally:
    save(
        "06-launch-claim-release.json",
        {"claim": claim.compact_summary(), "findings": list(coordinator.release(claim))},
    )
