"""Join unmodified bridge answers to the product's counted purpose ledger."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from ...domain.enterprise.models.cold_http_acceptance import (
    ColdHttpAcceptanceEnvelope,
)

_EPISODE = re.compile(r"#([1-9][0-9]*)\Z")


def build_raw_answer_index(
    journal_path: Path, envelope: ColdHttpAcceptanceEnvelope
) -> dict[str, Any]:
    """Cite every original response by sequence, purpose and episode."""
    if envelope.budget is None:
        raise ValueError("acceptance budget is missing")
    raw = Path(journal_path).read_bytes()
    events: dict[int, dict[str, dict[str, Any]]] = {}
    for line in raw.splitlines():
        try:
            event = json.loads(line)
        except ValueError as exc:
            raise ValueError("raw journal event is malformed") from exc
        if not isinstance(event, dict):
            raise ValueError("raw journal event is not an object")
        sequence = event.get("sequence")
        kind = event.get("event")
        if (
            isinstance(sequence, bool)
            or not isinstance(sequence, int)
            or sequence <= 0
            or kind not in {"attempt", "answer", "error"}
            or kind in events.setdefault(sequence, {})
        ):
            raise ValueError("raw journal sequence or event is invalid")
        events[sequence][kind] = event
    counted = [entry for entry in envelope.budget.entries if entry.seq > 0]
    if (
        len(counted) != envelope.budget.used_operations
        or {entry.seq for entry in counted} != set(events)
        or {entry.seq for entry in counted} != set(range(1, len(counted) + 1))
    ):
        raise ValueError("raw journal does not match counted product operations")
    indexed: list[dict[str, Any]] = []
    for entry in sorted(counted, key=lambda item: item.seq):
        pair = events[entry.seq]
        attempt = pair.get("attempt")
        answer = pair.get("answer") or pair.get("error")
        if attempt is None or answer is None or len(pair) != 2:
            raise ValueError("original answer is missing for a counted operation")
        request_js = attempt.get("request_js")
        if not isinstance(request_js, str):
            raise ValueError("raw request bytes are missing")
        body = answer.get("raw_answer")
        if body is not None and not isinstance(body, str):
            raise ValueError("original answer has an invalid type")
        match = _EPISODE.search(entry.purpose)
        indexed.append(
            {
                "sequence": entry.seq,
                "purpose": entry.purpose,
                "episode": int(match.group(1)) if match else None,
                "call": entry.call,
                "request_at_utc": attempt.get("at_utc", ""),
                "answer_at_utc": answer.get("at_utc", ""),
                "request_sha256": hashlib.sha256(
                    request_js.encode("utf-8")
                ).hexdigest(),
                "raw_answer_sha256": (
                    hashlib.sha256(body.encode("utf-8")).hexdigest()
                    if body is not None
                    else ""
                ),
                "raw_answer_bytes": len(body.encode("utf-8"))
                if body is not None
                else 0,
                "answer_observed": body is not None,
                "queued": answer.get("queued"),
                "error_type": answer.get("error_type", ""),
            }
        )
    return {
        "attempt_id": envelope.attempt_id,
        "source": envelope.source,
        "journal_sha256": hashlib.sha256(raw).hexdigest(),
        "counted_operations": len(indexed),
        "entries": indexed,
    }
