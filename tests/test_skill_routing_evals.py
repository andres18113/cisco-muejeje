from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from tools.skills_governance import load_manifest


REPO_ROOT = Path(__file__).resolve().parents[1]
CORPUS_PATH = REPO_ROOT / "skills" / "routing-evals.json"
REQUIRED_BIDIRECTIONAL_COLLISIONS = (
    ("enterprise-orchestrator", "enterprise-network-design"),
    ("enterprise-network-design", "enterprise-ipam-capacity"),
    ("enterprise-ipam-capacity", "enterprise-hardware"),
    ("enterprise-hardware", "packet-tracer-capabilities"),
    ("enterprise-configuration", "enterprise-security"),
    ("enterprise-configuration", "enterprise-services"),
    ("enterprise-configuration", "enterprise-voice"),
    ("enterprise-configuration", "campus-layer2"),
    ("enterprise-configuration", "first-hop-redundancy"),
    ("enterprise-configuration", "routing-igp"),
    ("campus-layer2", "first-hop-redundancy"),
    ("campus-layer2", "routing-igp"),
    ("first-hop-redundancy", "routing-igp"),
    ("enterprise-services", "enterprise-voice"),
    ("packet-tracer-runtime", "packet-tracer-capabilities"),
    ("packet-tracer-layout", "enterprise-network-design"),
    ("network-acceptance", "network-diagnosis"),
    ("enterprise-security", "network-acceptance"),
)


def _load_corpus() -> dict[str, object]:
    return json.loads(CORPUS_PATH.read_text(encoding="utf-8"))


def _has_direction(
    cases: list[dict[str, object]],
    expected_primary: str,
    excluded_primary: str,
) -> bool:
    return any(
        case["expected_primary"] == expected_primary
        and excluded_primary in case["excluded_primaries"]
        for case in cases
    )


def test_routing_corpus_is_complete_and_consistent() -> None:
    manifest = load_manifest(REPO_ROOT)
    corpus = _load_corpus()
    entries = manifest["skills"]
    canonical_ids = {entry["id"] for entry in entries}
    active_ids = {entry["id"] for entry in entries if entry["lifecycle"] == "active"}
    cases = corpus["cases"]

    assert corpus["schema_version"] == 1
    assert isinstance(cases, list)
    assert len({case["intent"] for case in cases}) == len(cases)

    positive_counts: Counter[str] = Counter()
    negative_counts: Counter[str] = Counter()
    for case in cases:
        assert set(case) == {"intent", "expected_primary", "excluded_primaries"}
        assert isinstance(case["intent"], str) and case["intent"].strip()
        expected_primary = case["expected_primary"]
        excluded_primaries = case["excluded_primaries"]
        assert expected_primary is None or expected_primary in active_ids
        assert isinstance(excluded_primaries, list)
        assert len(excluded_primaries) == len(set(excluded_primaries))
        assert set(excluded_primaries) <= canonical_ids
        assert expected_primary not in excluded_primaries
        if expected_primary is not None:
            positive_counts[expected_primary] += 1
        negative_counts.update(excluded_primaries)

    assert all(positive_counts[skill_id] >= 3 for skill_id in active_ids)
    assert all(negative_counts[skill_id] >= 3 for skill_id in active_ids)
    assert positive_counts["network-autofix"] == 0
    assert negative_counts["network-autofix"] >= 3


def test_required_routing_collisions_have_both_directions() -> None:
    cases = _load_corpus()["cases"]

    for left, right in REQUIRED_BIDIRECTIONAL_COLLISIONS:
        assert _has_direction(cases, left, right), f"missing {left} over {right} case"
        assert _has_direction(cases, right, left), f"missing {right} over {left} case"


def test_planned_autofix_has_only_negative_routing_evidence() -> None:
    cases = _load_corpus()["cases"]
    autofix_negatives = [
        case for case in cases if "network-autofix" in case["excluded_primaries"]
    ]
    intents = " ".join(case["intent"].lower() for case in autofix_negatives)

    assert not any(case["expected_primary"] == "network-autofix" for case in cases)
    assert any(
        case["expected_primary"] == "network-diagnosis"
        for case in autofix_negatives
    )
    assert "pt_fix_plan" in intents
    assert "live network" in intents
