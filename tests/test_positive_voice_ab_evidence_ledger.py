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
    "HARNESS_BOUNDARY_EDGE_ACTION_NAME_REJECTED",
    "CURRENT_NAMESPACE_NO_PORTFAST_PAIRED_BASELINE",
    "MEASURED_DHCP_POOL_READBACK_BASELINE",
    "SAME_RUN_ACCESS_VLAN_PAIRED_CAUSAL_CONTROL",
    "PAIRED_ACCESS_VLAN_FWD_GATED_ACQUISITION",
    "PHONE_DHCP_LIFECYCLE_QUALIFICATION",
    "PHONE_SVI_DHCP_RETRIGGER_CAUSAL_INTERVENTION",
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


def test_run_eight_adds_only_a_read_and_is_filed_as_its_own_measurement():
    # Run 8 repeats run 7's configuration exactly -- same namespace, same
    # NO-PortFast baseline -- and adds ONE read-only dimension.  Filing it as
    # another paired baseline would hide that a new surface was measured;
    # filing it as an intervention would claim a causal variable moved.
    ledger = json.loads(LEDGER.read_text(encoding="utf-8"))
    run8 = next(item for item in ledger["runs"] if item["run"] == "run8")
    run7 = next(item for item in ledger["runs"] if item["run"] == "run7")

    assert run8["role"] == "MEASURED_DHCP_POOL_READBACK_BASELINE"
    assert run8["outcome"] == run7["outcome"] == "SAME_FAILURE"
    assert run8["source_head"] != run7["source_head"]
    assert "read-only" in run8["note"].casefold()


def test_run_eight_records_the_pool_it_measured_without_claiming_more():
    # The numbers are the finding.  The excluded COUNT is not the excluded
    # CONFIGURATION, and the note must not let a later reader promote it.
    ledger = json.loads(LEDGER.read_text(encoding="utf-8"))
    note = next(
        item for item in ledger["runs"] if item["run"] == "run8"
    )["note"]

    assert "VOICEAB_VOICE" in note
    assert "10.93.0.10-10.93.0.254" in note
    assert "253 of 254" in note
    assert "excluded COUNT" in note
    assert "option 150 remains unreadable" in note



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


def test_run_numbers_are_ordered_numerically_after_run_nine(monkeypatch, tmp_path):
    raw, ledger = _isolate(monkeypatch, tmp_path)
    filename = "positive-voice-ab-run10-probe.json"
    (raw / filename).write_bytes(b"{}")
    ledger.write_text(json.dumps({
        "schema": "cp-scale-voice-ab-evidence-v1",
        "diagnostic": "POSITIVE_DISPOSABLE_VOICE_AB",
        "runs": [{"run": "run9"}],
    }), encoding="utf-8")

    _record(run="run10", filename=filename)

    saved = json.loads(ledger.read_text(encoding="utf-8"))
    assert [item["run"] for item in saved["runs"]] == ["run9", "run10"]


def test_the_causal_intervention_has_a_role_of_its_own(monkeypatch, tmp_path):
    # A one-variable intervention is not another qualification measurement, and
    # a ledger that filed it as one would lose what made run 5 different.
    raw, _ = _isolate(monkeypatch, tmp_path)
    (raw / "positive-voice-ab-run9-probe.json").write_bytes(b"{}")

    entry = _record(role="PORTFAST_ONLY_CAUSAL_INTERVENTION")

    assert entry["role"] == "PORTFAST_ONLY_CAUSAL_INTERVENTION"
    assert "PORTFAST_ONLY_CAUSAL_INTERVENTION" in tool.ROLES


def test_the_observational_lifecycle_has_a_dedicated_ledger_role(
    monkeypatch, tmp_path,
):
    raw, _ = _isolate(monkeypatch, tmp_path)
    (raw / "positive-voice-ab-run9-probe.json").write_bytes(b"{}")

    entry = _record(role="PHONE_DHCP_LIFECYCLE_QUALIFICATION")

    assert entry["role"] == "PHONE_DHCP_LIFECYCLE_QUALIFICATION"
    assert tool.ROLES == (
        "HARNESS_BOUNDARY_WRONG_PHONE_ADDRESSING_INTERFACE",
        "HARNESS_BOUNDARY_EMPTY_ADDRESS_SEMANTICS",
        "AUTHORITATIVE_SAME_FAILURE_MEASUREMENT",
        "FOUNDATION_QUALIFICATION_MEASUREMENT",
        "PORTFAST_ONLY_CAUSAL_INTERVENTION",
        "HARNESS_BOUNDARY_EDGE_ACTION_NAME_REJECTED",
        "CURRENT_NAMESPACE_NO_PORTFAST_PAIRED_BASELINE",
        "MEASURED_DHCP_POOL_READBACK_BASELINE",
        "SAME_RUN_ACCESS_VLAN_PAIRED_CAUSAL_CONTROL",
        "PAIRED_ACCESS_VLAN_FWD_GATED_ACQUISITION",
        "PHONE_DHCP_LIFECYCLE_QUALIFICATION",
        "PHONE_SVI_DHCP_RETRIGGER_CAUSAL_INTERVENTION",
    )


def test_the_phone_svi_retrigger_has_a_dedicated_causal_role(
    monkeypatch, tmp_path,
):
    raw, _ = _isolate(monkeypatch, tmp_path)
    (raw / "positive-voice-ab-run9-probe.json").write_bytes(b"{}")

    entry = _record(
        role="PHONE_SVI_DHCP_RETRIGGER_CAUSAL_INTERVENTION",
    )

    assert entry["role"] == (
        "PHONE_SVI_DHCP_RETRIGGER_CAUSAL_INTERVENTION"
    )
    assert entry["role"] in tool.ROLES


def test_a_run_whose_intervention_never_applied_is_filed_as_the_boundary_it_was():
    # Run 5 asked for PortFast and got `Invalid compiled device name` twice.
    # Filing it as an intervention would put a baseline in the ledger under an
    # experiment's name, which is the same promotion the statuses refuse.
    ledger = json.loads(LEDGER.read_text(encoding="utf-8"))
    run5 = next(item for item in ledger["runs"] if item["run"] == "run5")

    assert run5["role"] == "HARNESS_BOUNDARY_EDGE_ACTION_NAME_REJECTED"
    assert run5["role"] != "PORTFAST_ONLY_CAUSAL_INTERVENTION"
    assert "NOT_APPLIED" in run5["note"]


def test_the_paired_baseline_is_filed_as_the_control_it_is():
    # Run 7 is not another qualification and not an intervention: it is the
    # baseline half of run 6, on the same governed network mutation path and
    # the same namespace.  Its source revision differs only because the
    # post-acquisition edge-marker observer was corrected between the runs.
    # A ledger that filed it as either would lose what makes the pair a pair.
    ledger = json.loads(LEDGER.read_text(encoding="utf-8"))
    run7 = next(item for item in ledger["runs"] if item["run"] == "run7")
    run6 = next(item for item in ledger["runs"] if item["run"] == "run6")

    assert run7["role"] == "CURRENT_NAMESPACE_NO_PORTFAST_PAIRED_BASELINE"
    assert run6["role"] == "PORTFAST_ONLY_CAUSAL_INTERVENTION"
    assert run6["source_head"] == "a2a3e279f663539d0ff0d88be501ae2a595642d2"
    assert run7["source_head"] == "c9d6eada2d354e9dcdbcfe468268f84c97bc0885"
    assert run7["source_head"] != run6["source_head"]
    assert "paired" in run7["note"].casefold()
    assert "edge-marker classifier" in run7["note"].casefold()
    assert "same code" not in run7["note"].casefold()


def test_the_same_run_access_vlan_control_has_a_role_of_its_own():
    # Run 9 is a SAME-RUN two-phone A/B: one disposable, one acquisition
    # window, and the only network-policy difference is the intervention
    # port's access VLAN.  That is neither another PortFast intervention nor
    # a baseline, so it needs its own name in the closed role set.
    assert "SAME_RUN_ACCESS_VLAN_PAIRED_CAUSAL_CONTROL" in tool.ROLES


def test_run_ten_records_the_fail_closed_stp_boundary_without_dhcp_claims():
    ledger = json.loads(LEDGER.read_text(encoding="utf-8"))
    run10 = next(item for item in ledger["runs"] if item["run"] == "run10")

    assert run10["role"] == "PAIRED_ACCESS_VLAN_FWD_GATED_ACQUISITION"
    assert run10["source_head"] == (
        "d7a43778b377dbf7f83e214d7cd390fb34309360"
    )
    assert run10["outcome"] == "UNOBSERVABLE"
    assert run10["canonical_copy_at_write"] is True
    note = run10["note"]
    assert "STP_PRECONDITION_NOT_ESTABLISHED" in note
    assert "no DHCP arm calls" in note
    assert "no IPv4 causal interpretation" in note
    assert "no automatic rerun" in note


def test_run_eleven_records_fwd_then_the_fresh_trigger_boundary_exactly():
    ledger = json.loads(LEDGER.read_text(encoding="utf-8"))
    run11 = next(item for item in ledger["runs"] if item["run"] == "run11")

    assert run11 == {
        "run": "run11",
        "filename": (
            "positive-voice-ab-run11-fresh-dhcp-trigger-unproven.json"
        ),
        "sha256": (
            "8619852a1b405a4191067abefc453d4ccfc14cd28f3702521dd87a981b349a82"
        ),
        "source_head": "8ecee845c0553ae25e4e82d965671e98cf135bf3",
        "source_head_provenance": "HANDOFF_RECORDED",
        "role": "PAIRED_ACCESS_VLAN_FWD_GATED_ACQUISITION",
        "outcome": "UNOBSERVABLE",
        "packet_tracer_version": "9.0.1.0858",
        "canonical_copy_at_write": True,
        "note": run11["note"],
    }
    note = run11["note"]
    assert "new authoritative FWD" in note
    assert "UNOBSERVABLE(COMPLETENESS)" in note
    assert "Both PRE-arm DHCP flags were already YES" in note
    assert "no arm call or POST read" in note
    assert "FRESH_DHCP_TRIGGER_UNPROVEN" in note
    assert "No IPv4 causal interpretation" in note
    assert "no rerun occurred" in note


def test_run_twelve_records_the_observational_lifecycle_without_causal_promotion():
    ledger = json.loads(LEDGER.read_text(encoding="utf-8"))
    run12 = next(item for item in ledger["runs"] if item["run"] == "run12")

    assert run12 == {
        "run": "run12",
        "filename": (
            "positive-voice-ab-run12-phone-dhcp-lifecycle-qualification.json"
        ),
        "sha256": (
            "15fdf8f9ac95ab2e9ee6875f2b14d5c98e6de48e86373343a528c4e1016fbbbd"
        ),
        "source_head": "c0cc3d9f6eef41e7b5f136c9c10104be8d9d89ea",
        "source_head_provenance": "HANDOFF_RECORDED",
        "role": "PHONE_DHCP_LIFECYCLE_QUALIFICATION",
        "outcome": "UNOBSERVABLE",
        "packet_tracer_version": "9.0.1.0858",
        "canonical_copy_at_write": True,
        "note": run12["note"],
    }
    note = run12["note"]
    assert "first observed YES at IMMEDIATELY_BEFORE_STP_FWD_GATE" in note
    assert "Device-level DHCP was UNOBSERVABLE at every retained milestone" in note
    assert "Neither SVI nor device IPv4 appeared" in note
    assert "does not establish Discover, DORA, retry, transaction progress" in note
    assert "sequential reads may shift later observation time" in note
    assert "no rerun occurred" in note


def test_run_thirteen_records_the_valid_negative_causal_result_without_protocol_promotion():
    ledger = json.loads(LEDGER.read_text(encoding="utf-8"))
    run13 = next(item for item in ledger["runs"] if item["run"] == "run13")

    assert run13 == {
        "run": "run13",
        "filename": (
            "positive-voice-ab-run13-phone-svi-dhcp-retrigger-no-address.json"
        ),
        "sha256": (
            "8054b128b2a74cdc380e10b5eff03a80a08f1b75474ac10bfbbb9c5399df8c8a"
        ),
        "source_head": "718075318b18126dd672ec7dfda4fd1faf101f70",
        "source_head_provenance": "HANDOFF_RECORDED",
        "role": "PHONE_SVI_DHCP_RETRIGGER_CAUSAL_INTERVENTION",
        "outcome": "SAME_FAILURE",
        "packet_tracer_version": "9.0.1.0858",
        "canonical_copy_at_write": True,
        "note": run13["note"],
    }
    note = run13["note"]
    assert "Independent authoritative VLAN930 FWD gates" in note
    assert "One PRE endpoint observation per phone" in note
    assert "Only P2 received exact-SVI YES-to-NO-to-YES" in note
    assert "P1 stayed DHCP YES without mutation" in note
    assert "Acquisition was authorized" in note
    assert "binding table contained zero rows" in note
    assert "neither phone registered with SCCP" in note
    assert "NO_ADDRESS_AFTER_PHONE_SVI_DHCP_RETRIGGER" in note
    assert "exact transition was insufficient here" in note
    assert "Discover, DORA, server receipt and transaction progress remain unobservable" in note
    assert "empty semantic workspace were independently restored" in note
    assert "no rerun occurred" in note
