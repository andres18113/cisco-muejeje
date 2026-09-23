r"""Measure the scalable acceptance route over SIMULATED campuses.

Run from the checkout root with the checkout's interpreter:

    .venv\\Scripts\\python.exe tests\\http_acceptance_scale_benchmark.py OUT.json

Every number it prints was produced by the production coordinator, session
composition, product use case, runtimes, readiness gate, ledger, evaluator and
stores, driven over the simulated campus terminal with a fake clock. Simulated
seconds come from that clock: each dispatch costs `latency` simulated seconds
and each receiver reading costs `receiver_cost`, so feasibility is never shown
by a zero-latency trace alone. Wall time, evaluator time and memory are
measured on the machine that runs it. None of it is Packet Tracer behaviour or
Packet Tracer capacity.

Each case runs in its own interpreter process, so the process's peak resident
set is that case's own: it includes compiling the campus and the tracemalloc
bookkeeping, and is reported beside the Python allocation peak of the attempt
alone. The source identity every case executed is recorded with the results.
"""

from __future__ import annotations

import json
import math
import platform
import subprocess
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
MIB = 1024 * 1024


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


def _process_memory() -> tuple[int | None, int | None]:
    """Return this process's current and peak resident set, in bytes."""
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        class Counters(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD),
                ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        kernel32 = ctypes.WinDLL("kernel32")
        psapi = ctypes.WinDLL("psapi")
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        psapi.GetProcessMemoryInfo.argtypes = (
            wintypes.HANDLE,
            ctypes.POINTER(Counters),
            wintypes.DWORD,
        )
        psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
        counters = Counters()
        counters.cb = ctypes.sizeof(Counters)
        if not psapi.GetProcessMemoryInfo(
            kernel32.GetCurrentProcess(), ctypes.byref(counters), counters.cb
        ):
            return None, None
        return int(counters.WorkingSetSize), int(counters.PeakWorkingSetSize)
    import resource

    # Linux reports the peak in KiB; the current set is not reported here.
    return None, resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024


def _mib(value: int | None) -> float | None:
    return None if value is None else round(value / MIB, 1)


def _size(path: str | Path | None) -> int:
    return Path(path).stat().st_size if path and Path(path).exists() else 0


def measure(clients: int, sites: int, behaviour: str) -> dict[str, object]:
    """Run one attempt and return what it cost and what it produced."""
    plans = compose_campus(campus_payload(clients, marker=MARKER, sites=sites))
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
    rss_before, _ = _process_memory()
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
    rss_after, rss_peak = _process_memory()
    envelope = result.envelope
    record_path = envelope.product.get("reloaded_record_path") or envelope.product.get(
        "record_path", ""
    )
    kinds = Counter(harness.product_dispatches())
    budget = envelope.budget
    return {
        "clients": clients,
        "sites": sites,
        "behaviour": behaviour,
        "devices": plans.device_count,
        "links": plans.link_count,
        "accepted": result.accepted,
        "provisional_http_accepted": envelope.http_accepted,
        "publication": result.compact_summary()["publication"],
        "campaign_outcome": envelope.campaign_outcome.value,
        "accepted_clients": sum(1 for item in envelope.clients if item.accepted),
        "represented_clients": len(envelope.clients),
        "never_started_clients": sum(
            1 for item in envelope.clients if item.dispatches == 0
        ),
        "used_operations": budget.used_operations if budget else 0,
        "max_operations": budget.max_operations if budget else 0,
        "reserve_used": budget.reserve_used if budget else 0,
        "receiver_observations": budget.receiver_observations if budget else 0,
        "receiver_seconds": budget.receiver_observation_seconds if budget else 0.0,
        "simulated_seconds": round(harness.clock.now - started_sim, 3),
        "max_seconds": budget.max_seconds if budget else 0,
        "readiness_rows": envelope.product.get("readiness_rows", 0),
        "terminal_dispatches": sum(kinds.values()),
        "dispatches_by_kind": dict(sorted(kinds.items())),
        "wall_seconds": round(wall, 3),
        "evaluator_seconds": round(evaluator_seconds["value"], 3),
        "tracemalloc_peak_mib": round(peak / MIB, 1),
        "rss_before_mib": _mib(rss_before),
        "rss_after_mib": _mib(rss_after),
        "process_peak_rss_mib": _mib(rss_peak),
        "product_response_bytes": len(
            json.dumps(result.product_summary or {}, default=str).encode("utf-8")
        ),
        "acceptance_summary_bytes": len(
            json.dumps(result.compact_summary(), default=str).encode("utf-8")
        ),
        "record_bytes": _size(record_path),
        "envelope_bytes": _size(result.envelope_path),
        "publication_bytes": _size(result.publication_path),
        "primary_failure": envelope.primary_failure,
    }


def _source_identity(root: Path) -> dict[str, object]:
    def git(*args: str) -> str:
        return subprocess.run(
            ["git", *args], cwd=root, capture_output=True, text=True, check=False
        ).stdout.strip()

    return {
        "head": git("rev-parse", "HEAD"),
        "tree": git("rev-parse", "HEAD^{tree}"),
        "dirty_paths": [line for line in git("status", "--porcelain").splitlines()],
    }


def main(argv: list[str]) -> int:
    """Run every case in its own process and write the measurements as JSON."""
    if len(argv) == 5 and argv[1] == "--case":
        row = measure(int(argv[2]), int(argv[3]), argv[4])
        print(json.dumps(row))
        return 0
    out = Path(argv[1]) if len(argv) > 1 else Path("http_acceptance_scale.json")
    root = Path(__file__).resolve().parent.parent
    source = _source_identity(root)
    results = []
    for clients, sites in CASES:
        for behaviour in BEHAVIOURS:
            completed = subprocess.run(
                [
                    sys.executable,
                    str(Path(__file__).resolve()),
                    "--case",
                    str(clients),
                    str(sites),
                    behaviour,
                ],
                cwd=root,
                capture_output=True,
                text=True,
                check=True,
            )
            row = json.loads(completed.stdout.strip().splitlines()[-1])
            results.append(row)
            print(
                json.dumps(
                    {
                        key: row[key]
                        for key in (
                            "clients",
                            "behaviour",
                            "accepted",
                            "used_operations",
                            "simulated_seconds",
                            "wall_seconds",
                            "evaluator_seconds",
                            "tracemalloc_peak_mib",
                            "process_peak_rss_mib",
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
                    "executable": sys.executable,
                    "latency_seconds": LATENCY_SECONDS,
                    "receiver_cost_seconds": RECEIVER_COST_SECONDS,
                    "source": source,
                    "note": "simulated Packet Tracer; not Packet Tracer capacity",
                },
                "results": results,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    source_after = _source_identity(root)
    if source_after != source:
        print("WARNING: the source changed while the benchmark ran", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
