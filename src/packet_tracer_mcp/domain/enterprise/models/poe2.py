"""Passive, versioned POE-2 evidence envelope; policy lives in rules.poe2."""
from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, ConfigDict


class PoE2Capture(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    label: Literal["AUTO_1", "NEVER", "AUTO_2", "RESTORE"]
    started_at_utc: str
    completed_at_utc: str
    expected_prompt: str
    observation: dict
    repeat_observation: dict
    table_completeness: dict[str, bool]
    stable: bool
    raw_file: str
    raw_sha256: str


class PoE2Evidence(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    schema_version: Literal[1]
    experiment_id: str
    started_at_utc: str
    completed_at_utc: str
    START_HEAD: str
    start_head_committed_at_utc: str
    frozen_live_sha: str
    packet_tracer_build: str
    exact_binding: dict[str, str]
    fixture: dict
    baseline: dict
    calibration_reference: dict
    captures: list[PoE2Capture]
    experimental_classification: Literal["POSITIVE", "NEGATIVE", "UNKNOWN"]
    integration_result: Literal["NOT_ATTEMPTED", "PASS", "FAIL"]
    authority_delta: str
    restoration: dict
    safety: dict
    problems: list[str]
