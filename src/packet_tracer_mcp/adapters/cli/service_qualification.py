"""Operator entry point for one governed Server-PT qualification stage.

Translation and composition only. The adapter turns arguments into one
`QualificationRequest`, composes the production boundaries and prints the
coordinator's summary as JSON. It decides nothing: every refusal comes from the
domain rule or from the coordinator, through the same path the offline tests
drive.

Nothing runs by default. Without `--execute` the adapter refuses before it
reads anything. Without `PT_MCP_GOVERNED_ROOT` it refuses before it composes
anything. Building the production boundaries performs no I/O: the bridge is
started only when the coordinator opens the authorized channel, after local
admission. Under pytest the real import-isolation preflight answers
`TEST_PROCESS`, so the production wiring refuses before any channel exists.

The authorization values come from a reviewer's separate, stage- and
SHA-specific LIVE authorization. This adapter never invents one, and
`docs/qa/server-services-qualification.md` holds the template. No raw
JavaScript, IOS or bridge command is accepted from the operator.

Budget note: the production service runtime polls with an interval equal to
its HTTP timeout, so one fetch performs at most two inspections. The
coordinator therefore admits a fetch only when four operations remain outside
the reserve, which keeps the owned client's release inside the budget.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from ...application.ports.service_qualification import OpenedTransport
from ...application.use_cases.qualify_server_services import (
    IsolationObservation,
    LedgeredTransport,
    QualificationBoundaries,
    RuntimeIdentity,
    qualify_server_services,
)
from ...domain.enterprise.models.service_qualification import (
    ExecutionMode,
    QualificationAuthorization,
    QualificationRequest,
    RefusalKind,
    RefusalSubject,
    RepositoryIdentity,
    StageDefinition,
    refusal,
    stage_definition,
)
from ...domain.enterprise.models.service_run_record import generate_run_id
from ...domain.models.plans import DevicePlan, LinkPlan
from ...infrastructure.catalog.devices import ALL_MODELS
from ...infrastructure.execution.enterprise_configuration_runtime import (
    PacketTracerEnterpriseConfigurationRuntime,
)
from ...infrastructure.execution.enterprise_service_runtime import (
    PacketTracerEnterpriseServiceRuntime,
)
from ...infrastructure.execution.file_bridge import FileBridge
from ...infrastructure.execution.import_isolation_preflight import (
    PRODUCTION_NAMESPACE,
    ImportIsolationPreflight,
    governed_root_from_env,
)
from ...infrastructure.execution.live_bridge import PacketTracerHttpTransport
from ...infrastructure.execution.packet_tracer_physical_runtime import (
    PacketTracerPhysicalTopologyRuntime,
)
from ...infrastructure.execution.service_environment import ServiceEnvironmentReader
from ...infrastructure.execution.service_qualification_probes import (
    PacketTracerQualificationProbes,
)
from ...infrastructure.execution.source_preflight import GitSourceReader
from ...infrastructure.persistence.service_qualification_store import (
    QualificationRecordStore,
)

#: Service runtime timings for a qualification fetch; see the module docstring.
HTTP_TIMEOUT_SECONDS = 8.0
#: Physical runtime timeouts. The finalization time reserve covers them.
MUTATION_TIMEOUT_SECONDS = 15.0
OBSERVATION_TIMEOUT_SECONDS = 10.0
RECORD_DIRECTORY = ("data", "services", "qualification")


def fixture_plans(
    definition: StageDefinition,
) -> tuple[tuple[DevicePlan, ...], tuple[LinkPlan, ...]]:
    """Resolve a stage's fixtures through the device catalog, never by guessing.

    The PTBuilder device type comes from the catalog category, and every link
    port must be a catalogued port of its model. An unknown model or port
    raises `ValueError`, which the coordinator turns into a refusal before any
    contact.
    """
    devices: list[DevicePlan] = []
    ports: dict[str, set[str]] = {}
    for index, fixture in enumerate(definition.fixtures):
        model = ALL_MODELS.get(fixture.model)
        if model is None:
            raise ValueError(f"Fixture model {fixture.model!r} is not catalogued.")
        ports[fixture.name] = {port.full_name for port in model.ports}
        devices.append(
            DevicePlan(
                id=fixture.name,
                name=fixture.name,
                model=model.pt_type,
                category=model.category,
                x=120 + 160 * index,
                y=120,
            )
        )
    links: list[LinkPlan] = []
    for index, link in enumerate(definition.links, start=1):
        for device, port in (
            (link.device_a, link.port_a),
            (link.device_b, link.port_b),
        ):
            if port not in ports.get(device, set()):
                raise ValueError(f"Port {port!r} is not catalogued for {device!r}.")
        links.append(
            LinkPlan(
                id=f"q-link-{index}",
                device_a=link.device_a,
                port_a=link.port_a,
                device_b=link.device_b,
                port_b=link.port_b,
                cable="straight",
            )
        )
    return tuple(devices), tuple(links)


def _repository(governed_root: Path) -> RepositoryIdentity:
    observed = GitSourceReader().read(governed_root)
    errors = "; ".join(
        item
        for item in (
            observed.error,
            observed.dirty_error,
            observed.upstream_head_error,
            observed.source_tree_error,
        )
        if item
    )
    return RepositoryIdentity(
        branch=observed.branch,
        head=observed.head,
        tree=observed.source_tree,
        clean=None if observed.dirty is None else not observed.dirty,
        upstream=observed.upstream,
        upstream_head=observed.upstream_head,
        error=errors,
    )


def _isolation(governed_root: Path) -> IsolationObservation:
    result = ImportIsolationPreflight(governed_root).ensure_isolated()
    return IsolationObservation(result.isolated, result.state.value, result.detail)


def _runtime_identity() -> RuntimeIdentity:
    # Read the loaded package; importing it here would create what we audit.
    package = sys.modules.get(PRODUCTION_NAMESPACE)
    return RuntimeIdentity(
        python_executable=sys.executable,
        package_file=str(getattr(package, "__file__", "") or ""),
    )


def _open_transport(channel: str) -> OpenedTransport:
    if channel == "http":
        transport = PacketTracerHttpTransport()
        live = transport.start(wait_for_connection=True, timeout_seconds=8.0)
        return OpenedTransport(
            channel,
            transport,
            live,
            "webview_polling" if live else "webview_not_polling",
        )
    bridge = FileBridge()
    live = bridge.pt_alive()
    return OpenedTransport(
        channel, bridge, live, "heartbeat_fresh" if live else "heartbeat_stale"
    )


def _close_transport(opened: OpenedTransport) -> None:
    stop = getattr(opened.transport, "stop", None)
    if callable(stop):
        stop()


def _no_inventory() -> list[dict]:
    raise RuntimeError("A qualification runtime never enumerates the workspace.")


def _configuration_runtime(
    bound: LedgeredTransport,
) -> PacketTracerEnterpriseConfigurationRuntime:
    return PacketTracerEnterpriseConfigurationRuntime(
        _no_inventory, bound.send, bound.send_and_wait
    )


def _service_runtime(bound: LedgeredTransport) -> PacketTracerEnterpriseServiceRuntime:
    return PacketTracerEnterpriseServiceRuntime(
        _no_inventory,
        bound.send_and_wait,
        dispatch_and_wait=bound.dispatch_and_wait,
        http_timeout_seconds=HTTP_TIMEOUT_SECONDS,
        convergence_interval_seconds=HTTP_TIMEOUT_SECONDS,
        clock=bound.clock,
        sleeper=bound.capped_sleep,
    )


def production_boundaries(governed_root: Path) -> QualificationBoundaries:
    """Compose the LIVE boundaries; constructing them performs no I/O."""
    return QualificationBoundaries(
        execution_mode=ExecutionMode.LIVE,
        isolation=lambda: _isolation(governed_root),
        runtime_identity=_runtime_identity,
        repository=lambda: _repository(governed_root),
        record_store=QualificationRecordStore(
            governed_root.joinpath(*RECORD_DIRECTORY)
        ),
        open_transport=_open_transport,
        close_transport=_close_transport,
        fixture_plans=fixture_plans,
        build_reader=lambda send_and_wait: ServiceEnvironmentReader(send_and_wait),
        physical_runtime=lambda send_and_wait: PacketTracerPhysicalTopologyRuntime(
            send_and_wait,
            mutation_timeout_seconds=MUTATION_TIMEOUT_SECONDS,
            observation_timeout_seconds=OBSERVATION_TIMEOUT_SECONDS,
        ),
        probes=lambda bound, run_id, nonce: PacketTracerQualificationProbes(
            run_id=run_id,
            nonce=nonce,
            dispatch_and_wait=bound.dispatch_and_wait,
            send=bound.send,
        ),
        configuration_runtime=_configuration_runtime,
        service_runtime=_service_runtime,
        clock=time.monotonic,
        sleep=time.sleep,
        now=lambda: datetime.now(UTC),
        new_run_id=generate_run_id,
        new_nonce=lambda: uuid4().hex,
    )


def _integer(value: str | None) -> Any:
    """Keep a malformed number raw so the domain rule can name it."""
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return value


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--stage", default="")
    parser.add_argument("--expected-head", default="")
    parser.add_argument("--target", action="append", default=[])
    parser.add_argument("--channel", default="")
    parser.add_argument("--packet-tracer-build", default="")
    parser.add_argument("--authorization-id")
    parser.add_argument("--authorized-stage")
    parser.add_argument("--authorized-sha")
    parser.add_argument("--authorized-target", action="append")
    parser.add_argument("--authorized-channel")
    parser.add_argument("--authorized-build")
    parser.add_argument("--authorized-max-operations")
    parser.add_argument("--authorized-max-seconds")
    return parser


def _request(argv: Sequence[str] | None) -> QualificationRequest:
    args = _parser().parse_args(argv)
    named = (
        args.authorization_id,
        args.authorized_stage,
        args.authorized_sha,
        args.authorized_target,
        args.authorized_channel,
        args.authorized_build,
        args.authorized_max_operations,
        args.authorized_max_seconds,
    )
    authorization = None
    if any(item is not None for item in named):
        authorization = QualificationAuthorization(
            authorization_id=args.authorization_id or "",
            stage=args.authorized_stage or "",
            sha=args.authorized_sha or "",
            targets=tuple(args.authorized_target or ()),
            channel=args.authorized_channel or "",
            build=args.authorized_build or "",
            max_operations=_integer(args.authorized_max_operations),
            max_seconds=_integer(args.authorized_max_seconds),
        )
    return QualificationRequest(
        execute=bool(args.execute),
        stage=args.stage,
        expected_head=args.expected_head,
        targets=tuple(args.target),
        channel=args.channel,
        packet_tracer_build=args.packet_tracer_build,
        authorization=authorization,
    )


def _print(payload: Mapping[str, Any]) -> None:
    print(json.dumps(payload, sort_keys=True), flush=True)


def main(
    argv: Sequence[str] | None = None,
    *,
    environ: Mapping[str, str] | None = None,
    boundaries_factory=production_boundaries,
) -> int:
    """Run one stage and return 0 completed, 1 stopped or 2 refused."""
    request = _request(argv)
    if not request.execute:
        _print(
            {
                "outcome": "refused",
                "refusals": [
                    refusal(
                        RefusalKind.MISSING,
                        RefusalSubject.EXECUTION,
                        "--execute is required; nothing was read or contacted.",
                    ).model_dump(mode="json")
                ],
            }
        )
        return 2
    governed_root = governed_root_from_env(environ)
    if governed_root is None:
        _print(
            {
                "outcome": "refused",
                "refusals": [
                    refusal(
                        RefusalKind.MISSING,
                        RefusalSubject.GOVERNED_ROOT,
                        "PT_MCP_GOVERNED_ROOT must declare the governed checkout.",
                    ).model_dump(mode="json")
                ],
            }
        )
        return 2
    definition = stage_definition(request.stage)
    capabilities = (
        frozenset(definition.experimental_capabilities)
        if definition is not None
        else frozenset()
    )
    try:
        result = qualify_server_services(
            request,
            boundaries_factory(governed_root),
            experimental_capabilities=capabilities,
        )
    except KeyboardInterrupt:
        _print({"outcome": "stopped", "primary_failure": "cancelled"})
        return 130
    _print(result.compact_summary())
    return result.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
