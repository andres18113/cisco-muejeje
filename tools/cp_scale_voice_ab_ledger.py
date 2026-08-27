"""Record one positive Voice A/B raw run in the tracked provenance ledger.

The raw runs are generated runtime journals and stay under ignored `data/`,
which is where this repository keeps them.  What that costs is identity: the
canonical `positive-voice-ab.json` is overwritten by every LIVE, so a
measurement that is not archived under a unique name and pinned by digest stops
existing the moment the next run starts.

This tool buys that identity back in the shape the repository already uses for
`live_canonical_checkpoint.json`: a small TRACKED record naming the ignored
artefact and pinning its SHA-256.  It computes the digest itself -- a digest
typed in by hand is a claim about a file nobody read.

    python tools/cp_scale_voice_ab_ledger.py \\
        --run run4 --file positive-voice-ab-run4-foundation.json \\
        --source-head <40-hex> --role FOUNDATION_QUALIFICATION_MEASUREMENT \\
        --outcome SAME_FAILURE --packet-tracer-version 9.0.1.0858

`--archive` copies the canonical file to the unique name first, so the archive
and the digest are of the same bytes.  Archiving never overwrites: a run
filename that already exists is refused, because the one thing this tool must
never do is destroy a previous measurement while recording a new one.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
from pathlib import Path

GOVERNED_ROOT = Path(__file__).resolve().parents[1]
RAW_DIRECTORY = GOVERNED_ROOT / "data" / "cp-scale"
CANONICAL_FILENAME = "positive-voice-ab.json"
LEDGER_PATH = (
    GOVERNED_ROOT / "docs" / "reference" / "cp-scale" / "positive_voice_ab_runs.json"
)

SCHEMA = "cp-scale-voice-ab-evidence-v1"
DIAGNOSTIC = "POSITIVE_DISPOSABLE_VOICE_AB"

ROLES = (
    "HARNESS_BOUNDARY_WRONG_PHONE_ADDRESSING_INTERFACE",
    "HARNESS_BOUNDARY_EMPTY_ADDRESS_SEMANTICS",
    "AUTHORITATIVE_SAME_FAILURE_MEASUREMENT",
    "FOUNDATION_QUALIFICATION_MEASUREMENT",
    "PORTFAST_ONLY_CAUSAL_INTERVENTION",
    "HARNESS_BOUNDARY_EDGE_ACTION_NAME_REJECTED",
    "CURRENT_NAMESPACE_NO_PORTFAST_PAIRED_BASELINE",
    "MEASURED_DHCP_POOL_READBACK_BASELINE",
    "SAME_RUN_ACCESS_VLAN_PAIRED_CAUSAL_CONTROL",
)
HEAD_PROVENANCE = ("HANDOFF_RECORDED", "DERIVED_FROM_ARTEFACT_MTIME")

_COMMIT = re.compile(r"^[0-9a-f]{40}$")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load() -> dict:
    if not LEDGER_PATH.is_file():
        return {"schema": SCHEMA, "diagnostic": DIAGNOSTIC, "runs": []}
    return json.loads(LEDGER_PATH.read_text(encoding="utf-8"))


def save(ledger: dict) -> None:
    LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
    LEDGER_PATH.write_text(
        json.dumps(ledger, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def archive(filename: str) -> Path:
    """Copy the canonical artefact to its unique name, never over another run."""
    destination = RAW_DIRECTORY / filename
    if destination.exists():
        raise SystemExit(
            f"{filename} already exists; a recorded run is never overwritten."
        )
    source = RAW_DIRECTORY / CANONICAL_FILENAME
    if not source.is_file():
        raise SystemExit(f"There is no {CANONICAL_FILENAME} to archive.")
    shutil.copy2(source, destination)
    return destination


def record(
    *, run: str, filename: str, source_head: str, role: str, outcome: str,
    packet_tracer_version: str, head_provenance: str, note: str,
) -> dict:
    if filename == CANONICAL_FILENAME:
        raise SystemExit(
            "The canonical filename is overwritten by every LIVE; record the "
            "unique archive instead."
        )
    if role not in ROLES:
        raise SystemExit(f"Unknown role {role!r}; expected one of {ROLES}.")
    if head_provenance not in HEAD_PROVENANCE:
        raise SystemExit(f"Unknown head provenance {head_provenance!r}.")
    if not _COMMIT.match(source_head):
        raise SystemExit("The source head must be a full 40-character commit id.")
    raw = RAW_DIRECTORY / filename
    if not raw.is_file():
        raise SystemExit(f"{filename} is not present; nothing to hash.")

    raw_digest = digest(raw)
    canonical = RAW_DIRECTORY / CANONICAL_FILENAME
    entry = {
        "run": run,
        "filename": filename,
        "sha256": raw_digest,
        "source_head": source_head,
        "source_head_provenance": head_provenance,
        "role": role,
        "outcome": outcome,
        "packet_tracer_version": packet_tracer_version,
        # MEASURED, not declared: whether the archive still holds exactly what
        # the canonical file held when it was recorded.  It is what lets a
        # later reader know the archive is the whole run and not a partial copy
        # of a file that has since been overwritten by another LIVE.
        "canonical_copy_at_write": bool(
            canonical.is_file() and digest(canonical) == raw_digest
        ),
        "note": note,
    }
    ledger = load()
    runs = [item for item in ledger.get("runs", []) if item.get("run") != run]
    runs.append(entry)
    runs.sort(key=lambda item: item["run"])
    ledger["schema"] = SCHEMA
    ledger["diagnostic"] = DIAGNOSTIC
    ledger["runs"] = runs
    save(ledger)
    return entry


def verify() -> int:
    """Compare every retained raw run against what the ledger recorded."""
    ledger = load()
    mismatched: list[str] = []
    compared = 0
    for entry in ledger.get("runs", []):
        raw = RAW_DIRECTORY / entry["filename"]
        if not raw.is_file():
            continue
        compared += 1
        if digest(raw) != entry["sha256"]:
            mismatched.append(entry["filename"])
    print(json.dumps({
        "event": "VOICE_AB_LEDGER_VERIFY",
        "recorded": len(ledger.get("runs", [])),
        "compared": compared,
        "mismatched": mismatched,
    }))
    return 1 if mismatched else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--run")
    parser.add_argument("--file")
    parser.add_argument("--source-head")
    parser.add_argument("--role", choices=ROLES)
    parser.add_argument("--outcome")
    parser.add_argument("--packet-tracer-version")
    parser.add_argument("--head-provenance", choices=HEAD_PROVENANCE,
                        default="HANDOFF_RECORDED")
    parser.add_argument("--archive", action="store_true",
                        help="copy the canonical artefact to --file first")
    parser.add_argument("--note", default="")
    args = parser.parse_args()

    if args.verify:
        return verify()
    missing = [
        name for name in ("run", "file", "source_head", "role", "outcome",
                          "packet_tracer_version")
        if not getattr(args, name)
    ]
    if missing:
        parser.error("missing required arguments: " + ", ".join(missing))
    if args.archive:
        archive(args.file)
    entry = record(
        run=args.run, filename=args.file, source_head=args.source_head,
        role=args.role, outcome=args.outcome,
        packet_tracer_version=args.packet_tracer_version,
        head_provenance=args.head_provenance, note=args.note,
    )
    print(json.dumps({"event": "VOICE_AB_LEDGER_RECORDED", **entry}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
