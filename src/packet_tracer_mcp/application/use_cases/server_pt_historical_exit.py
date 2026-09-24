"""Pure rules for importing one historical process exit, append-only.

FASTLOOP episode 1's owned Packet Tracer exited after the lead's graceful
close request, outside the maintained `--retire`, which had refused. The
operator's Addendum 02 authorizes importing that one exit from retained
originals. These rules decide whether the offered originals support the
import and build the narrow claim it may make; they read no file and no
process. The CLI supplies the bytes, the launch record and the clock.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from itertools import pairwise

from .server_pt_process_evidence import exit_evidence_findings


@dataclass(frozen=True)
class HistoricalExitImportAuthority:
    """The one historical exit an operator addendum authorizes importing."""

    addendum_sha256: str
    campaign_id: str
    attempt_id: str
    episode: int
    episode_source_sha: str
    episode_source_tree: str


#: SERVER-PT-IOS-FASTLOOP-01 Addendum 02, section 1: the exit of PID 3248.
FASTLOOP_EPISODE_1_EXIT_IMPORT = HistoricalExitImportAuthority(
    addendum_sha256="684636f6436934029709d83e7bd651194aa6d3a7cd9e56da55d592b8660ea288",
    campaign_id="SERVER-PT-IOS-FASTLOOP-01",
    attempt_id="b118c84808bb06f3a8ede6cf124323b2",
    episode=1,
    episode_source_sha="1d086aad5ec473a29ddb3c631d6615ee8344d29d",
    episode_source_tree="1e709da5744ad8861239765bff9fa0a0e1c6a09f",
)

#: Every artifact role, with whether the import requires it.
ARTIFACT_ROLES = {
    "close_capture": True,
    "close_request_output": True,
    "prelaunch_census": True,
    "transcript_excerpt": True,
    "event_log_query": False,
}
#: How each capture field came to be written, as the lead declares it.
FIELD_ORIGINS = frozenset({"observed", "transcribed", "lead_assertion"})
#: Fields the exit claim rests on: only the capturing command's own reading.
_OBSERVED_ONLY = frozenset({"actual_exit_observed", "process_count", "observed_at_utc"})
#: Identity fields may be copied from the request's own answer, never asserted.
_IDENTITY_FIELDS = frozenset(
    {
        "pid",
        "process_path",
        "process_incarnation",
        "method",
        "requested",
        "requested_at_utc",
    }
)
#: The bounds, in the only consistent order, with the clock each one uses.
TIME_BOUNDS = (
    ("close_requested_at_utc", "os"),
    ("presence_last_reported_by_utc", "session_transcript"),
    ("absence_first_reported_by_utc", "session_transcript"),
    ("zero_census_observed_at_utc", "os"),
)
#: Command text that would name a process termination in a retained record.
_TERMINATION = re.compile(
    r"stop-process|taskkill|terminateprocess|\.kill\(|kill\s+-", re.IGNORECASE
)
_REQUEST_FIELD = re.compile(r"([a-z_0-9]+)=(\S+)")


@dataclass(frozen=True)
class _Excerpt:
    """Transcript excerpt lines, decoded, addressed by their source numbers."""

    numbers: tuple[int, ...] = ()
    decoded: tuple[object, ...] = ()

    def strings(self, line: object) -> list[str] | None:
        """Every string in the cited line, or `None` if it is not included."""
        if isinstance(line, bool) or not isinstance(line, int):
            return None
        if line not in self.numbers:
            return None
        return _strings(self.decoded[self.numbers.index(line)])


def _instant(value: object) -> datetime | None:
    """Parse one timezone-aware ISO instant; anything else is unusable."""
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def _strings(value: object) -> list[str]:
    """Every string inside one decoded JSON value, depth first."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, Mapping):
        return [item for child in value.values() for item in _strings(child)]
    if isinstance(value, list):
        return [item for child in value for item in _strings(child)]
    return []


def excerpt_lines(excerpt: bytes) -> list[bytes]:
    """Split one excerpt into lines; a final newline ends the last one."""
    lines = excerpt.split(b"\n")
    if lines and lines[-1] == b"":
        lines.pop()
    return lines


def _excerpt(meta: Mapping[str, object], raw: bytes) -> tuple[_Excerpt, list[str]]:
    """Decode the excerpt; its declared source lines must address it exactly."""
    lines = excerpt_lines(raw)
    numbers = meta.get("source_lines")
    if (
        not isinstance(numbers, list)
        or not numbers
        or any(isinstance(item, bool) or not isinstance(item, int) for item in numbers)
        or numbers != sorted(set(numbers))
        or numbers[0] < 1
        or len(numbers) != len(lines)
    ):
        return _Excerpt(), ["transcript_excerpt_lines_malformed"]
    try:
        decoded = tuple(json.loads(line) for line in lines)
    except ValueError:
        return _Excerpt(), ["transcript_excerpt_line_not_json"]
    return _Excerpt(tuple(numbers), decoded), []


def _capture_findings(
    launch: Mapping[str, object], capture: Mapping[str, object]
) -> list[str]:
    found: list[str] = []
    if capture.get("forced_termination") is not None or exit_evidence_findings(
        launch,
        capture,
        process_count=capture.get("process_count"),
        allow_forced=False,
    ):
        found.append("close_capture_does_not_bind_the_launch")
    if capture.get("method") != "CloseMainWindow":
        found.append("close_capture_method_unexpected")
    return found


def _prelaunch_findings(
    authority: HistoricalExitImportAuthority,
    launch: Mapping[str, object],
    census: Mapping[str, object],
    offered_path: object,
) -> list[str]:
    observed_at = _instant(census.get("observed_at_utc"))
    launched_at = _instant(launch.get("launched_at_utc"))
    if (
        census.get("attempt_id") != authority.attempt_id
        or census.get("source_sha") != launch.get("source_sha")
        or census.get("process_count") != 0
        or offered_path != launch.get("prelaunch_census_path")
        or observed_at is None
        or launched_at is None
        or not observed_at < launched_at
    ):
        return ["prelaunch_census_does_not_bind_the_launch"]
    return []


def _provenance_findings(origins: object, capture: Mapping[str, object]) -> list[str]:
    if (
        not isinstance(origins, Mapping)
        or set(origins) != set(capture)
        or any(value not in FIELD_ORIGINS for value in origins.values())
    ):
        return ["capture_field_provenance_incomplete"]
    if any(origins[name] != "observed" for name in _OBSERVED_ONLY) or any(
        origins[name] == "lead_assertion" for name in _IDENTITY_FIELDS
    ):
        return ["exit_claim_not_supported_by_observation"]
    return []


def _bound_findings(
    bounds: object,
    capture: Mapping[str, object],
    excerpt: _Excerpt,
    artifacts: Mapping[str, bytes],
    first: Sequence[datetime | None],
    archive_at: datetime | None,
) -> list[str]:
    """Check citations and the one strict order launch .. archive."""
    names = [name for name, _clock in TIME_BOUNDS]
    if not isinstance(bounds, Mapping) or set(bounds) != set(names):
        return ["time_bounds_incomplete"]
    found: list[str] = []
    instants: list[datetime | None] = []
    for name, clock in TIME_BOUNDS:
        bound = bounds[name]
        if (
            not isinstance(bound, Mapping)
            or bound.get("clock") != clock
            or bound.get("artifact") not in artifacts
            or (
                bound.get("artifact") == "transcript_excerpt"
                and excerpt.strings(bound.get("line")) is None
            )
        ):
            found.append("time_bound_citation_invalid")
            instants.append(None)
            continue
        instants.append(_instant(bound.get("value")))
    if found:
        return found
    if bounds["close_requested_at_utc"].get("value") != capture.get(
        "requested_at_utc"
    ) or bounds["zero_census_observed_at_utc"].get("value") != capture.get(
        "observed_at_utc"
    ):
        found.append("time_bounds_disagree_with_capture")
    ordered = [*first, *instants, archive_at]
    if any(item is None for item in ordered):
        return [*found, "time_bounds_out_of_order"]
    # Pairs: launch < cleanup < request < presence < absence <= census < archive.
    pairs = list(pairwise(ordered))
    absence_to_census = len(first) + 2
    if not all(
        earlier <= later if index == absence_to_census else earlier < later
        for index, (earlier, later) in enumerate(pairs)
    ):
        found.append("time_bounds_out_of_order")
    return found


def _refusal_findings(
    authority: HistoricalExitImportAuthority, refusal: object, excerpt: _Excerpt
) -> list[str]:
    if not isinstance(refusal, Mapping) or not isinstance(refusal.get("output"), str):
        return ["retire_refusal_not_retained"]
    output = refusal["output"]
    try:
        refused = json.loads(output)
    except ValueError:
        refused = None
    texts = excerpt.strings(refusal.get("line"))
    if (
        texts is None
        or not isinstance(refused, dict)
        or refused.get("outcome") != "refused"
        or not refused.get("reasons")
        or refusal.get("source_sha") != authority.episode_source_sha
        or not any(output in text for text in texts)
    ):
        return ["retire_refusal_not_retained"]
    return []


def _range_findings(retained: object, excerpt: _Excerpt) -> list[str]:
    """Require the retained command range whole and free of terminations."""
    first = retained.get("first_line") if isinstance(retained, Mapping) else None
    last = retained.get("last_line") if isinstance(retained, Mapping) else None
    if (
        isinstance(first, bool)
        or isinstance(last, bool)
        or not isinstance(first, int)
        or not isinstance(last, int)
        or first > last
        or any(line not in excerpt.numbers for line in range(first, last + 1))
    ):
        return ["retained_command_range_incomplete"]
    if any(
        _TERMINATION.search(text)
        for line in range(first, last + 1)
        for text in excerpt.strings(line) or ()
    ):
        return ["retained_record_names_a_termination"]
    return []


def historical_exit_import_findings(
    *,
    authority: HistoricalExitImportAuthority,
    manifest: Mapping[str, object],
    launch: Mapping[str, object],
    cleanup_recorded_at_utc: str,
    artifacts: Mapping[str, bytes],
    archive_at_utc: str,
) -> tuple[str, ...]:
    """Name every way the offered originals fail to support the import.

    `artifacts` maps each offered role to its exact bytes. The capture must
    pass the existing exit rules against the launch; the request's own
    answer, the prelaunch census and the time bounds must agree with it and
    with the launch; the declared field origins must be complete and must not
    rest the exit on an assertion; every citation must name an excerpt line;
    and the retained command range must be whole and name no termination.
    """
    found: list[str] = []
    if (
        manifest.get("kind") != "historical_exit_import"
        or manifest.get("attempt_id") != authority.attempt_id
        or manifest.get("episode") != authority.episode
    ):
        found.append("import_manifest_not_this_authority")
    if (launch.get("source_sha"), launch.get("source_tree")) != (
        authority.episode_source_sha,
        authority.episode_source_tree,
    ):
        found.append("launch_not_the_authorized_episode_source")
    offered = manifest.get("artifacts")
    if (
        not isinstance(offered, Mapping)
        or set(offered) - set(ARTIFACT_ROLES)
        or set(offered) != set(artifacts)
        or any(
            not isinstance(meta, Mapping) or not isinstance(meta.get("path"), str)
            for meta in offered.values()
        )
    ):
        return (*found, "import_artifacts_malformed")
    if any(
        required and role not in offered for role, required in ARTIFACT_ROLES.items()
    ):
        return (*found, "import_artifact_missing")
    try:
        capture = json.loads(artifacts["close_capture"])
        census = json.loads(artifacts["prelaunch_census"])
        request = artifacts["close_request_output"].decode("ascii")
    except (UnicodeDecodeError, ValueError):
        return (*found, "import_artifact_unreadable")
    if not isinstance(capture, dict) or not isinstance(census, dict):
        return (*found, "import_artifact_unreadable")

    found += _capture_findings(launch, capture)
    fields = dict(_REQUEST_FIELD.findall(request))
    if fields.get("requested") != "True" or fields.get(
        "requested_at_utc"
    ) != capture.get("requested_at_utc"):
        found.append("close_request_output_disagrees")
    found += _prelaunch_findings(
        authority, launch, census, offered["prelaunch_census"]["path"]
    )
    found += _provenance_findings(manifest.get("capture_field_provenance"), capture)
    excerpt, excerpt_found = _excerpt(
        offered["transcript_excerpt"], artifacts["transcript_excerpt"]
    )
    found += excerpt_found
    found += _bound_findings(
        manifest.get("time_bounds"),
        capture,
        excerpt,
        artifacts,
        (_instant(launch.get("launched_at_utc")), _instant(cleanup_recorded_at_utc)),
        _instant(archive_at_utc),
    )
    found += _refusal_findings(authority, manifest.get("retire_refusal"), excerpt)
    found += _range_findings(manifest.get("retained_command_range"), excerpt)
    return tuple(dict.fromkeys(found))


def historical_exit_claim(manifest: Mapping[str, object]) -> dict[str, object]:
    """Build the one claim an admitted import makes, and no larger one."""
    origins = manifest.get("capture_field_provenance")
    assertions = sorted(
        name
        for name, origin in (origins.items() if isinstance(origins, Mapping) else ())
        if origin == "lead_assertion"
    )
    return {
        "disposition": "absence_observed_after_graceful_request",
        "owned_process_absence_observed": True,
        "graceful_request_returned_true": True,
        "exit_method": "unproven",
        "exit_instant": (
            "after presence_last_reported_by_utc and no later than "
            "absence_first_reported_by_utc; not observed exactly"
        ),
        "termination_named_in_retained_command_range": False,
        "retire_refused_before_any_effect": True,
        "retire_credited": False,
        "lead_assertions_not_evidence": assertions,
    }
