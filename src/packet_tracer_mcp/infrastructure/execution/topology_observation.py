"""Typed runtime observations for Packet Tracer links and layout.

The MCP adapter contains many tool closures, which makes local helpers hard to
exercise without starting an MCP server.  This module keeps the evidence rules
pure and importable: mutation acknowledgement never counts as topology proof,
and visual placement is compared with an explicit tolerance.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from enum import Enum
import json
import time
from typing import Callable


class LinkObservationStatus(str, Enum):
    """Outcome of an exact two-ended link read-back."""

    EXACT = "EXACT"
    DEVICE_MISSING = "DEVICE_MISSING"
    PORT_MISSING = "PORT_MISSING"
    NO_LINK = "NO_LINK"
    ENDPOINT_MISMATCH = "ENDPOINT_MISMATCH"
    MALFORMED_RESPONSE = "MALFORMED_RESPONSE"
    TIMEOUT = "TIMEOUT"


@dataclass(frozen=True)
class LinkEndpoint:
    device: str
    port: str


@dataclass(frozen=True)
class LinkExpectation:
    endpoint_a: LinkEndpoint
    endpoint_b: LinkEndpoint


@dataclass(frozen=True)
class LinkReadback:
    status: LinkObservationStatus
    exact: bool
    port_a_bound: bool = False
    port_b_bound: bool = False
    both_ports_bound: bool = False
    same_link: bool = False
    observed_link_a: tuple[LinkEndpoint, ...] = ()
    observed_link_b: tuple[LinkEndpoint, ...] = ()
    link_class_a: str = ""
    link_class_b: str = ""
    detail: str = ""


@dataclass(frozen=True)
class LinkConvergenceResult:
    verified: bool
    attempts: int
    elapsed_seconds: float
    observation: LinkReadback


def build_exact_link_readback_js(expectation: LinkExpectation) -> str:
    """Build read-only JS that proves the exact peer at both requested ports.

    Every caller-controlled field is serialized with :func:`json.dumps`.  The
    script only uses Packet Tracer APIs already exercised elsewhere in this
    repository: getPort/getLink/getPort1/getPort2/getOwnerDevice/getName and
    getClassName.
    """

    device_a = json.dumps(expectation.endpoint_a.device, ensure_ascii=False)
    port_a = json.dumps(expectation.endpoint_a.port, ensure_ascii=False)
    device_b = json.dumps(expectation.endpoint_b.device, ensure_ascii=False)
    port_b = json.dumps(expectation.endpoint_b.port, ensure_ascii=False)
    return (
        "try{(function(){"
        "var __ed1=" + device_a + ",__ep1=" + port_a + ";"
        "var __ed2=" + device_b + ",__ep2=" + port_b + ";"
        "var __o={exact:false,port_a_bound:false,port_b_bound:false,"
        "both_ports_bound:false,same_link:false,"
        "reason:'',link_class_a:'',link_class_b:'',"
        "observed_link_a:[],observed_link_b:[]};"
        "function __emit(){reportResult(JSON.stringify(__o));}"
        "function __endpoint(__p){return {device:String(__p.getOwnerDevice().getName()),"
        "port:String(__p.getName())};}"
        "function __ends(__l){return [__endpoint(__l.getPort1()),__endpoint(__l.getPort2())];}"
        "function __matches(__e){var __f=(__e[0].device===__ed1&&__e[0].port===__ep1&&"
        "__e[1].device===__ed2&&__e[1].port===__ep2);"
        "var __r=(__e[1].device===__ed1&&__e[1].port===__ep1&&"
        "__e[0].device===__ed2&&__e[0].port===__ep2);return __f||__r;}"
        "var __n=ipc.network();var __d1=__n.getDevice(__ed1);var __d2=__n.getDevice(__ed2);"
        "if(!__d1||!__d2){__o.reason='DEVICE_MISSING';__emit();return;}"
        "var __p1=__d1.getPort(__ep1);var __p2=__d2.getPort(__ep2);"
        "if(!__p1||!__p2){__o.reason='PORT_MISSING';__emit();return;}"
        "var __l1=__p1.getLink();var __l2=__p2.getLink();"
        "__o.port_a_bound=!!__l1;__o.port_b_bound=!!__l2;"
        "if(!__l1||!__l2){__o.reason='NO_LINK';__emit();return;}"
        # Dos `getLink()` sobre el mismo enlace devuelven proxies IPC distintos,
        # asi que `===` es false incluso cuando el enlace es el mismo. Medido en
        # PT 9.0.1.0858: `getObjectUuid()` si coincide. Se compara la identidad
        # declarada y solo se cae en `===` si el getter no existe.
        "__o.both_ports_bound=true;"
        "__o.same_link=(function(){try{var __ua=String(__l1.getObjectUuid());"
        "var __ub=String(__l2.getObjectUuid());"
        "if(__ua&&__ub){return __ua===__ub;}}catch(__ue){}return __l1===__l2;})();"
        "__o.link_class_a=String(__l1.getClassName());"
        "__o.link_class_b=String(__l2.getClassName());"
        "__o.observed_link_a=__ends(__l1);__o.observed_link_b=__ends(__l2);"
        "__o.exact=__o.same_link&&__matches(__o.observed_link_a)&&"
        "__matches(__o.observed_link_b);"
        "__o.reason=__o.exact?'EXACT':'ENDPOINT_MISMATCH';__emit();"
        "})();}catch(__e){reportResult(JSON.stringify({exact:false,reason:'MALFORMED_RESPONSE',"
        "detail:String(__e)}));}"
    )


def _parse_endpoints(value: object) -> tuple[LinkEndpoint, ...]:
    if not isinstance(value, list):
        return ()
    parsed: list[LinkEndpoint] = []
    for item in value:
        if not isinstance(item, dict):
            return ()
        device = item.get("device")
        port = item.get("port")
        if not isinstance(device, str) or not isinstance(port, str):
            return ()
        parsed.append(LinkEndpoint(device=device, port=port))
    return tuple(parsed)


def parse_exact_link_readback(raw: str | None) -> LinkReadback:
    """Parse the compact payload emitted by ``build_exact_link_readback_js``."""

    if raw is None:
        return LinkReadback(status=LinkObservationStatus.TIMEOUT, exact=False)
    try:
        payload = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return LinkReadback(
            status=LinkObservationStatus.MALFORMED_RESPONSE,
            exact=False,
            detail=str(raw)[:200],
        )
    if not isinstance(payload, dict):
        return LinkReadback(
            status=LinkObservationStatus.MALFORMED_RESPONSE,
            exact=False,
            detail=str(raw)[:200],
        )
    reason = str(payload.get("reason") or "MALFORMED_RESPONSE")
    try:
        status = LinkObservationStatus(reason)
    except ValueError:
        status = LinkObservationStatus.MALFORMED_RESPONSE
    observed_a = _parse_endpoints(payload.get("observed_link_a"))
    observed_b = _parse_endpoints(payload.get("observed_link_b"))
    exact = (
        payload.get("exact") is True
        and status is LinkObservationStatus.EXACT
        and payload.get("both_ports_bound") is True
        and payload.get("same_link") is True
        and len(observed_a) == 2
        and len(observed_b) == 2
    )
    if status is LinkObservationStatus.EXACT and not exact:
        status = LinkObservationStatus.ENDPOINT_MISMATCH
    return LinkReadback(
        status=status,
        exact=exact,
        port_a_bound=payload.get("port_a_bound") is True,
        port_b_bound=payload.get("port_b_bound") is True,
        both_ports_bound=payload.get("both_ports_bound") is True,
        same_link=payload.get("same_link") is True,
        observed_link_a=observed_a,
        observed_link_b=observed_b,
        link_class_a=str(payload.get("link_class_a") or "")[:100],
        link_class_b=str(payload.get("link_class_b") or "")[:100],
        detail=str(payload.get("detail") or "")[:200],
    )


def verify_exact_link_convergence(
    send_and_wait: Callable[[str, float], str | None],
    expectation: LinkExpectation,
    *,
    timeout_seconds: float = 4.0,
    poll_interval_seconds: float = 0.15,
    clock: Callable[[], float] = time.monotonic,
    sleeper: Callable[[float], None] = time.sleep,
) -> LinkConvergenceResult:
    """Poll exact two-ended read-back until success or a bounded deadline."""

    timeout_seconds = max(0.01, float(timeout_seconds))
    poll_interval_seconds = max(0.01, float(poll_interval_seconds))
    started = clock()
    deadline = started + timeout_seconds
    attempts = 0
    observation = LinkReadback(status=LinkObservationStatus.TIMEOUT, exact=False)
    script = build_exact_link_readback_js(expectation)

    while True:
        remaining = max(0.01, deadline - clock())
        attempts += 1
        observation = parse_exact_link_readback(
            send_and_wait(script, min(1.0, remaining))
        )
        expected = {
            (expectation.endpoint_a.device, expectation.endpoint_a.port),
            (expectation.endpoint_b.device, expectation.endpoint_b.port),
        }
        observed_a = {(item.device, item.port) for item in observation.observed_link_a}
        observed_b = {(item.device, item.port) for item in observation.observed_link_b}
        if observation.exact and (observed_a != expected or observed_b != expected):
            observation = replace(
                observation,
                status=LinkObservationStatus.ENDPOINT_MISMATCH,
                exact=False,
                detail="read-back payload did not match the requested endpoint pair",
            )
        if observation.exact:
            return LinkConvergenceResult(
                verified=True,
                attempts=attempts,
                elapsed_seconds=max(0.0, clock() - started),
                observation=observation,
            )
        remaining = deadline - clock()
        if remaining <= 0:
            break
        sleeper(min(poll_interval_seconds, remaining))

    return LinkConvergenceResult(
        verified=False,
        attempts=attempts,
        elapsed_seconds=max(0.0, clock() - started),
        observation=observation,
    )


class LayoutApplicationStatus(str, Enum):
    REQUESTED = "REQUESTED"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    OBSERVED = "OBSERVED"
    DRIFTED = "DRIFTED"


@dataclass(frozen=True)
class LayoutPoint:
    x: int
    y: int


@dataclass(frozen=True)
class LayoutDrift:
    x: int
    y: int

    @property
    def maximum_axis(self) -> int:
        return max(abs(self.x), abs(self.y))


@dataclass(frozen=True)
class LayoutApplicationEvidence:
    requested: LayoutPoint
    acknowledged: bool
    observed: LayoutPoint | None
    tolerance: int
    drift: LayoutDrift | None
    within_tolerance: bool | None
    status: LayoutApplicationStatus

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def assess_layout_application(
    requested: LayoutPoint,
    *,
    acknowledged: bool,
    observed: LayoutPoint | None,
    tolerance: int,
) -> LayoutApplicationEvidence:
    """Separate requested, acknowledged and observed placement evidence."""

    tolerance = max(0, int(tolerance))
    if not acknowledged:
        return LayoutApplicationEvidence(
            requested=requested,
            acknowledged=False,
            observed=observed,
            tolerance=tolerance,
            drift=None,
            within_tolerance=None,
            status=LayoutApplicationStatus.REQUESTED,
        )
    if observed is None:
        return LayoutApplicationEvidence(
            requested=requested,
            acknowledged=True,
            observed=None,
            tolerance=tolerance,
            drift=None,
            within_tolerance=None,
            status=LayoutApplicationStatus.ACKNOWLEDGED,
        )
    drift = LayoutDrift(x=observed.x - requested.x, y=observed.y - requested.y)
    within = drift.maximum_axis <= tolerance
    return LayoutApplicationEvidence(
        requested=requested,
        acknowledged=True,
        observed=observed,
        tolerance=tolerance,
        drift=drift,
        within_tolerance=within,
        status=(
            LayoutApplicationStatus.OBSERVED
            if within
            else LayoutApplicationStatus.DRIFTED
        ),
    )


def build_layout_observation_js(device_name: str) -> str:
    """Build the read-only coordinate query already supported by PT exports."""

    device = json.dumps(device_name, ensure_ascii=False)
    return (
        "try{var __d=ipc.network().getDevice(" + device + ");"
        "if(!__d){reportResult(JSON.stringify({found:false,supported:true}));}"
        "else if(typeof __d.getXCoordinate!=='function'||"
        "typeof __d.getYCoordinate!=='function'){"
        "reportResult(JSON.stringify({found:true,supported:false}));}"
        "else{reportResult(JSON.stringify({found:true,supported:true,"
        "x:Number(__d.getXCoordinate()),y:Number(__d.getYCoordinate())}));}}"
        "catch(__e){reportResult(JSON.stringify({found:false,supported:false,"
        "error:String(__e)}));}"
    )


def parse_layout_observation(raw: str | None) -> LayoutPoint | None:
    if raw is None:
        return None
    try:
        payload = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    if payload.get("found") is not True or payload.get("supported") is not True:
        return None
    x = payload.get("x")
    y = payload.get("y")
    if not isinstance(x, (int, float)) or not isinstance(y, (int, float)):
        return None
    return LayoutPoint(x=round(x), y=round(y))
