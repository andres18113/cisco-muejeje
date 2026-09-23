r"""Measure the scalable acceptance route over SIMULATED campuses.

Run from the checkout root with the checkout's interpreter:

    .venv\\Scripts\\python.exe tests\\http_acceptance_scale_benchmark.py OUT.json

Every number it prints was produced by the production coordinator, session
composition, product use case, runtimes, readiness gate, ledger, evaluator and
stores, driven over the simulated campus terminal with a fake clock. Simulated
seconds come from that clock: each dispatch costs `latency` simulated seconds
and each receiver reading costs `receiver_cost`, so feasibility is never shown
by a zero-latency trace alone. Wall time, evaluator time and peak memory are
measured on the machine that runs it. None of it is Packet Tracer behaviour or
Packet Tracer capacity.
"""

from __future__ import annotations

import json
import math
import platform
import sys
import tempfile
import time
import tracemalloc
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from campus_product_simulation import campus_payload, compose_campus
from cold_http_acceptance_harness import MARKER
from scalable_http_acceptance_harness import build_scalable_harness

from packet_tracer_mcp.application.use_cases import accept_cold_http

#: Per dispatch, in simulated seconds, and per receiver reading (the measured
#: Win32 reading on the delivery machine: median 5 ms, p95 8 ms, max 15 ms).
LATENCY_SECONDS = 0.05
RECEIVER_COST_SECONDS = 0.015
CASES = ((2, 1), (20, 1), (200, 1), (1000, 3))
BEHAVIOURS = ("immediate_fwd", "delayed_fwd", "persistent_non_fwd")


def _configure(harness, behaviour: str) -> None:
    terminal = harness.terminal
    terminal.latency = lambda script: LATENCY_SECONDS
    harness.receiver.cost = RECEIVER_COST_SECONDS
    if behaviour == "delayed_fwd":
        terminal.access_forwarding_after = {
            name: 26.0 for name in terminal.network.switches
        }
        terminal.trunk_forwarding_after = 12.0
    elif behaviour == "persistent_non_fwd":
        terminal.access_forwarding_after = {
            name: math.inf for name in terminal.network.switches
        }


def measure(clients: int, sites: int, behaviour: str, plans) -> dict[str, object]:
    """Run one attempt and return what it cost and what it produced."""
    workspace = Path(tempfile.mkdtemp(prefix="scale-"))
    harness = build_scalable_harness(workspace, clients, sites=sites, plans=plans)
    _configure(harness, behaviour)
    evaluator_seconds = {"value": 0.0}
    original = accept_cold_http.evaluate_scalable_attempt

    def timed(*args, **kwargs):
        started = time.perf_counter()
        try:
            return original(*args, **kwargs)
        finally:
            evaluator_seconds["value"] += time.perf_counter() - started

    accept_cold_http.evaluate_scalable_attempt = timed
    tracemalloc.start()
    started_wall = time.perf_counter()
    started_sim = harness.clock.now
    try:
        result = harness.run()
    finally:
        accept_cold_http.evaluate_scalable_attempt = original
    wall = time.perf_counter() - started_wall
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    envelope = result.envelope
    record_path = envelope.product.get("reloaded_record_path") or envelope.product.get(
        "record_path", ""
    )
    envelope_path = Path(result.envelope_path) if result.envelope_path else None
    kinds = Counter(harness.product_dispatches())
    return {
        "clients": clients,
        "sites": sites,
        "behaviour": behaviour,
        "devices": plans.device_count,
        "links": plans.link_count,
        "http_accepted": envelope.http_accepted,
        "campaign_outcome": envelope.campaign_outcome.value,
        "accepted_clients": sum(1 for item in envelope.clients if item.accepted),
        "represented_clients": len(envelope.clients),
        "never_started_clients": sum(
            1 for item in envelope.clients if item.dispatches == 0
        ),
        "used_operations": envelope.budget.used_operations if envelope.budget else 0,
        "max_operations": envelope.budget.max_operations if envelope.budget else 0,
        "reserve_used": envelope.budget.reserve_used if envelope.budget else 0,
        "receiver_observations": (
            envelope.budget.receiver_observations if envelope.budget else 0
        ),
        "receiver_seconds": (
            envelope.budget.receiver_observation_seconds if envelope.budget else 0.0
        ),
        "simulated_seconds": round(harness.clock.now - started_sim, 3),
        "max_seconds": envelope.budget.max_seconds if envelope.budget else 0,
        "readiness_groups": envelope.product.get("readiness_rows", 0),
        "dispatches_by_kind": dict(sorted(kinds.items())),
        "wall_seconds": round(wall, 3),
        "evaluator_seconds": round(evaluator_seconds["value"], 3),
        "peak_memory_mib": round(peak / (1024 * 1024), 1),
        "public_result_bytes": len(
            json.dumps(result.product_summary or {}, default=str).encode("utf-8")
        ),
        "record_bytes": Path(record_path).stat().st_size if record_path else 0,
        "envelope_bytes": (
            envelope_path.stat().st_size
            if envelope_path and envelope_path.exists()
            else 0
        ),
        "primary_failure": envelope.primary_failure,
    }


def main(argv: list[str]) -> int:
    """Run every case and write the measurements as JSON."""
    out = Path(argv[1]) if len(argv) > 1 else Path("http_acceptance_scale.json")
    results = []
    for clients, sites in CASES:
        plans = compose_campus(campus_payload(clients, marker=MARKER, sites=sites))
        for behaviour in BEHAVIOURS:
            row = measure(clients, sites, behaviour, plans)
            results.append(row)
            print(
                json.dumps(
                    {
                        key: row[key]
                        for key in (
                            "clients",
                            "behaviour",
                            "http_accepted",
                            "used_operations",
                            "simulated_seconds",
                            "wall_seconds",
                            "evaluator_seconds",
                            "peak_memory_mib",
                            "envelope_bytes",
                            "record_bytes",
                        )
                    }
                ),
                flush=True,
            )
    out.write_text(
        json.dumps(
            {
                "environment": {
                    "platform": platform.platform(),
                    "python": sys.version.split()[0],
                    "latency_seconds": LATENCY_SECONDS,
                    "receiver_cost_seconds": RECEIVER_COST_SECONDS,
                    "note": "simulated Packet Tracer; not Packet Tracer capacity",
                },
                "results": results,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
