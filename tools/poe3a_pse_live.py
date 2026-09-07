"""One governed PSE run over the exact canonical 7960 binding on a 3560-24PS.

The binding is rederived from `cp_scale_physical_design()` at the frozen SHA,
never supplied by the caller, and no caller-supplied IOS or JavaScript reaches
Packet Tracer: the three mode changes come from `PoEInlineMode` and the reads
from the governed executor's own registered qualification query.

What this produces is one typed `PoEPseDeliveryScope` -- the POE-3A claim
contract -- built from the measured captures, plus the raw bytes it was read
from, so a later reader can check the typed conclusion against the text.

What it deliberately does NOT produce is authority. A positive PoE claim also
requires `LiveSessionSafetyEvidence` that passes
`validate_live_session_positive_admission`, which demands an exact canonical
`.pts` and a disposable copy with matching SHA-256 identities. This session
runs on an empty untitled workspace: there is no canonical file at risk, and
this repository has no capability to open or save one. Fabricating that
evidence for a file Packet Tracer never touched would be a lie in the exact
place the contract exists to prevent one, so the bundle records the run as
non-productive and says why.
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
import sys

import packet_tracer_mcp
from packet_tracer_mcp.domain.enterprise.models.capabilities import (
    CapabilityStatus, EvidenceSource,
)
from packet_tracer_mcp.domain.enterprise.scenarios.cp_scale_physical import (
    cp_scale_physical_design,
)
from packet_tracer_mcp.domain.enterprise.services.poe_claims import (
    _AUTHORIZED_OBSERVATION_METHODS,
)
from packet_tracer_mcp.domain.enterprise.services.poe_pse_claims import (
    PoEPseCapture, PoEPseDeliveryScope, decode_poe_pse_delivery_scope,
    encode_poe_pse_dimensions,
)
from packet_tracer_mcp.infrastructure.execution.import_isolation_preflight import (
    ImportIsolationPreflight,
)
from packet_tracer_mcp.infrastructure.execution.live_bridge import PTCommandBridge
from packet_tracer_mcp.infrastructure.execution.poe2_evidence import (
    BUILD, START_HEAD, completeness,
)
from packet_tracer_mcp.shared.utils import resolve_within, safe_name_component

from poe2_ap_live import (
    Experiment, authenticated_status, command, prove_processes, utc,
)
from poe_inline_calibration_live import PoEInlineMode

ROOT = Path(__file__).resolve().parents[1]
REPO = "andres18113/cisco-muejeje"
BRANCH = "feature/runtime-ripv2"
ENDPOINT_MODEL = "7960"


def governed_binding() -> dict[str, str]:
    """The exact binding the canonical design demands, read from source."""
    design = cp_scale_physical_design()
    models = {device.id: device.model for site in design.sites for device in site.devices}
    candidates = sorted(
        (binding.device_id, binding.device_port, binding.endpoint_port)
        for site in design.sites for binding in site.endpoint_bindings
        if binding.endpoint_model == ENDPOINT_MODEL
        and models.get(binding.device_id) == "3560-24PS"
    )
    if not candidates:
        raise RuntimeError("The canonical design carries no 3560-24PS 7960 binding")
    device_id, device_port, endpoint_port = candidates[0]
    return {
        "device_id": device_id, "switch_model": "3560-24PS",
        "switch_port": device_port, "endpoint_model": ENDPOINT_MODEL,
        "endpoint_port": endpoint_port,
    }


def source_baseline(binding: dict[str, str]) -> dict:
    if command("git", "branch", "--show-current") != BRANCH:
        raise RuntimeError("Wrong branch")
    if command("git", "status", "--porcelain"):
        raise RuntimeError("Worktree must be clean")
    sha = command("git", "rev-parse", "HEAD")
    command("git", "merge-base", "--is-ancestor", START_HEAD, sha)
    remote = json.loads(command(
        "gh", "api", "repos/" + REPO + "/git/ref/heads/" + BRANCH,
    ))["object"]["sha"]
    if sha != remote:
        raise RuntimeError("Local and remote SHA differ")
    runs = json.loads(command(
        "gh", "run", "list", "--repo", REPO, "--commit", sha,
        "--json", "databaseId,name,headSha,status,conclusion,url",
    ))
    run = next(r for r in runs if r["name"] == "tests" and r["headSha"] == sha)
    jobs = json.loads(command(
        "gh", "api",
        "repos/" + REPO + "/actions/runs/" + str(run["databaseId"]) + "/jobs",
    ))["jobs"]
    if len(jobs) != 4 or any(
        job["conclusion"] != "success" or job["head_sha"] != sha for job in jobs
    ):
        raise RuntimeError("Exact SHA Actions is not 4/4 green")
    if _AUTHORIZED_OBSERVATION_METHODS != frozenset({"manual_visible_power_state"}):
        raise RuntimeError("Strict E5 manual allowlist changed")
    return dict(
        verified_at_utc=utc(), local_head=sha, remote_head=remote, actions_run=run,
        jobs=[{k: job[k] for k in ("name", "conclusion", "head_sha", "html_url")}
              for job in jobs],
        strict_e5_manual_allowlist=True, derived_binding=binding,
        initial_START_HEAD_verified=True,
    )


def pse_capture(label: str, capture, observation: dict) -> PoEPseCapture:
    """Translate one governed observation into the typed claim vocabulary."""
    row = observation["ports"][0]["row"]
    delivering = observation["ports"][0]["delivery"] == "delivering"
    if row is None:
        return PoEPseCapture(label, _MODE_BY_LABEL[label], "absent", 0.0, False, delivering)
    return PoEPseCapture(
        label=label, admin_mode=row["admin"], oper_state=row["oper"],
        power_watts=float(row["power_watts"]), row_present=True, delivering=delivering,
    )


_MODE_BY_LABEL = {"AUTO_1": "auto", "NEVER": "never", "AUTO_2": "auto"}


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
    binding = governed_binding()
    baseline = source_baseline(binding)
    baseline["processes"] = prove_processes()
    baseline["import_isolation"] = dict(
        result=isolation.render(), executable=sys.executable,
        production_file=packet_tracer_mcp.__file__,
        loaded_namespaces=[n for n in ("packet_tracer_mcp", "src.packet_tracer_mcp")
                           if n in sys.modules],
    )
    run_id = ("poe3a-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
              + "-" + token_hex(4))
    started = utc()

    exp = Experiment(run_id)
    if not exp.bridge.pt_alive():
        raise RuntimeError("File bridge heartbeat stale")
    if list(exp.bridge.dir.glob("req_*.js")) or list(exp.bridge.dir.glob("res_*.txt")):
        raise RuntimeError("Foreign mailbox residue")
    os.environ["PT_MCP_BRIDGE_TOKEN"] = token_urlsafe(32)
    http = PTCommandBridge(port=54321, token=os.environ["PT_MCP_BRIDGE_TOKEN"])
    http.start()

    captures, pse_captures, problems = [], [], []
    fixture, restoration, safety, raw_files = {}, {}, {}, {}
    opening = preexisting = env = None
    creation_started = False
    try:
        baseline["fresh_authenticated_bridge"] = authenticated_status(http)
        env = exp.environment()
        if env.get("pt_version") != BUILD or env.get("simulation_mode") is not False:
            raise RuntimeError("Wrong PT build or mode")
        if env.get("devices") != 0 or env.get("links") != 0 or env.get("saved_filename") != "":
            raise RuntimeError("Requires an empty, untitled semantic baseline")
        baseline["environment"] = env
        opening = exp.fixture.inventory_fingerprint()
        preexisting = exp.names()
        baseline["inventory_fingerprint"] = opening
        baseline["devices"] = sorted(preexisting)
        prove_processes()
        print("LIVE OPEN " + run_id + " source=" + baseline["local_head"], flush=True)
        creation_started = True

        switch = exp.fixture.create_device(
            binding["switch_model"], exp.switch, (binding["switch_port"],), arm="candidate")
        phone = exp.fixture.create_device(
            binding["endpoint_model"], exp.endpoint, (binding["endpoint_port"],), arm="candidate")
        if switch.model != binding["switch_model"] or phone.model != binding["endpoint_model"]:
            raise RuntimeError("Fixture model readback mismatch")
        link = exp.fixture.create_link(
            switch, binding["switch_port"], phone, binding["endpoint_port"])
        fixture = dict(switch=switch.model_dump(mode="json"),
                       endpoint=phone.model_dump(mode="json"),
                       link=link.model_dump(mode="json"))
        baseline["boot"] = exp.executor.wait_until_ready(
            exp.switch, timeout_seconds=150).model_dump(mode="json")

        for label, mode in (("AUTO_1", PoEInlineMode.AUTO),
                            ("NEVER", PoEInlineMode.NEVER),
                            ("AUTO_2", PoEInlineMode.AUTO)):
            prove_processes()
            if (command("git", "status", "--porcelain")
                    or command("git", "rev-parse", "HEAD") != baseline["local_head"]):
                raise RuntimeError("Frozen LIVE source changed")
            exp.apply(mode)
            capture = exp.capture(label)
            captures.append(capture)
            raw_files[capture.raw_file] = capture.observation["raw_output"].encode()
            if not all(capture.table_completeness.values()):
                raise RuntimeError(label + " did not satisfy every completeness gate")
            pse_captures.append(pse_capture(label, capture, capture.observation))
            print(label + " captured; ports=" + str(capture.observation["ports"])
                  + "; completeness=True", flush=True)
    except Exception as exc:
        problems.append(type(exc).__name__ + ": " + str(exc))
    finally:
        if creation_started:
            try:
                exp.apply(PoEInlineMode.AUTO)
                restored = exp.capture("RESTORE")
                raw_files[restored.raw_file] = restored.observation["raw_output"].encode()
                restoration["fresh_readback"] = restored.model_dump(mode="json")
                row = restored.observation["ports"][0]["row"]
                restoration["power_inline_auto_proven"] = (
                    row is not None and row["admin"] == "auto")
            except Exception as exc:
                problems.append("Restoration readback: " + str(exc))
            for name, key in ((exp.endpoint, "endpoint_deleted"), (exp.switch, "switch_deleted")):
                try:
                    restoration[key] = exp.fixture.delete_device(name)
                except Exception as exc:
                    problems.append("Cleanup: " + str(exc))
            try:
                restoration["residue_retired"] = list(
                    exp.fixture.retire_session_residue(preexisting))
                restoration["inventory_fingerprint_after"] = (
                    exp.fixture.wait_for_inventory_fingerprint(opening))
                restoration["inventory_restored"] = (
                    restoration["inventory_fingerprint_after"] == opening)
                restoration["fixture_removed"] = exp.names() == preexisting
                closing = exp.environment()
                restoration["environment_after"] = closing
                restoration["realtime_restored"] = closing.get("simulation_mode") is False
                exp.bridge.collect_completed()
                files_clean = (not list(exp.bridge.dir.glob("req_*.js"))
                               and not list(exp.bridge.dir.glob("res_*.txt")))
                final_processes = prove_processes()
                before = {p["ProcessId"] for p in baseline["processes"]
                          if p["Name"] == "PacketTracer.exe"}
                after = {p["ProcessId"] for p in final_processes
                         if p["Name"] == "PacketTracer.exe"}
                safety = dict(
                    clean=(files_clean and exp.bridge.pt_alive() and before == after
                           and closing == env and not exp.transport_problems and not problems),
                    mailbox_clean=files_clean, runtime_heartbeat_fresh=exp.bridge.pt_alive(),
                    same_pt_processes=before == after, before_pt_pids=sorted(before),
                    after_pt_pids=sorted(after), transport_problems=exp.transport_problems,
                    file_safety="untitled workspace; no save issued; saved_filename remained empty",
                    frozen_source_unchanged=(
                        command("git", "rev-parse", "HEAD") == baseline["local_head"]
                        and not command("git", "status", "--porcelain")),
                )
            except Exception as exc:
                problems.append("Safety finalization: " + str(exc))
        http.stop()
    completed = utc()
    print("LIVE CLOSED; persisting after cleanup", flush=True)

    scope = dimensions = decoded = None
    if len(pse_captures) == 3 and not problems:
        scope = PoEPseDeliveryScope(
            schema_version=1, switch_model=binding["switch_model"],
            switch_port=binding["switch_port"], endpoint_model=binding["endpoint_model"],
            endpoint_port=binding["endpoint_port"], packet_tracer_build=BUILD,
            observer_id="GovernedPoEInlineObserver", experiment_id=run_id,
            observed_at=completed, captures=tuple(pse_captures),
            gates=tuple(sorted(captures[0].table_completeness)),
            simultaneous_active_ports=1, cleanup_status="clean",
            inventory_restoration="restored", live_safety="admitted",
        )
        try:
            dimensions = encode_poe_pse_dimensions(scope)
        except ValueError as exc:
            problems.append("PSE contract refused the measured scope: " + str(exc))

    bundle = dict(
        schema_version=1, kind="poe3a-pse-delivery-measurement", experiment_id=run_id,
        started_at_utc=started, completed_at_utc=completed, START_HEAD=START_HEAD,
        frozen_live_sha=baseline["local_head"], packet_tracer_build=BUILD,
        exact_binding=binding, productive=False,
        integration_result="NOT_ATTEMPTED",
        authority_delta="none; measurement only",
        not_productive_because=(
            "A positive PoE claim additionally requires LiveSessionSafetyEvidence that "
            "passes validate_live_session_positive_admission, which demands an exact "
            "canonical .pts and a disposable copy with matching SHA-256 identities. This "
            "run used an empty untitled workspace, so no canonical file was ever at risk "
            "and none can honestly be attested. The measurement below is real; the "
            "authority step is not taken."
        ),
        baseline=baseline, fixture=fixture,
        captures=[c.model_dump(mode="json") for c in captures],
        pse_scope=(asdict(scope) if scope is not None else None),
        pse_dimensions=dimensions, restoration=restoration, safety=safety,
        problems=problems,
    )

    directory = resolve_within(
        ROOT, Path("docs/reference/cp-scale/canonical-live-evidence") / safe_name_component(run_id))
    directory.mkdir(parents=True, exist_ok=False)
    for name, content in raw_files.items():
        resolve_within(directory, safe_name_component(name)).write_bytes(content)
    path = resolve_within(directory, "evidence.json")
    path.write_bytes((json.dumps(bundle, indent=2, sort_keys=True) + "\n").encode())

    print(json.dumps(dict(
        bundle=str(directory), binding=binding,
        measured=[asdict(c) for c in pse_captures],
        pse_contract_accepts_the_measurement=dimensions is not None,
        integration_result=bundle["integration_result"],
        restoration=restoration.get("inventory_restored"),
        safety=safety, problems=problems,
    ), indent=2))
    return 0 if not problems else 2


if __name__ == "__main__":
    raise SystemExit(main())
