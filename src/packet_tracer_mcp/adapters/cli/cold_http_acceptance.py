"""Operator entry point for one granted cold-HTTP acceptance attempt.

Translation and composition only. The adapter reads the operator's grant and
intent files, composes the production boundaries and prints the coordinator's
summary as JSON. It decides nothing: every refusal comes from a domain rule or
from the coordinator, through the same path the offline tests drive.

Nothing runs by default. Without `--execute` the adapter refuses before it
reads anything, and without `PT_MCP_GOVERNED_ROOT` it refuses before it
composes anything. Building the boundaries performs no I/O: the file mailbox is
opened only when the coordinator reaches its contact step, after local
admission, and under pytest the real import-isolation preflight answers
`TEST_PROCESS`, so the production wiring refuses before any channel exists.

The product session is `adapters.service_session`, the same composition the
MCP tool uses, over a `FixedChannelProductTransport` bound to the granted
channel. The public tool's picker is never consulted here, and no raw
JavaScript, IOS or bridge command is accepted from the operator.
"""

from __future__ import annotations

import argparse
import json
import time
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from typing import Any

from ...application.ports.service_qualification import OpenedTransport
from ...application.use_cases.accept_cold_http import (
    AcceptanceBoundaries,
    AcceptanceChannel,
    AcceptanceRequest,
    accept_cold_http,
)
from ...application.use_cases.apply_enterprise_services import (
    MAX_INTENT_JSON_BYTES,
    ServiceInvocationBinding,
    TransportSelection,
)
from ...domain.enterprise.models.cold_http_acceptance import ACCEPTANCE_CHANNEL
from ...domain.enterprise.models.service_run_record import SourceTreeIdentity
from ...infrastructure.execution.file_bridge import FileBridge
from ...infrastructure.execution.import_isolation_preflight import (
    ImportIsolationPreflight,
    governed_root_from_env,
)
from ...infrastructure.execution.product_channel import FixedChannelProductTransport
from ...infrastructure.execution.service_qualification_lifecycle import (
    PacketTracerDiagnosticLifecycleReader,
)
from ...infrastructure.persistence.campaign_coordination import (
    FileCampaignCoordinator,
)
from ...infrastructure.persistence.cold_http_acceptance_store import (
    ColdHttpAcceptanceStore,
)
from ...infrastructure.persistence.deployment_manifest_store import (
    DeploymentManifestStore,
)
from ...infrastructure.persistence.service_run_record_store import (
    ServiceRunRecordStore,
)
from ..service_session import SessionControls, compose_service_session
from ..service_session import observe_source_tree as observe_checkout
from .service_qualification import repository_identity, runtime_identity

RECORD_DIRECTORY = ("data", "services")
MANIFEST_DIRECTORY = ("data", "deployments")
ENVELOPE_DIRECTORY = ("data", "acceptance", "cold-http")
MAX_GRANT_BYTES = 64 * 1024


def acceptance_session(
    channel: AcceptanceChannel,
    *,
    observe_source: Callable[[], SourceTreeIdentity],
) -> Callable[[], ServiceInvocationBinding]:
    """Compose the product session on the one bound channel, with its controls."""
    fixed = FixedChannelProductTransport(channel.channel, channel.transport)
    return compose_service_session(
        send_and_wait=fixed.send_and_wait,
        dispatch_and_wait=fixed.dispatch_and_wait,
        send_payload=fixed.send_payload,
        query_inventory=fixed.query_inventory,
        observe_environment=fixed.observe_environment,
        select_transport=lambda: TransportSelection(
            channel=channel.channel,
            fixed_at=channel.bound_at,
            ready=True,
        ),
        record_store_factory=lambda: channel.record_store,
        observe_source_tree=observe_source,
        controls=SessionControls(
            clock=channel.clock,
            sleeper=channel.sleeper,
            wait_allowance=channel.wait_allowance,
            owned_release=channel.owned_release,
            effect_admission=channel.effect_admission,
        ),
    )


def open_file_channel(channel: str) -> OpenedTransport:
    """Open only the envelope's bound channel and read its heartbeat."""
    if channel != ACCEPTANCE_CHANNEL:
        return OpenedTransport(channel, None, False, "channel_not_bound_by_envelope")
    bridge = FileBridge()
    live = bridge.pt_alive()
    return OpenedTransport(
        channel, bridge, live, "heartbeat_fresh" if live else "heartbeat_stale"
    )


def _close_channel(opened: OpenedTransport) -> None:
    stop = getattr(opened.transport, "stop", None)
    if callable(stop):
        stop()


def production_boundaries(governed_root: Path) -> AcceptanceBoundaries:
    """Compose the LIVE boundaries; constructing them performs no I/O."""
    return AcceptanceBoundaries(
        import_preflight=ImportIsolationPreflight(governed_root),
        runtime_identity=runtime_identity,
        repository=lambda: repository_identity(governed_root),
        lifecycle=PacketTracerDiagnosticLifecycleReader().read,
        # Exclusion is taken beside the mailbox, which is what two checkouts
        # share, never in a record directory neither of them can see.
        campaign_coordinator=FileCampaignCoordinator(),
        manifest_store=DeploymentManifestStore(
            governed_root.joinpath(*MANIFEST_DIRECTORY)
        ),
        record_store=ServiceRunRecordStore(governed_root.joinpath(*RECORD_DIRECTORY)),
        envelope_store=ColdHttpAcceptanceStore(
            governed_root.joinpath(*ENVELOPE_DIRECTORY)
        ),
        open_channel=open_file_channel,
        close_channel=_close_channel,
        session_factory=partial(
            acceptance_session,
            observe_source=lambda: observe_checkout(governed_root),
        ),
        clock=time.monotonic,
        sleep=time.sleep,
        now=lambda: datetime.now(UTC),
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--grant", default="")
    parser.add_argument("--intent", default="")
    return parser


def _read_text(path: str, limit: int) -> str:
    """Read one operator file within a byte bound; never a partial file."""
    raw = Path(path).read_bytes()
    if len(raw) > limit:
        raise ValueError("the file exceeds its input budget")
    return raw.decode("utf-8")


def _print(payload: Mapping[str, Any]) -> None:
    print(json.dumps(payload, sort_keys=True), flush=True)


def _refusal(detail: str) -> dict[str, Any]:
    return {"campaign_outcome": "refused", "http_accepted": False, "reasons": [detail]}


def main(
    argv: Sequence[str] | None = None,
    *,
    environ: Mapping[str, str] | None = None,
    boundaries_factory=production_boundaries,
) -> int:
    """Run one attempt and return 0 accepted, 1 not accepted or 2 refused."""
    args = _parser().parse_args(argv)
    if not args.execute:
        _print(_refusal("--execute is required; nothing was read or contacted."))
        return 2
    governed_root = governed_root_from_env(environ)
    if governed_root is None:
        _print(_refusal("PT_MCP_GOVERNED_ROOT must declare the governed checkout."))
        return 2
    try:
        grant_text = _read_text(args.grant, MAX_GRANT_BYTES)
        grant_document = json.loads(grant_text)
        intent_json = _read_text(args.intent, MAX_INTENT_JSON_BYTES)
    except (OSError, ValueError) as exc:
        _print(_refusal(f"input_unreadable:{type(exc).__name__}"))
        return 2
    result = accept_cold_http(
        AcceptanceRequest(
            execute=True,
            grant_document=grant_document,
            grant_text=grant_text,
            intent_json=intent_json,
        ),
        boundaries_factory(governed_root),
    )
    _print(result.compact_summary())
    return result.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
