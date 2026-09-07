"""Calibrate the previously uncharacterized auto/off/0 row; no AP claim.

One disposable 3560 Fa0/13 and 7960. Physically remove the created powered
endpoint, prove zero links, then recreate/reconnect it. A missing physical
power path establishes non-delivery independently of any power getter.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from secrets import token_hex, token_urlsafe
import time

from poe2_ap_live import (
    ROOT, Experiment, source_baseline, prove_processes, utc, command,
    authenticated_status, PoEInlineMode, PTCommandBridge, ImportIsolationPreflight,
    BINDING, BUILD, START_HEAD, resolve_within, safe_name_component,
)
from packet_tracer_mcp.infrastructure.execution.poe2_evidence import capture_delivery


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    if not parser.parse_args().execute:
        return 1
    isolation = ImportIsolationPreflight(ROOT).ensure_isolated()
    if not isolation.isolated:
        raise RuntimeError(isolation.render())
    baseline = source_baseline()
    baseline["processes"] = prove_processes()
    baseline["import_isolation"] = isolation.render()
    run_id = "poe2-off-calibration-" + token_hex(6)
    exp = Experiment(run_id)
    if not exp.bridge.pt_alive() or list(exp.bridge.dir.glob("req_*.js")) or list(exp.bridge.dir.glob("res_*.txt")):
        raise RuntimeError("Bridge is stale or dirty")
    os.environ["PT_MCP_BRIDGE_TOKEN"] = token_urlsafe(32)
    http = PTCommandBridge(port=54321, token=os.environ["PT_MCP_BRIDGE_TOKEN"])
    http.start()
    started = utc()
    facts, captures, raw_files, problems, restoration = {}, [], {}, [], {}
    created = False
    try:
        baseline["fresh_authenticated_bridge"] = authenticated_status(http)
        before = exp.environment()
        if before != {"found": True, "saved_filename": "", "pt_version": BUILD,
                      "simulation_mode": False, "devices": 0, "links": 0}:
            raise RuntimeError("Empty untitled Realtime baseline required")
        baseline["environment"] = before
        baseline["fingerprint"] = exp.fixture.inventory_fingerprint()
        preexisting = exp.names()
        print("CALIBRATION LIVE OPEN " + run_id, flush=True)
        created = True
        sw = exp.fixture.create_device(BINDING["switch_model"], exp.switch, (BINDING["switch_port"],), arm="candidate")
        phone = exp.fixture.create_device("7960", exp.endpoint, ("Switch",), arm="candidate")
        link = exp.fixture.create_link(sw, BINDING["switch_port"], phone, "Switch")
        facts["fixture"] = dict(switch=sw.model_dump(mode="json"), endpoint=phone.model_dump(mode="json"), link=link.model_dump(mode="json"))
        exp.executor.wait_until_ready(exp.switch, timeout_seconds=150)
        exp.apply(PoEInlineMode.AUTO)
        for label, capture_label in (("connected_1", "AUTO_1"), ("pd_absent", "NEVER"), ("connected_2", "AUTO_2")):
            prove_processes()
            if label == "pd_absent":
                if not exp.fixture.delete_device(exp.endpoint):
                    raise RuntimeError("Endpoint deletion not proven")
                if exp.endpoint in exp.names() or exp.environment()["links"] != 0:
                    raise RuntimeError("Physical power path remains")
                facts["pd_absent"] = dict(endpoint_absent=True, links=0, observed_at_utc=utc())
                time.sleep(6)
            elif label == "connected_2":
                phone = exp.fixture.create_device("7960", exp.endpoint, ("Switch",), arm="candidate")
                link = exp.fixture.create_link(sw, BINDING["switch_port"], phone, "Switch")
                facts["reconnected_link"] = link.model_dump(mode="json")
                time.sleep(6)
            c = exp.capture(capture_label)
            c.raw_file = label + ".txt"
            captures.append(c.model_dump(mode="json"))
            raw_files[c.raw_file] = c.observation["raw_output"].encode()
            print(label + ": " + capture_delivery(c, raw_files[c.raw_file], exp.switch), flush=True)
    except Exception as exc:
        problems.append(str(exc))
    finally:
        if created:
            try:
                exp.apply(PoEInlineMode.AUTO)
                c = exp.capture("RESTORE")
                restoration["capture"] = c.model_dump(mode="json")
                raw_files[c.raw_file] = c.observation["raw_output"].encode()
                capture_delivery(c, raw_files[c.raw_file], exp.switch)
                restoration["auto_proven"] = c.observation["ports"][0]["row"]["admin"] == "auto"
            except Exception as exc:
                problems.append("Restore: " + str(exc))
            for name in (exp.endpoint, exp.switch):
                try:
                    if not exp.fixture.delete_device(name):
                        problems.append("Not deleted: " + name)
                except Exception as exc:
                    problems.append(str(exc))
            try:
                restoration["residue_retired"] = list(exp.fixture.retire_session_residue(preexisting))
                restoration["fingerprint"] = exp.fixture.wait_for_inventory_fingerprint(baseline["fingerprint"])
                restoration["environment"] = exp.environment()
                restoration["inventory_restored"] = restoration["fingerprint"] == baseline["fingerprint"]
                exp.bridge.collect_completed()
                restoration["mailbox_clean"] = not list(exp.bridge.dir.glob("req_*.js")) and not list(exp.bridge.dir.glob("res_*.txt"))
                restoration["runtime_healthy"] = exp.bridge.pt_alive() and {p["ProcessId"] for p in prove_processes() if p["Name"] == "PacketTracer.exe"} == {p["ProcessId"] for p in baseline["processes"] if p["Name"] == "PacketTracer.exe"}
                restoration["frozen_source_unchanged"] = command("git", "rev-parse", "HEAD") == baseline["local_head"]
                restoration["clean"] = all(restoration.get(k) is True for k in ("auto_proven", "inventory_restored", "mailbox_clean", "runtime_healthy", "frozen_source_unchanged")) and restoration["environment"] == before and not exp.transport_problems and not problems
            except Exception as exc:
                problems.append("Safety: " + str(exc))
        http.stop()
    print("CALIBRATION LIVE CLOSED", flush=True)
    payload = dict(schema_version=1, kind="poe2-pse-off-calibration", experiment_id=run_id,
                   started_at_utc=started, completed_at_utc=utc(), START_HEAD=START_HEAD,
                   frozen_live_sha=baseline["local_head"], packet_tracer_build=BUILD,
                   productive=False, baseline=baseline, facts=facts, captures=captures,
                   restoration=restoration, problems=problems)
    directory = resolve_within(ROOT, "docs/reference/cp-scale/canonical-live-evidence", safe_name_component(run_id))
    directory.mkdir(parents=True, exist_ok=False)
    for name, raw in raw_files.items():
        resolve_within(directory, safe_name_component(name)).write_bytes(raw)
    path = resolve_within(directory, "evidence.json")
    path.write_bytes((json.dumps(payload, indent=2) + "\n").encode())
    print(json.dumps(dict(path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest(), restoration=restoration.get("clean"), problems=problems)))
    return 0 if restoration.get("clean") else 2


if __name__ == "__main__":
    raise SystemExit(main())
