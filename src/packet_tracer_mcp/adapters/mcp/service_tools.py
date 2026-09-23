"""MCP registration for the enterprise-services product entry point.

Translation only. The tool turns four strings into one application call and
one application result into JSON, and it decides nothing: no orchestration, no
transport policy of its own, no domain rule. Everything a caller could get
wrong - an unparseable intent, a deployment that does not exist, a build that
disagrees with the manifest, a process that is not the live one - is refused by
the use case, through the same code path the offline tests drive.

The production wiring itself is `adapters.service_session`, which this tool
shares with the cold-HTTP acceptance envelope. What this route adds is its own
channel policy: the picker is consulted ONCE, lazily after A1/A4, and both
runtimes are bound to that answer, so E5 and E6 cannot end up talking over
different transports within one invocation. The tool passes no optional
session control.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ...application.use_cases.apply_enterprise_services import (
    TransportSelection,
    apply_enterprise_services,
)
from ...domain.enterprise.models.deployment import EnvironmentFingerprint
from ...infrastructure.execution.import_isolation_preflight import (
    ImportIsolationPreflight,
)
from ...infrastructure.execution.transport_outcome import BridgeDispatchOutcome
from ...infrastructure.persistence.deployment_manifest_store import (
    DeploymentManifestStore,
)
from ...infrastructure.persistence.service_run_record_store import (
    ServiceRunRecordStore,
)
from ..service_session import compose_service_session, observe_source_tree

#: The checkout this package was loaded from. The preflight compares the live
#: interpreter and the loaded package against it, so it is read from the
#: package location rather than from a working directory a caller controls.
GOVERNED_ROOT = Path(__file__).resolve().parents[3].parent


def picked_transport_selection(pick_channel: Callable[[], str]) -> TransportSelection:
    """Consult the ordinary picker once and state what it chose."""
    channel = pick_channel()
    ready = channel in {"http", "file"}
    return TransportSelection(
        channel=channel,
        fixed_at=datetime.now(UTC),
        ready=ready,
        detail="" if ready else "Packet Tracer is not connected on any channel.",
    )


def register_service_tools(
    mcp: Any,
    *,
    send_and_wait: Callable[[str, float, str | None], str | None],
    dispatch_and_wait: Callable[[str, float, str | None], BridgeDispatchOutcome],
    send_payload: Callable[[str, str | None], bool],
    query_inventory: Callable[[Sequence[str], str | None], list[dict] | dict],
    pick_channel: Callable[[], str],
    observe_environment: Callable[[str], EnvironmentFingerprint],
    governed_root: Path = GOVERNED_ROOT,
) -> None:
    """Register `pt_apply_enterprise_services` on the enterprise surface.

    The registry passes its own closure-scoped transport helpers, so the tool
    shares the one bridge session the rest of the surface already uses instead
    of opening a second one.
    """

    @mcp.tool()
    def pt_apply_enterprise_services(
        intent_json: str,
        deployment_id: str,
        packet_tracer_version: str,
        run_label: str = "",
    ) -> str:
        """
        Apply governed Server-PT services to an existing deployment.

        The tool binds a DeploymentManifest produced by pt_live_deploy; it
        deploys no topology and deletes no operator resource. The bounded path
        is one site and segment with a static Server-PT and wired PC-PT clients
        on one access switch. DNS/HTTP use the documentary baseline. Mail and
        delegated Server-PT DHCP compile as candidates but remain unavailable
        under the default UNKNOWN capability records.

        Parameters:
        - intent_json: EnterpriseIntent JSON with the requested services; DNS
          requires an explicit address and DHCP requires canonical identities.
        - deployment_id: the already verified physical deployment identity.
        - packet_tracer_version: the exact build, equal to the manifest and the
          freshly observed environment fingerprint.
        - run_label: display metadata; it chooses no path and overwrites no run.

        Returns JSON with per-service and per-client checks, the actual E5
        effect scope, effect/residue uncertainty, owned-resource releases,
        capability provenance and the durable run-record path. Offline results
        never promote a Packet Tracer capability.
        """
        session_factory = compose_service_session(
            send_and_wait=send_and_wait,
            dispatch_and_wait=dispatch_and_wait,
            send_payload=send_payload,
            query_inventory=query_inventory,
            observe_environment=observe_environment,
            select_transport=lambda: picked_transport_selection(pick_channel),
            record_store_factory=ServiceRunRecordStore,
            observe_source_tree=lambda: observe_source_tree(governed_root),
        )
        result = apply_enterprise_services(
            intent_json,
            deployment_id=deployment_id,
            packet_tracer_version=packet_tracer_version.strip(),
            manifest_store_factory=DeploymentManifestStore,
            import_preflight=ImportIsolationPreflight(governed_root),
            record_store_factory=ServiceRunRecordStore,
            session_factory=session_factory,
            run_label=run_label,
        )
        return json.dumps(result.compact_summary(), indent=2, ensure_ascii=False)
