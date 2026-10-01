"""Q1: index page tables through both handles, then the HTTP/HTTPS listeners."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ....domain.enterprise.models.service_plan import (
    ServiceEvidenceKind,
    ServiceVerificationExpectation,
    ServiceVerificationKind,
)
from ....domain.enterprise.models.service_qualification import (
    Q1_PC1,
    Q1_SERVER,
    Q1_SERVER_IPV4,
    MeasurementConclusion,
    ReleaseRecord,
)
from ....domain.enterprise.models.service_runtime import RuntimeServiceVerification
from ....domain.enterprise.services.service_qualification_evidence import (
    Assessment,
    assess_https_listener,
    assess_page_tables,
    assess_port_readiness,
    listener_toggle_established,
    marker_page_established,
    page_read_admits_second_write,
    page_write_established,
)
from ..contracts import MAX_DETAIL
from ..execution import Execution
from ..fixtures import (
    await_readiness,
    configure_web_fixture,
    fixture_endpoints,
    setup_fixtures,
)

#: The worst case of one production fetch: start, two inspections, release.
FETCH_OPERATIONS = 4


def run_q1(execution: Execution) -> None:
    """Run the repaired Q1 scope: the page tables, then the listeners.

    M-DNS-3 is declared OMITTED, not scheduled. Its reader was measured by the
    Q1-file run at `0850de3`, nothing in this stage depends on that reading,
    and a second sample would be a second sample attributed to its own SHA --
    never additional support for the first one.
    """
    required = [item.id for item in execution.definition.experiments if item.required]
    if not execution.ledger.can_afford(
        execution.definition.fixture_operations
        + execution.definition.required_experiment_operations
    ):
        execution.not_run(required, "budget_insufficient_for:Q1")
        execution.stop("budget:Q1")
        return
    if not setup_fixtures(execution) or not configure_web_fixture(execution):
        execution.not_run(required, "fixture_setup_failed")
        return
    ids = ("M-HTTPS-1",)
    if execution.begin(ids, "HTTPS1"):
        with execution.procedure(ids):
            execution.conclude("M-HTTPS-1", _page_tables(execution))
        execution.finish("HTTPS1")
    ids = ("M-HTTPS-2",)
    if execution.begin(ids, "HTTPS2"):
        with execution.procedure(ids):
            execution.conclude("M-HTTPS-2", _https_listener(execution))
        execution.finish("HTTPS2")


def _fetch(
    execution: Execution, label: str, scheme: str, marker: str
) -> RuntimeServiceVerification | None:
    """One production fetch, started only when its whole lifecycle fits.

    Four operations: the start, at most two inspections (the production
    runtime polls with an interval equal to its timeout) and the release of
    the owned client, which must never be the call the budget refuses.
    """
    if execution.stopped:
        return None
    if not execution.ledger.can_afford(FETCH_OPERATIONS):
        execution.stop(f"budget:fetch:{label}")
        return None
    expectation = ServiceVerificationExpectation(
        id=f"q1-{label}",
        service_id=f"q1-{scheme}",
        action_id="q1-fixture",
        kind=(
            ServiceVerificationKind.HTTPS_FETCH
            if scheme == "https"
            else ServiceVerificationKind.HTTP_FETCH
        ),
        evidence_kind=ServiceEvidenceKind.BEHAVIORAL,
        host_device_id=Q1_SERVER,
        host_device_name=Q1_SERVER,
        client_device_id=Q1_PC1,
        client_device_name=Q1_PC1,
        expected={"scheme": scheme, "address": Q1_SERVER_IPV4, "marker": marker},
        host_model="Server-PT",
        client_model="PC-PT",
    )
    with execution.ledger.purpose_of(f"fetch:{label}"):
        row = execution.run.boundaries.service_runtime(execution.bound).verify(
            expectation
        )
    released = str(row.observed.get("released", ""))
    execution.record.releases.append(
        ReleaseRecord(
            resource=f"client:{label}",
            kind="client",
            outcome=released or "unknown",
            detail="; ".join(row.limitations)[:MAX_DETAIL],
        )
    )
    if released not in ("released", "nothing_owned"):
        execution.record.engine_residue.append(
            f"client:{label}:{released or 'unknown'}"
        )
        # An owned client whose release nobody observed is an effect with an
        # unknown outcome. It authorizes no further experimental mutation.
        execution.stop(f"outcome_unknown:fetch_client:{label}")
    return row


def _page_tables(execution: Execution) -> Assessment:
    """Write the existing index page through each handle, reading between.

    Four evaluations, each admitted only after the previous one was
    interpreted: write H through `HttpServer` (bracketed by a complete read of
    both handles), an independent read of both, write S through
    `HttpsServer` (bracketed again), and a final independent read. Nothing is
    written under a new page name, and a step that could not be read stops
    the procedure rather than guessing.
    """
    probes = execution.probes
    texts = probes.page_marker_texts()
    write_http = probes.write_index_marker(Q1_SERVER, "http")
    read_http = write_https = read_https = None
    if page_write_established(write_http):
        read_http = probes.read_index_cells(Q1_SERVER)
    if page_read_admits_second_write(read_http, texts["http_marker"]):
        write_https = probes.write_index_marker(Q1_SERVER, "https")
    if page_write_established(write_https):
        read_https = probes.read_index_cells(Q1_SERVER)
    return assess_page_tables(
        write_http,
        read_http,
        write_https,
        read_https,
        http_marker=texts["http_marker"],
        https_marker=texts["https_marker"],
    )


def _https_listener(execution: Execution) -> Assessment:
    """Run the listener procedure, admitting each effect only after the last one.

    Nothing reaches the network before the bounded readiness gate reports one
    fresh complete sample in which every fixture link is up. A gate that never
    becomes ready leaves the marked page unwritten and every fetch unstarted:
    that is a readiness result about the measured links, never evidence that
    HTTP or HTTPS is broken.

    A same-mode working positive then comes before every negative: an
    HTTP-mode fetch with both listeners enabled, then HTTP off and an
    HTTPS-mode fetch. A negative whose positive did not retrieve the marker is
    not run, because it could not discriminate anything; a failed positive
    instead spends one read of listener and endpoint readiness, so the record
    says what the fixture looked like when it failed. No wait, timeout or
    status-code meaning is added to force a positive, and a started fetch is
    never retried inside this experiment.
    """
    probes = execution.probes
    marker = f"MCPQ-{execution.nonce[:16]}-INDEX"
    endpoints = fixture_endpoints(execution)
    urls = {scheme: f"{scheme}://{Q1_SERVER_IPV4}/" for scheme in ("http", "https")}
    gate = await_readiness(
        execution,
        endpoints,
        lambda timeout: probes.read_listener_readiness(Q1_SERVER, endpoints, timeout),
        purpose="readiness:q1_fixture_links",
    )
    steps: dict[str, Any] = {
        "readiness": gate.facts(),
        "marker_page": None,
        "http_positive": None,
        "http_off": None,
        "https_positive": None,
        "http_negative": None,
        "https_off": None,
        "https_negative": None,
    }

    def assessed(readiness_after: Mapping[str, Any] | None = None) -> Assessment:
        return assess_https_listener(
            **steps, request_urls=urls, readiness_after=readiness_after
        )

    def failed_positive() -> Assessment:
        if execution.stopped or not execution.ledger.can_afford(1):
            return assessed()
        with execution.ledger.purpose_of("readiness:q1_after_failed_positive"):
            reading = probes.read_listener_readiness(Q1_SERVER, endpoints)
        return assessed(dict(assess_port_readiness(reading, endpoints).facts))

    if execution.stopped or not gate.ready:
        return assessed()
    steps["marker_page"] = probes.prepare_marker_page(Q1_SERVER, marker)
    if not marker_page_established(steps["marker_page"]):
        return assessed()
    steps["http_positive"] = _fetch(execution, "http-positive", "http", marker)
    current = assessed()
    if execution.stopped or current.conclusion is MeasurementConclusion.CONTRADICTED:
        return current
    if current.facts["positive_http_mode_both_enabled"]["fetch"] != "marker_retrieved":
        return failed_positive()
    steps["http_off"] = probes.disable_http(Q1_SERVER)
    if not listener_toggle_established(steps["http_off"], http=False, https=True):
        return assessed()
    steps["https_positive"] = _fetch(execution, "https-positive", "https", marker)
    current = assessed()
    if execution.stopped or current.conclusion is MeasurementConclusion.CONTRADICTED:
        return current
    https_worked = current.facts["positive_https_only"]["fetch"] == "marker_retrieved"
    steps["http_negative"] = _fetch(execution, "http-negative", "http", marker)
    current = assessed()
    if execution.stopped or current.conclusion is MeasurementConclusion.CONTRADICTED:
        return current
    if not https_worked:
        return failed_positive()
    if not execution.ledger.can_afford(1 + FETCH_OPERATIONS):
        execution.stop("budget:https_negative")
        return assessed()
    steps["https_off"] = probes.disable_https(Q1_SERVER)
    if listener_toggle_established(steps["https_off"], http=False, https=False):
        steps["https_negative"] = _fetch(execution, "https-negative", "https", marker)
    return assessed()
