"""Provenance for the positive Voice A/B raw runs.

The runs themselves live under ignored `data/`, which is where generated
runtime journals belong: they are megabyte-scale and there is no repository
precedent for committing them.  What that costs is identity -- a file under
`data/` can be overwritten by the next LIVE, and then the measurement it held
is gone with nothing left to say it ever existed.

This ledger is the smallest thing that buys the identity back, and it follows
the convention `docs/reference/cp-scale/live_canonical_checkpoint.json` already
set: a small TRACKED record that names the ignored artefact and pins its
SHA-256.  The canonical filename the runner writes is deliberately absent from
it: `positive-voice-ab.json` is overwritten by every LIVE, so recording a
digest against that name would publish a promise the next run breaks.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "docs" / "reference" / "cp-scale" / "positive_voice_ab_runs.json"
RAW_DIRECTORY = ROOT / "data" / "cp-scale"
CANONICAL_FILENAME = "positive-voice-ab.json"

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_COMMIT = re.compile(r"^[0-9a-f]{40}$")

#: Provenance of the SOURCE HEAD, which is not the same fact as the run.  Only
#: run 3 had its head written down while the session was live; the first two
#: were recovered afterwards by bracketing the artefact's mtime between two
#: commit timestamps, and that is a weaker kind of knowing.  Recording which
#: one produced each head is the difference between provenance and a guess
#: that reads like provenance.
HEAD_PROVENANCE = {"HANDOFF_RECORDED", "DERIVED_FROM_ARTEFACT_MTIME"}

ROLES = {
    "HARNESS_BOUNDARY_WRONG_PHONE_ADDRESSING_INTERFACE",
    "HARNESS_BOUNDARY_EMPTY_ADDRESS_SEMANTICS",
    "AUTHORITATIVE_SAME_FAILURE_MEASUREMENT",
    "FOUNDATION_QUALIFICATION_MEASUREMENT",
    "PORTFAST_ONLY_CAUSAL_INTERVENTION",
}


@pytest.fixture(scope="module")
def ledger() -> dict:
    return json.loads(LEDGER.read_text(encoding="utf-8"))


def test_the_ledger_declares_its_schema_and_what_it_is_about(ledger):
    assert ledger["schema"] == "cp-scale-voice-ab-evidence-v1"
    assert ledger["diagnostic"] == "POSITIVE_DISPOSABLE_VOICE_AB"
    assert isinstance(ledger["runs"], list) and ledger["runs"]


def test_every_run_carries_a_digest_a_head_and_how_that_head_is_known(ledger):
    for entry in ledger["runs"]:
        assert _SHA256.match(entry["sha256"]), entry["filename"]
        assert _COMMIT.match(entry["source_head"]), entry["filename"]
        assert entry["source_head_provenance"] in HEAD_PROVENANCE, entry["filename"]
        assert entry["role"] in ROLES, entry["filename"]
        assert entry["outcome"], entry["filename"]
        assert entry["packet_tracer_version"], entry["filename"]


def test_the_three_known_runs_are_recorded_in_the_order_they_ran(ledger):
    assert [item["run"] for item in ledger["runs"]][:3] == ["run1", "run2", "run3"]
    roles = {item["run"]: item["role"] for item in ledger["runs"]}
    assert roles["run1"] == "HARNESS_BOUNDARY_WRONG_PHONE_ADDRESSING_INTERFACE"
    assert roles["run2"] == "HARNESS_BOUNDARY_EMPTY_ADDRESS_SEMANTICS"
    assert roles["run3"] == "AUTHORITATIVE_SAME_FAILURE_MEASUREMENT"
    outcomes = {item["run"]: item["outcome"] for item in ledger["runs"]}
    assert outcomes["run1"] == "UNOBSERVABLE"
    assert outcomes["run2"] == "UNOBSERVABLE"
    assert outcomes["run3"] == "SAME_FAILURE"


def test_no_two_runs_share_a_filename_or_a_digest(ledger):
    names = [item["filename"] for item in ledger["runs"]]
    digests = [item["sha256"] for item in ledger["runs"]]

    assert len(names) == len(set(names))
    assert len(digests) == len(set(digests))


def test_the_canonical_filename_is_never_a_ledger_entry(ledger):
    # Every LIVE overwrites it.  A digest recorded against that name would be
    # a promise the very next run breaks, and the archive under a unique name
    # is what actually preserves the measurement.
    names = {item["filename"] for item in ledger["runs"]}

    assert CANONICAL_FILENAME not in names
    assert all(name.startswith("positive-voice-ab-run") for name in names)


def test_a_retained_raw_run_still_hashes_to_what_the_ledger_recorded(ledger):
    # `data/` is ignored, so on a fresh clone there is nothing to compare and
    # the ledger IS the record.  Wherever the artefact survives, it has to
    # agree -- a ledger that drifts from the file it names is worse than none.
    compared = 0
    for entry in ledger["runs"]:
        raw = RAW_DIRECTORY / entry["filename"]
        if not raw.is_file():
            continue
        compared += 1
        assert hashlib.sha256(raw.read_bytes()).hexdigest() == entry["sha256"], (
            entry["filename"]
        )
    if compared == 0:
        pytest.skip("no retained raw run is present in this checkout")


def test_run_three_records_that_the_canonical_file_was_its_own_copy(ledger):
    # The archive and the canonical file were byte-identical when run 3 ended.
    # Writing that down is what stops a later reader wondering whether the
    # archive was a partial copy of a file that has since moved on.
    run3 = next(item for item in ledger["runs"] if item["run"] == "run3")

    assert run3["canonical_copy_at_write"] is True


# --- the tool that maintains it ---------------------------------------------
#
# It imports nothing from the production package, so it may be loaded here
# directly: there is no second namespace identity to create.

import tools.cp_scale_voice_ab_ledger as tool  # noqa: E402


def _isolate(monkeypatch, tmp_path: Path) -> tuple[Path, Path]:
    raw = tmp_path / "raw"
    raw.mkdir()
    ledger = tmp_path / "ledger.json"
    monkeypatch.setattr(tool, "RAW_DIRECTORY", raw)
    monkeypatch.setattr(tool, "LEDGER_PATH", ledger)
    return raw, ledger


def _record(**overrides):
    fields = {
        "run": "run9",
        "filename": "positive-voice-ab-run9-probe.json",
        "source_head": "0" * 40,
        "role": "FOUNDATION_QUALIFICATION_MEASUREMENT",
        "outcome": "SAME_FAILURE",
        "packet_tracer_version": "9.0.1.0858",
        "head_provenance": "HANDOFF_RECORDED",
        "note": "",
    }
    fields.update(overrides)
    return tool.record(**fields)


def test_the_digest_is_computed_from_the_file_and_never_supplied(monkeypatch, tmp_path):
    raw, _ = _isolate(monkeypatch, tmp_path)
    (raw / "positive-voice-ab-run9-probe.json").write_bytes(b'{"outcome": "x"}')

    entry = _record()

    assert entry["sha256"] == hashlib.sha256(b'{"outcome": "x"}').hexdigest()


def test_recording_a_run_whose_artefact_is_absent_is_refused(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)

    with pytest.raises(SystemExit):
        _record()


def test_the_canonical_filename_can_never_be_recorded(monkeypatch, tmp_path):
    raw, _ = _isolate(monkeypatch, tmp_path)
    (raw / CANONICAL_FILENAME).write_bytes(b"{}")

    with pytest.raises(SystemExit):
        _record(filename=CANONICAL_FILENAME)


def test_archiving_never_overwrites_a_run_that_is_already_there(monkeypatch, tmp_path):
    # The one thing this tool must not do is destroy a measurement while
    # recording another one.
    raw, _ = _isolate(monkeypatch, tmp_path)
    (raw / CANONICAL_FILENAME).write_bytes(b'{"outcome": "new"}')
    (raw / "positive-voice-ab-run9-probe.json").write_bytes(b'{"outcome": "old"}')

    with pytest.raises(SystemExit):
        tool.archive("positive-voice-ab-run9-probe.json")
    assert (raw / "positive-voice-ab-run9-probe.json").read_bytes() == b'{"outcome": "old"}'


def test_an_archive_that_still_matches_the_canonical_file_says_so(monkeypatch, tmp_path):
    raw, _ = _isolate(monkeypatch, tmp_path)
    (raw / CANONICAL_FILENAME).write_bytes(b'{"outcome": "same"}')
    tool.archive("positive-voice-ab-run9-probe.json")

    assert _record()["canonical_copy_at_write"] is True

    (raw / CANONICAL_FILENAME).write_bytes(b'{"outcome": "a later live"}')
    assert _record()["canonical_copy_at_write"] is False


def test_verify_reports_a_ledger_that_drifted_from_its_artefact(monkeypatch, tmp_path):
    raw, _ = _isolate(monkeypatch, tmp_path)
    (raw / "positive-voice-ab-run9-probe.json").write_bytes(b'{"outcome": "x"}')
    _record()
    assert tool.verify() == 0

    (raw / "positive-voice-ab-run9-probe.json").write_bytes(b'{"outcome": "edited"}')
    assert tool.verify() == 1


def test_an_unknown_role_or_a_short_head_is_refused(monkeypatch, tmp_path):
    raw, _ = _isolate(monkeypatch, tmp_path)
    (raw / "positive-voice-ab-run9-probe.json").write_bytes(b"{}")

    with pytest.raises(SystemExit):
        _record(role="LOOKS_IMPORTANT")
    with pytest.raises(SystemExit):
        _record(source_head="485ef13")


def test_the_causal_intervention_has_a_role_of_its_own(monkeypatch, tmp_path):
    # A one-variable intervention is not another qualification measurement, and
    # a ledger that filed it as one would lose what made run 5 different.
    raw, _ = _isolate(monkeypatch, tmp_path)
    (raw / "positive-voice-ab-run9-probe.json").write_bytes(b"{}")

    entry = _record(role="PORTFAST_ONLY_CAUSAL_INTERVENTION")

    assert entry["role"] == "PORTFAST_ONLY_CAUSAL_INTERVENTION"
    assert "PORTFAST_ONLY_CAUSAL_INTERVENTION" in tool.ROLES
