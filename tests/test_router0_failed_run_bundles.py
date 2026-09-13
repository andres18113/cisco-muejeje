"""Immutable Router0 attempts are failures, not successful evidence closure."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INDEX = (
    ROOT
    / "docs"
    / "reference"
    / "cp-scale"
    / "router0_failed_run_bundles.json"
)
STATE = ROOT / "docs" / "reference" / "cp-scale" / "current_state.json"


EXPECTED = {
    "canonical-cp-scale-voice-20260902T215118136599Z-aa94ce992c6b": {
        "executed_sha": "aa94ce992c6bbcd45e44f4aca097f446b28e2ca4",
        "failed_stage": "floor2",
        "failure_sha256": "8cf8f3346a5ec058875839c22c4ea0647f965be9fe0a9b918742812e382a966c",
        "cleanup_sha256": "12ada64f65f8e49503b93e0a2772f7611f2ad26a3a8ddd0d6556c16bf5ba6191",
    },
    "canonical-cp-scale-voice-20260903T002846400677Z-6c6db5556689": {
        "executed_sha": "6c6db55566890f1d9ca9cc06bfc13ae24505e793",
        "failed_stage": "floor3",
        "failure_sha256": "a5b06fea51243887153cbcd48038036c5b3b3b2ca040b20210c8d592717c100a",
        "cleanup_sha256": "f8c0fff1bcee2d6b2418074ae11e16e578e8fa313f9c9d10028d57e235150219",
    },
    "canonical-cp-scale-voice-20260912T165448035171Z-3bb959fc20ac": {
        "executed_sha": "3bb959fc20acb027deae304e1ab28fc1cf40de56",
        "failed_stage": "floor2",
        "failure_sha256": "5df3e6618eff2e39e9b530c3ab2fc2973c49080100d9c8f025fc03a9e9593a9e",
        "cleanup_sha256": "794f8d59e316b62f3394439cf19710949682efcef2e810c9555801156ec55d58",
    },
    "canonical-cp-scale-voice-20260912T233455597224Z-09d2003dd529": {
        "executed_sha": "09d2003dd529c537e20bd759d0e2fffe21c7f7d9",
        "failed_stage": "floor3",
        "failure_sha256": "b7d7f269ec79fbb92e7ad35bba1e6752aeacc501457dccf1ef8913d7106ca29f",
        "cleanup_sha256": "b69277ea9cb4b7982b24273a8d7d820bf63ecf66c4749cf530cdfd04f1833e8b",
    },
    "canonical-cp-scale-voice-20260913T011017280517Z-008da3f6c4c9": {
        "executed_sha": "008da3f6c4c9bcf2ee82fd202d41fd79af300662",
        "failed_stage": "floor3",
        "failure_sha256": "a34ab13d9e401b7c5e802de364fa71a1f62fc8c86fef16460c09b07a6306ab89",
        "cleanup_sha256": "e297ea759ca2a0959ce71dba5b1cab3096c38be9cc8824d0c463c02fface8383",
    },
    "canonical-cp-scale-voice-20260913T015449677311Z-5051c280d3cb": {
        "executed_sha": "5051c280d3cb25e8c7839b79bd728dc6d84b1762",
        "failed_stage": "floor3",
        "failure_sha256": "0fdc8fe07489460e283f98b96f5ecfb6dfd990ae8a7dca901fb1a35e11908cff",
        "cleanup_sha256": "00215c0f3ff000d84a4b49a906fe9becab7d948afa140fc96b4fdd5e86d860a1",
    },
    "canonical-cp-scale-voice-20260913T031542845385Z-ccfb555f685a": {
        "executed_sha": "ccfb555f685ae460a4ced023aab7fc66b981b9f2",
        "failed_stage": "router0-branch",
        "failure_sha256": "dff81031a11f4a5082becd50cd6668485496ec3b2ee50ce9e27be41cc438b696",
        "cleanup_sha256": "173b72fd9b808f300855b8b619f776a554fefdfabf9e47af163badfa454f6786",
    },
}


def test_router0_bundle_index_pins_original_bytes_and_failure_identity():
    index = json.loads(INDEX.read_text(encoding="utf-8"))

    assert index["schema"] == "cp-scale-router0-failed-run-bundles-v1"
    assert index["classification"] == "FAILED"
    assert index["publication_is_success_authority"] is False
    assert index["router0_successful_closure"] is False
    assert {item["run_identity"] for item in index["runs"]} == set(EXPECTED)
    for item in index["runs"]:
        expected = EXPECTED[item["run_identity"]]
        assert item["classification"] == "FAILED"
        assert item["executed_sha"] == expected["executed_sha"]
        assert item["failed_stage"] == expected["failed_stage"]
        artifacts = {artifact["phase"]: artifact for artifact in item["artifacts"]}
        assert artifacts["failure-precleanup"]["sha256"] == expected["failure_sha256"]
        assert artifacts["cleanup"]["sha256"] == expected["cleanup_sha256"]
        for artifact in artifacts.values():
            raw = (ROOT / artifact["path"]).read_bytes()
            assert hashlib.sha256(raw).hexdigest() == artifact["sha256"]
        failure = json.loads(
            (ROOT / artifacts["failure-precleanup"]["path"]).read_text(
                encoding="utf-8",
            )
        )
        cleanup = json.loads(
            (ROOT / artifacts["cleanup"]["path"]).read_text(encoding="utf-8")
        )
        assert failure["run_identity"] == item["run_identity"]
        assert failure["failure"] == item["failure"]
        assert cleanup["source_head"] == item["executed_sha"]
        assert cleanup["run_identity"] == item["run_identity"]
        assert cleanup["cleanup"]["verified"] is True
        assert cleanup["cleanup"]["second"]["semantic_device_count"] == 0
        assert cleanup["cleanup"]["second"]["link_count"] == 0
        assert cleanup["cleanup_realtime"]["verified"] is True


def test_current_state_points_to_the_complete_failed_bundle_index():
    state = json.loads(STATE.read_text(encoding="utf-8"))
    pointer = state["last_live_state"]["run_accounting"][
        "post_ledger_failed_run_bundles"
    ]
    raw = INDEX.read_bytes()

    assert pointer == {
        "path": "docs/reference/cp-scale/router0_failed_run_bundles.json",
        "sha256": hashlib.sha256(raw).hexdigest(),
        "run_count": 7,
        "classification": "FAILED",
        "successful_closure": False,
    }
