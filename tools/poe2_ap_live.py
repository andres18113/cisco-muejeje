"""One disposable, exact AP PoE experiment. No caller-supplied IOS or JS.

Requires a clean, pushed, exact-SHA 4/4 green source descendant of START_HEAD.
The authenticated HTTP listener is fresh and tested; IPC transport uses the
existing user-ACL file mailbox, explicitly recorded rather than claiming a
webview HTTP connection. No source writes occur inside the LIVE boundary.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
import os
from pathlib import Path
from secrets import token_hex, token_urlsafe
import subprocess
import sys
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import packet_tracer_mcp
from packet_tracer_mcp.domain.enterprise.models.poe2 import PoE2Capture, PoE2Evidence
from packet_tracer_mcp.infrastructure.execution.poe2_evidence import (
    BINDING, BUILD, START_HEAD, capture_delivery, completeness, validate_poe2_evidence,
)
from packet_tracer_mcp.domain.enterprise.scenarios.cp_scale_physical import (
    cp_scale_physical_design, MLS6,
)
from packet_tracer_mcp.domain.enterprise.services.poe_claims import _AUTHORIZED_OBSERVATION_METHODS
from packet_tracer_mcp.infrastructure.execution.configuration_runtime import PacketTracerConfigurationRuntime
from packet_tracer_mcp.infrastructure.execution.file_bridge import FileBridge
from packet_tracer_mcp.infrastructure.execution.import_isolation_preflight import ImportIsolationPreflight
from packet_tracer_mcp.infrastructure.execution.ios_terminal import ControlledIosExecutor
from packet_tracer_mcp.infrastructure.execution.live_bridge import PTCommandBridge
from packet_tracer_mcp.infrastructure.execution.poe_delivery_runtime import PacketTracerPoEDeliveryFixtureRuntime
from packet_tracer_mcp.infrastructure.execution.poe_inline_observer import GovernedPoEInlineObserver
from packet_tracer_mcp.shared.utils import safe_name_component, resolve_within
from poe_inline_calibration_live import _ENV_JS, _DEVICE_NAMES_JS, _payload, PoEInlineMode

ROOT = Path(__file__).resolve().parents[1]
CALIBRATION = "docs/reference/cp-scale/canonical-live-evidence/poe-inline-calibration-poe1-c5626851.json"
CALIBRATION_SHA = "f870b200d14e79c6a11bd656664f543fa5b91da9c41ab6310cf1ff3cd4584dd8"
REPO = "andres18113/cisco-muejeje"
BRANCH = "feature/runtime-ripv2"


def utc() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def command(*args: str) -> str:
    return subprocess.run(args, cwd=ROOT, check=True, capture_output=True,
                          text=True, timeout=60).stdout.strip()


def processes() -> list[dict]:
    script = "Get-CimInstance Win32_Process | Where-Object { $_.Name -match '^(python|pythonw|pytest|PacketTracer)\\.exe$' } | Select-Object ProcessId,ParentProcessId,Name,ExecutablePath,CommandLine | ConvertTo-Json -Compress"
    # Keep regex literal in PowerShell; no shell interpolation from evidence.
    raw = command("powershell.exe", "-NoProfile", "-Command", script)
    result = json.loads(raw) if raw else []
    return result if isinstance(result, list) else [result]


def prove_processes() -> list[dict]:
    result = processes()
    allowed = {os.getpid(), os.getppid()}
    foreign = [p for p in result if p["Name"].lower() != "packettracer.exe" and p["ProcessId"] not in allowed]
    if foreign:
        raise RuntimeError("Foreign Python/test process: " + json.dumps(foreign))
    if not any(p["Name"] == "PacketTracer.exe" for p in result):
        raise RuntimeError("Packet Tracer is absent")
    return result


def source_baseline() -> dict:
    if command("git", "branch", "--show-current") != BRANCH:
        raise RuntimeError("Wrong branch")
    if command("git", "status", "--porcelain"):
        raise RuntimeError("Worktree must be clean")
    sha = command("git", "rev-parse", "HEAD")
    command("git", "merge-base", "--is-ancestor", START_HEAD, sha)
    remote = json.loads(command("gh", "api", "repos/" + REPO + "/git/ref/heads/" + BRANCH))["object"]["sha"]
    if sha != remote:
        raise RuntimeError("Local and remote SHA differ")
    runs = json.loads(command("gh", "run", "list", "--repo", REPO, "--commit", sha,
                             "--json", "databaseId,name,headSha,status,conclusion,url"))
    run = next(r for r in runs if r["name"] == "tests" and r["headSha"] == sha)
    jobs = json.loads(command("gh", "api", "repos/" + REPO + "/actions/runs/" + str(run["databaseId"]) + "/jobs"))["jobs"]
    if len(jobs) != 4 or any(j["conclusion"] != "success" or j["head_sha"] != sha for j in jobs):
        raise RuntimeError("Exact SHA Actions is not 4/4 green")
    if _AUTHORIZED_OBSERVATION_METHODS != frozenset({"manual_visible_power_state"}):
        raise RuntimeError("Strict E5 baseline changed")
    calibration_path = resolve_within(ROOT, CALIBRATION)
    if hashlib.sha256(calibration_path.read_bytes()).hexdigest() != CALIBRATION_SHA:
        raise RuntimeError("Calibration hash mismatch")
    design = cp_scale_physical_design()
    device = next(d for s in design.sites for d in s.devices if d.id == MLS6)
    bindings = [b for s in design.sites for b in s.endpoint_bindings
                if b.device_id == MLS6 and b.endpoint_model == "AccessPoint-PT"]
    if len(bindings) != 1:
        raise RuntimeError("Exact AP binding became ambiguous")
    b = bindings[0]
    derived = dict(switch_model=device.model, switch_port=b.device_port,
                   endpoint_model=b.endpoint_model, endpoint_port=b.endpoint_port)
    if derived != BINDING:
        raise RuntimeError("Governed AP binding changed")
    return dict(verified_at_utc=utc(), local_head=sha, remote_head=remote,
                actions_run=run, jobs=[{k: j[k] for k in ("name", "conclusion", "head_sha", "html_url")} for j in jobs],
                strict_e5=True, derived_binding=b.model_dump(mode="json"),
                initial_START_HEAD_verified=True)


class Experiment:
    def __init__(self, run_id: str) -> None:
        self.bridge = FileBridge()
        self.fixture = PacketTracerPoEDeliveryFixtureRuntime(self.send, BUILD)
        self.executor = ControlledIosExecutor(self.send)
        self.observer = GovernedPoEInlineObserver(self.executor)
        self.config = PacketTracerConfigurationRuntime(self.bridge.send)
        self.switch = "MCP-POE2-SW-" + run_id
        self.endpoint = "MCP-POE2-AP-" + run_id
        self.transport_problems: list[str] = []

    def send(self, script: str, timeout: float = 12.0) -> str | None:
        result = self.bridge.send_and_wait(script, timeout)
        if result is None:
            self.transport_problems.append(self.bridge.last_disposition.value)
        return result

    def read(self, script: str) -> dict:
        raw = self.send(script, 15)
        if raw is None or raw.startswith(("ERROR:", "PT_ERROR:")):
            raise RuntimeError("Governed environment read failed: " + str(raw))
        return json.loads(raw)

    def names(self) -> frozenset[str]:
        return frozenset(self.read(_DEVICE_NAMES_JS)["devices"])

    def environment(self) -> dict:
        return self.read(_ENV_JS)

    def apply(self, mode: PoEInlineMode) -> None:
        if not self.config.configure_ios(self.switch, _payload(BINDING["switch_port"], mode)):
            raise RuntimeError("Mode was not queued")
        time.sleep(6)
        self.bridge.collect_completed()
        if self.bridge._pending:
            raise RuntimeError("Mode dispatch still pending")

    def capture(self, label: str) -> PoE2Capture:
        start = utc()
        # Same documented getter used by ControlledIosExecutor. Reads only the
        # exact fixture terminal; the expected prompt is measured, not guessed.
        first = self.observer.observe_poe_inline_status(self.switch, (BINDING["switch_port"],))
        state = self.executor._terminal_state(json.dumps(self.switch))
        prompt = str(state.get("prompt") or "").strip()
        time.sleep(2)
        second = self.observer.observe_poe_inline_status(self.switch, (BINDING["switch_port"],))
        serialize = lambda x: json.loads(json.dumps(asdict(x), default=lambda v: v.value if isinstance(v, Enum) else str(v)))
        a, b = serialize(first), serialize(second)
        stable = first.raw_output == second.raw_output
        return PoE2Capture(label=label, started_at_utc=start, completed_at_utc=utc(),
                           expected_prompt=prompt, observation=a, repeat_observation=b,
                           table_completeness=completeness(a, prompt, stable, self.switch),
                           stable=stable, raw_file=label.lower() + ".txt",
                           raw_sha256=hashlib.sha256(first.raw_output.encode()).hexdigest())


def authenticated_status(bridge: PTCommandBridge) -> dict:
    url = "http://127.0.0.1:54321/status"
    try:
        urlopen(url, timeout=3)
    except HTTPError as exc:
        unauth = exc.code
    else:
        raise RuntimeError("Unauthenticated bridge accepted request")
    with urlopen(Request(url, headers={"X-PT-Token": bridge.token}), timeout=3) as response:
        status = response.status
    if unauth != 401 or status != 200:
        raise RuntimeError("Authentication gate failed")
    return dict(pid=os.getpid(), token_fingerprint=bridge.token_id,
                authenticated_status=status, unauthenticated_status=unauth,
                active_pt_transport="file_bridge_user_acl", webview_http_connection_claimed=False)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if not args.execute:
        print("No LIVE without --execute")
        return 1
    isolation = ImportIsolationPreflight(ROOT).ensure_isolated()
    if not isolation.isolated:
        raise RuntimeError(isolation.render())
    baseline = source_baseline()
    baseline["processes"] = prove_processes()
    baseline["import_isolation"] = dict(result=isolation.render(), executable=sys.executable,
        production_file=packet_tracer_mcp.__file__, loaded_namespaces=[n for n in ("packet_tracer_mcp", "src.packet_tracer_mcp") if n in sys.modules])
    run_id = "poe2-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + token_hex(4)
    started = utc()
    exp = Experiment(run_id)
    if not exp.bridge.pt_alive():
        raise RuntimeError("File bridge heartbeat stale")
    if list(exp.bridge.dir.glob("req_*.js")) or list(exp.bridge.dir.glob("res_*.txt")):
        raise RuntimeError("Foreign mailbox residue")
    os.environ["PT_MCP_BRIDGE_TOKEN"] = token_urlsafe(32)
    http = PTCommandBridge(port=54321, token=os.environ["PT_MCP_BRIDGE_TOKEN"])
    http.start()  # bind must fail if any foreign listener won the port.
    captures, problems, fixture, restoration, safety = [], [], {}, {}, {}
    raw_files = {}
    opening, preexisting, env = None, None, None
    creation_started = False
    try:
        baseline["fresh_authenticated_bridge"] = authenticated_status(http)
        env = exp.environment()
        if env.get("pt_version") != BUILD or env.get("simulation_mode") is not False:
            raise RuntimeError("Wrong PT build or mode")
        if env.get("devices") != 0 or env.get("links") != 0 or env.get("saved_filename") != "":
            raise RuntimeError("Requires empty, untitled semantic baseline")
        baseline["environment"] = env
        opening = exp.fixture.inventory_fingerprint()
        preexisting = exp.names()
        baseline["inventory_fingerprint"] = opening
        baseline["devices"] = sorted(preexisting)
        prove_processes()
        print("LIVE OPEN " + run_id + " source=" + baseline["local_head"], flush=True)
        creation_started = True
        sw = exp.fixture.create_device(BINDING["switch_model"], exp.switch, (BINDING["switch_port"],), arm="candidate")
        ap = exp.fixture.create_device(BINDING["endpoint_model"], exp.endpoint, (BINDING["endpoint_port"],), arm="candidate")
        if sw.model != BINDING["switch_model"] or ap.model != BINDING["endpoint_model"]:
            raise RuntimeError("Fixture model readback mismatch")
        link = exp.fixture.create_link(sw, BINDING["switch_port"], ap, BINDING["endpoint_port"])
        fixture = dict(switch=sw.model_dump(mode="json"), endpoint=ap.model_dump(mode="json"), link=link.model_dump(mode="json"), external_power_condition="as_created_unchanged")
        baseline["boot"] = exp.executor.wait_until_ready(exp.switch, timeout_seconds=150).model_dump(mode="json")
        for label, mode in (("AUTO_1", PoEInlineMode.AUTO), ("NEVER", PoEInlineMode.NEVER), ("AUTO_2", PoEInlineMode.AUTO)):
            prove_processes()
            if command("git", "status", "--porcelain") or command("git", "rev-parse", "HEAD") != baseline["local_head"]:
                raise RuntimeError("Frozen LIVE source changed")
            exp.apply(mode)
            capture = exp.capture(label)
            captures.append(capture)
            raw_files[capture.raw_file] = capture.observation["raw_output"].encode()
            print(label + " captured; diagnostic=" + str(capture.observation["ports"]) + "; completeness=" + str(all(capture.table_completeness.values())), flush=True)
    except Exception as exc:
        problems.append(type(exc).__name__ + ": " + str(exc))
    finally:
        if creation_started:
            try:
                exp.apply(PoEInlineMode.AUTO)
                restored = exp.capture("RESTORE")
                raw = restored.observation["raw_output"].encode()
                raw_files[restored.raw_file] = raw
                restoration["fresh_readback"] = restored.model_dump(mode="json")
                capture_delivery(restored, raw, exp.switch)
                row = restored.observation["ports"][0]["row"]
                restoration["power_inline_auto_proven"] = row is not None and row["admin"] == "auto"
            except Exception as exc:
                problems.append("Restoration readback: " + str(exc))
            for name, key in ((exp.endpoint, "endpoint_deleted"), (exp.switch, "switch_deleted")):
                try:
                    restoration[key] = exp.fixture.delete_device(name)
                except Exception as exc:
                    problems.append("Cleanup: " + str(exc))
            try:
                restoration["residue_retired"] = list(exp.fixture.retire_session_residue(preexisting))
                restoration["inventory_fingerprint_after"] = exp.fixture.wait_for_inventory_fingerprint(opening)
                restoration["inventory_restored"] = restoration["inventory_fingerprint_after"] == opening
                restoration["fixture_removed"] = exp.names() == preexisting
                closing = exp.environment()
                restoration["environment_after"] = closing
                restoration["realtime_restored"] = closing.get("simulation_mode") is False
                exp.bridge.collect_completed()
                files_clean = not list(exp.bridge.dir.glob("req_*.js")) and not list(exp.bridge.dir.glob("res_*.txt"))
                final_processes = prove_processes()
                before_pids = {p["ProcessId"] for p in baseline["processes"] if p["Name"] == "PacketTracer.exe"}
                after_pids = {p["ProcessId"] for p in final_processes if p["Name"] == "PacketTracer.exe"}
                safety = dict(clean=files_clean and exp.bridge.pt_alive() and before_pids == after_pids and
                              closing == env and not exp.transport_problems and not problems,
                              mailbox_clean=files_clean, runtime_heartbeat_fresh=exp.bridge.pt_alive(),
                              same_pt_processes=before_pids == after_pids, before_pt_pids=sorted(before_pids),
                              after_pt_pids=sorted(after_pids), transport_problems=exp.transport_problems,
                              file_safety="untitled workspace; no save issued; saved_filename remained empty",
                              external_power_condition="as_created_unchanged",
                              frozen_source_unchanged=command("git", "rev-parse", "HEAD") == baseline["local_head"] and not command("git", "status", "--porcelain"))
            except Exception as exc:
                problems.append("Safety finalization: " + str(exc))
        http.stop()
    completed = utc()
    print("LIVE CLOSED; persisting after cleanup", flush=True)
    evidence = PoE2Evidence(schema_version=1, experiment_id=run_id,
        started_at_utc=started, completed_at_utc=completed, START_HEAD=START_HEAD,
        start_head_committed_at_utc=command("git", "show", "-s", "--format=%cI", START_HEAD),
        frozen_live_sha=baseline["local_head"], packet_tracer_build=BUILD, exact_binding=BINDING,
        fixture=fixture, baseline=baseline, calibration_reference=dict(path=CALIBRATION, sha256=CALIBRATION_SHA, productive=False),
        captures=captures, experimental_classification="UNKNOWN", integration_result="NOT_ATTEMPTED",
        authority_delta="none; qualification only", restoration=restoration, safety=safety, problems=problems)
    for candidate in ("POSITIVE", "NEGATIVE"):
        trial = evidence.model_copy(update={"experimental_classification": candidate})
        if validate_poe2_evidence(trial, raw_files).is_valid:
            evidence = trial
            break
    directory = resolve_within(ROOT, Path("docs/reference/cp-scale/canonical-live-evidence") / safe_name_component(run_id))
    directory.mkdir(parents=True, exist_ok=False)
    for name, content in raw_files.items():
        resolve_within(directory, safe_name_component(name)).write_bytes(content)
    path = resolve_within(directory, "evidence.json")
    path.write_bytes((evidence.model_dump_json(indent=2) + "\n").encode())
    persisted = PoE2Evidence.model_validate_json(path.read_bytes())
    readback = {n: resolve_within(directory, safe_name_component(n)).read_bytes() for n in raw_files}
    validation = validate_poe2_evidence(persisted, readback)
    print(json.dumps(dict(bundle=str(directory), experimental_result=evidence.experimental_classification,
                         integration_result=evidence.integration_result, validation=validation.to_dict(),
                         restoration=restoration.get("power_inline_auto_proven"), safety=safety), indent=2))
    return 0 if validation.is_valid else 2


if __name__ == "__main__":
    raise SystemExit(main())
