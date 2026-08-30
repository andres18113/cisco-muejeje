"""Durable structure and authority boundaries for the Voice retrospective."""

from __future__ import annotations

import re
from pathlib import Path


DOCUMENT = Path(
    "docs/reference/cp-scale/voice_root_cause_implementation_retrospective.md"
)


def _text() -> str:
    return DOCUMENT.read_text(encoding="utf-8")


def test_retrospective_is_explicitly_noncanonical_and_names_governed_sources():
    text = _text()

    assert "not** a canonical state source" in text
    assert "handoff.md" in text
    assert "positive_voice_ab_runs.json" in text
    assert "archived artifacts under `data/cp-scale/`" in text
    assert "If this retrospective conflicts" in text
    assert "CP_SCALE_STATE_BEGIN" not in text


def test_retrospective_contains_all_required_numbered_sections():
    headings = re.findall(r"^## ([0-9]+)\. ", _text(), flags=re.MULTILINE)

    assert headings == [str(number) for number in range(1, 20)]


def test_every_new_run_is_tied_to_its_archived_artifact():
    text = _text()

    for run in range(17, 24):
        assert f"RUN{run}" in text
        assert f"positive-voice-ab-run{run}-" in text


def test_fact_inference_boundary_and_unobservable_internals_are_preserved():
    text = _text()

    for label in ("MEASURED FACT", "SOURCE FACT", "INFERENCE", "LESSON"):
        assert label in text
    assert (
        "FRESH_7960_DHCP_TRANSACTION = NOT_INDEPENDENTLY_ESTABLISHED"
        in text
    )
    assert "SERVER_RECEIVES_DISCOVER = UNOBSERVABLE" in text
    assert "DHCP_TRANSACTION_PROGRESS = UNOBSERVABLE" in text
    assert "SERVER_RECEIVES_DISCOVER = YES" not in text


def test_decisive_claim_requires_run23_production_confirmation():
    text = _text()

    assert (
        "RUN19 versus RUN22 strongly localized the missing FWD boundary"
        in text
    )
    assert "not, by itself, a perfect one-variable" in text
    assert (
        "RUN22 vs RUN23 confirmed it in the production path"
        in text
    )
    assert "ROOT_CAUSE = CONFIRMED" in text
