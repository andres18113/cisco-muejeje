"""Capacidades E6 observadas en los procesos de Server-PT.

La matriz describe canales independientes. En particular, que TftpServer pueda
habilitarse no demuestra que la Extensions API permita publicar un archivo.

The table is written out record by record, on purpose. The previous form built
every profile with a comprehension over `ServiceType` and then demoted the few
dimensions that were not supported, which meant a service family added later
arrived SUPPORTED by default and a build nobody had ever measured inherited the
one measured build's answers. Evidence does not work that way: a record exists
because something was read or observed, so every record here names what it is
and where it came from, and a version with no evidence produces UNKNOWN for
every dimension rather than the baseline's table under a different label.

Provenance is part of each record. The baseline DNS/HTTP records retain their
`documentary_baseline` source. The native Server-PT DHCP binding alone is a
scoped `recorded_run` entry backed by the archived e8-e10 owned-lab episodes.
Its policy and action/verification resolution remain bounded independently of
the generic DHCP profile, which stays UNKNOWN.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping

from ...domain.enterprise.models.capabilities import CapabilityStatus
from ...domain.enterprise.models.configuration import AddressRange
from ...domain.enterprise.models.evidence import CapabilityReadiness, ReadinessStatus
from ...domain.enterprise.models.service_plan import (
    CapabilityProvenance,
    ClientOperationCapability,
    NativeDhcpPolicyScope,
    ServiceActionType,
    ServiceCapabilityProfile,
    ServiceCapabilityRecords,
    ServiceType,
    ServiceVerificationKind,
)

#: The one build any dimension below was measured or documented against.
BASELINE_PACKET_TRACER_VERSION = "9.0.1.0858"

_BASELINE_SOURCE = "PT 9.0.1 local IpcAPI reference and controlled process probes"
_SERVER_MODEL = "Server-PT"
_CLIENT_MODEL = "PC-PT"


class ServiceCapabilityCatalogError(ValueError):
    """Raised when the capability records contradict each other."""


def _readiness(
    capability: str,
    *,
    verify: ReadinessStatus,
    apply_status: ReadinessStatus = ReadinessStatus.READY,
    reason: str = "",
) -> CapabilityReadiness:
    return CapabilityReadiness(
        capability=capability,
        compile=ReadinessStatus.READY,
        apply=apply_status,
        verify=verify,
        reasons={"verify": [reason]} if reason else {},
    )


def _profile(
    service_type: ServiceType,
    *,
    version: str,
    application: CapabilityStatus,
    direct_readback: CapabilityStatus,
    behavioral: CapabilityStatus,
    actions: dict[str, CapabilityStatus] | None = None,
    readiness: CapabilityReadiness | None = None,
) -> ServiceCapabilityProfile:
    return ServiceCapabilityProfile(
        service_type=service_type,
        compile_support=CapabilityStatus.SUPPORTED,
        application_support=application,
        action_application_support=dict(actions or {}),
        direct_readback_support=direct_readback,
        behavioral_verification_support=behavioral,
        source=_BASELINE_SOURCE,
        packet_tracer_version=version,
        capability_readiness=(
            {"behavioral_verification": readiness} if readiness is not None else {}
        ),
        provenance=CapabilityProvenance.DOCUMENTARY_BASELINE,
    )


def _operation(
    model: str,
    operation: str,
    support: CapabilityStatus,
    *,
    version: str,
    source: str = _BASELINE_SOURCE,
) -> ClientOperationCapability:
    return ClientOperationCapability(
        key=f"{model}:{operation}",
        model=model,
        operation=operation,
        support=support,
        provenance=CapabilityProvenance.DOCUMENTARY_BASELINE,
        source=source,
        packet_tracer_version=version,
    )


def _baseline_profiles(version: str) -> list[ServiceCapabilityProfile]:
    """Return the five server families with every dimension stated."""
    return [
        _profile(
            ServiceType.DNS,
            version=version,
            application=CapabilityStatus.SUPPORTED,
            direct_readback=CapabilityStatus.SUPPORTED,
            behavioral=CapabilityStatus.SUPPORTED,
            readiness=_readiness(
                "dns_behavioral_verification", verify=ReadinessStatus.READY
            ),
        ),
        _profile(
            ServiceType.HTTP,
            version=version,
            application=CapabilityStatus.SUPPORTED,
            direct_readback=CapabilityStatus.SUPPORTED,
            behavioral=CapabilityStatus.SUPPORTED,
            readiness=_readiness(
                "http_behavioral_verification", verify=ReadinessStatus.READY
            ),
        ),
        _profile(
            ServiceType.HTTPS,
            version=version,
            application=CapabilityStatus.SUPPORTED,
            direct_readback=CapabilityStatus.SUPPORTED,
            behavioral=CapabilityStatus.UNKNOWN,
            readiness=_readiness(
                "https_behavioral_verification",
                verify=ReadinessStatus.UNKNOWN,
                apply_status=ReadinessStatus.PARTIAL,
                reason=(
                    "A typed HTTPS URL is compiled, but PT 9.0.1 client behavior "
                    "has not been live verified."
                ),
            ),
        ),
        _profile(
            ServiceType.NTP,
            version=version,
            application=CapabilityStatus.SUPPORTED,
            direct_readback=CapabilityStatus.SUPPORTED,
            behavioral=CapabilityStatus.UNKNOWN,
            readiness=_readiness(
                "ntp_behavioral_verification",
                verify=ReadinessStatus.UNOBSERVABLE,
                apply_status=ReadinessStatus.PARTIAL,
                reason=(
                    "Packet Tracer exposes activation but no independent "
                    "registered synchronization observation."
                ),
            ),
        ),
        _profile(
            ServiceType.TFTP,
            version=version,
            application=CapabilityStatus.SUPPORTED,
            direct_readback=CapabilityStatus.SUPPORTED,
            behavioral=CapabilityStatus.UNKNOWN,
            actions={
                ServiceActionType.ENABLE_TFTP.value: CapabilityStatus.SUPPORTED,
                ServiceActionType.PUBLISH_TFTP_FILE.value: CapabilityStatus.UNKNOWN,
            },
            readiness=_readiness(
                "tftp_behavioral_verification",
                verify=ReadinessStatus.UNOBSERVABLE,
                apply_status=ReadinessStatus.PARTIAL,
                reason=(
                    "Packet Tracer exposes service activation but no safe "
                    "registered publication/retrieval observation."
                ),
            ),
        ),
    ]


#: Why every S2 mail record is UNKNOWN on the measured build.
_MAIL_UNKNOWN_SOURCE = (
    "no recorded mail evidence; R-EVT-05 fallback (no safe zero-event release "
    "on either channel at 0850de3), Q2 not run"
)


def _mail_profiles(version: str) -> list[ServiceCapabilityProfile]:
    """SMTP and POP3 on the server: documented, not measured, so UNKNOWN."""
    unknown = CapabilityStatus.UNKNOWN
    readiness = _readiness(
        "mail_behavioral_verification",
        verify=ReadinessStatus.UNKNOWN,
        apply_status=ReadinessStatus.UNKNOWN,
        reason=(
            "Mailbox presence is supporting evidence only; send and retrieval "
            "events are gated until a safe zero-event release is established."
        ),
    )
    return [
        ServiceCapabilityProfile(
            service_type=service_type,
            compile_support=CapabilityStatus.SUPPORTED,
            application_support=unknown,
            action_application_support={item.value: unknown for item in actions},
            direct_readback_support=unknown,
            behavioral_verification_support=unknown,
            source=_MAIL_UNKNOWN_SOURCE,
            packet_tracer_version=version,
            capability_readiness={"behavioral_verification": readiness},
            provenance=CapabilityProvenance.DOCUMENTARY_BASELINE,
        )
        for service_type, actions in (
            (
                ServiceType.SMTP,
                (
                    ServiceActionType.ENABLE_SMTP,
                    ServiceActionType.ENSURE_EMAIL_ACCOUNT,
                ),
            ),
            (ServiceType.POP3, (ServiceActionType.ENABLE_POP3,)),
        )
    ]


def _mail_operations(version: str) -> list[ClientOperationCapability]:
    """Every S2 operation on the model that performs it, each UNKNOWN."""
    return [
        _operation(
            model,
            operation.value,
            CapabilityStatus.UNKNOWN,
            version=version,
            source=_MAIL_UNKNOWN_SOURCE,
        )
        for model, operation in (
            (_CLIENT_MODEL, ServiceActionType.CONFIGURE_EMAIL_CLIENT),
            (_CLIENT_MODEL, ServiceActionType.SEND_MAIL_MESSAGE),
            (_CLIENT_MODEL, ServiceVerificationKind.EMAIL_CLIENT_STATE),
            (_CLIENT_MODEL, ServiceVerificationKind.SMTP_SEND),
            (_CLIENT_MODEL, ServiceVerificationKind.POP3_RETRIEVE),
            (_CLIENT_MODEL, ServiceVerificationKind.EMAIL_END_TO_END),
            (_SERVER_MODEL, ServiceVerificationKind.SMTP_DELIVERED),
        )
    ]


_DHCP_UNKNOWN_SOURCE = (
    "documented DHCP members only; M-DHCP-1..6 and Q3 not run, R-EVT-05 "
    "permits read-back at most UNKNOWN"
)


def _dhcp_profiles(version: str) -> list[ServiceCapabilityProfile]:
    """Server-PT DHCP is a complete but entirely UNKNOWN product profile."""
    unknown = CapabilityStatus.UNKNOWN
    return [
        ServiceCapabilityProfile(
            service_type=ServiceType.DHCP,
            compile_support=CapabilityStatus.SUPPORTED,
            application_support=unknown,
            action_application_support={
                ServiceActionType.ENABLE_SERVER_DHCP.value: unknown,
                ServiceActionType.CONFIGURE_SERVER_DHCP_POOL.value: unknown,
            },
            direct_readback_support=unknown,
            behavioral_verification_support=unknown,
            source=_DHCP_UNKNOWN_SOURCE,
            packet_tracer_version=version,
            capability_readiness={
                "behavioral_verification": _readiness(
                    "dhcp_behavioral_verification",
                    verify=ReadinessStatus.UNKNOWN,
                    apply_status=ReadinessStatus.UNKNOWN,
                    reason="Acquisition and lease-table end conditions require Q3.",
                )
            },
            provenance=CapabilityProvenance.DOCUMENTARY_BASELINE,
        )
    ]


def _dhcp_operations(version: str) -> list[ClientOperationCapability]:
    """Keep acquisition UNKNOWN while recording measured client mode reads."""
    unknown = [
        _operation(
            model,
            operation.value,
            CapabilityStatus.UNKNOWN,
            version=version,
            source=_DHCP_UNKNOWN_SOURCE,
        )
        for model, operation in (
            (_CLIENT_MODEL, ServiceActionType.ACQUIRE_DHCP_LEASE),
            (_CLIENT_MODEL, ServiceVerificationKind.DHCP_LEASE),
            (_SERVER_MODEL, ServiceVerificationKind.DHCP_SERVER_STATE),
            (_SERVER_MODEL, ServiceVerificationKind.DHCP_LEASE_ATTRIBUTED),
        )
    ]
    return [
        *unknown,
        ClientOperationCapability(
            key="PC-PT:endpoint_dhcp_mode",
            model="PC-PT",
            operation=ServiceVerificationKind.ENDPOINT_DHCP_MODE.value,
            support=CapabilityStatus.SUPPORTED,
            provenance=CapabilityProvenance.RECORDED_RUN,
            source="SERVER-PT-DHCP-AUTONOMOUS-02/e8,e9,e10 client mode readback",
            packet_tracer_version=version,
            build=version,
            executed_sha="e8c810192b44d75340ffa6ad81c16473eb060fd2",
            transport="file",
            run_id="2026-09-26T13-08-43Z-a18db0b4",
        ),
    ]


def _native_dhcp_binding(version: str) -> ClientOperationCapability:
    """Bind the exact-build native strategy to the measured policy family."""
    return ClientOperationCapability(
        key="Server-PT:dhcp_native_default_binding",
        model="Server-PT",
        operation="dhcp_native_default_binding",
        support=CapabilityStatus.SUPPORTED,
        provenance=CapabilityProvenance.RECORDED_RUN,
        source=(
            "SERVER-PT-DHCP-AUTONOMOUS-02/e8,e9,e10: native physical pool, "
            "capacity one/two, two distinct requested allocation starts, "
            "attributed clients and cold HTTP; exact policy readback required"
        ),
        packet_tracer_version=version,
        build=version,
        executed_sha="e8c810192b44d75340ffa6ad81c16473eb060fd2",
        transport="file",
        run_id="2026-09-26T13-08-43Z-a18db0b4",
        native_policy_scope=NativeDhcpPolicyScope(
            network="192.0.2.0",
            netmask="255.255.255.0",
            server_address="192.0.2.10",
            gateway="192.0.2.1",
            dns_server="192.0.2.10",
            first_lease="192.0.2.100",
            latest_start="192.0.2.151",
            last_lease="192.0.2.152",
            max_users=2,
            max_exclusion_ranges=2,
            excluded_ranges=[
                AddressRange(start="192.0.2.1", end="192.0.2.1"),
                AddressRange(start="192.0.2.10", end="192.0.2.10"),
            ],
        ),
    )


def _baseline_client_operations(version: str) -> list[ClientOperationCapability]:
    """Client-side verification, keyed by the model that performs it."""
    supported = (
        ServiceVerificationKind.DNS_RESOLUTION,
        ServiceVerificationKind.DNS_NEGATIVE_CONTROL,
        ServiceVerificationKind.HTTP_FETCH,
        ServiceVerificationKind.HTTP_BY_HOSTNAME,
    )
    unknown = (
        # No live evidence for a PC-PT HTTPS fetch; HTTPS ownership is Q1.
        ServiceVerificationKind.HTTPS_FETCH,
        # A new reader with no evidence at all. It must not inherit support
        # from another getter on the same client, and it stays advisory until
        # M-DNS-3 records it.
        ServiceVerificationKind.CLIENT_DNS_SERVER,
        ServiceVerificationKind.NTP_SYNC,
        ServiceVerificationKind.TFTP_RETRIEVE,
    )
    return [
        *(
            _operation(
                _CLIENT_MODEL, kind.value, CapabilityStatus.SUPPORTED, version=version
            )
            for kind in supported
        ),
        *(
            _operation(
                _CLIENT_MODEL,
                kind.value,
                CapabilityStatus.UNKNOWN,
                version=version,
                source=f"no recorded client evidence for {_CLIENT_MODEL}:{kind.value}",
            )
            for kind in unknown
        ),
    ]


def _unknown_records(version: str) -> list[object]:
    """Every dimension UNKNOWN, for a build nothing was measured against."""
    source = f"no recorded evidence for {version}"
    profiles = [
        ServiceCapabilityProfile(
            service_type=service_type,
            compile_support=CapabilityStatus.UNKNOWN,
            application_support=CapabilityStatus.UNKNOWN,
            action_application_support={
                action_type.value: CapabilityStatus.UNKNOWN
                for action_type in ServiceActionType
            },
            direct_readback_support=CapabilityStatus.UNKNOWN,
            behavioral_verification_support=CapabilityStatus.UNKNOWN,
            source=source,
            packet_tracer_version=version,
            provenance=CapabilityProvenance.DOCUMENTARY_BASELINE,
        )
        for service_type in ServiceType
    ]
    operations = [
        ClientOperationCapability(
            key=f"{_CLIENT_MODEL}:{kind.value}",
            model=_CLIENT_MODEL,
            operation=kind.value,
            support=CapabilityStatus.UNKNOWN,
            provenance=CapabilityProvenance.DOCUMENTARY_BASELINE,
            source=source,
            packet_tracer_version=version,
        )
        for kind in ServiceVerificationKind
    ]
    # The measured build's operation keys that are not client kinds (mail
    # actions and the server-performed mailbox scan) answer UNKNOWN too, so an
    # unmeasured build never lacks a record the baseline has.
    known = {item.key for item in operations}
    operations.extend(
        item.model_copy(update={"source": source})
        for item in [*_mail_operations(version), *_dhcp_operations(version)]
        if item.key not in known
    )
    operations.append(
        ClientOperationCapability(
            key="Server-PT:dhcp_native_default_binding",
            model="Server-PT",
            operation="dhcp_native_default_binding",
            support=CapabilityStatus.UNKNOWN,
            source=source,
            packet_tracer_version=version,
        )
    )
    return [*profiles, *operations]


def _validate(records: list[object], version: str) -> None:
    """Fail closed on duplicate, contradictory or mis-versioned records.

    Validation runs over the LIST, before it becomes a dictionary, because a
    dictionary silently keeps the last of two records that disagree. That is
    the one failure mode a catalog must not have.
    """
    seen: dict[str, object] = {}
    for record in records:
        key = (
            record.key
            if isinstance(record, ClientOperationCapability)
            else f"{_SERVER_MODEL}:{record.service_type.value}"
        )
        if key in seen:
            raise ServiceCapabilityCatalogError(
                f"Duplicate capability record for {key!r}; a catalog may not "
                "hold two answers for one operation."
            )
        seen[key] = record
        declared = record.packet_tracer_version
        if declared != version:
            raise ServiceCapabilityCatalogError(
                f"Capability record {key!r} declares version {declared!r}, not "
                f"{version!r}; one snapshot describes one build."
            )
        if isinstance(record, ServiceCapabilityProfile):
            readiness = record.capability_readiness.get("behavioral_verification")
            behavioral_supported = (
                record.behavioral_verification_support is CapabilityStatus.SUPPORTED
            )
            if behavioral_supported and (
                readiness is None or readiness.verify is not ReadinessStatus.READY
            ):
                raise ServiceCapabilityCatalogError(
                    f"Capability record {key!r} claims behavioural support while "
                    "its readiness does not say the verification is ready."
                )
        elif record.provenance is CapabilityProvenance.RECORDED_RUN and not (
            record.build and record.executed_sha and record.run_id
        ):
            raise ServiceCapabilityCatalogError(
                f"Capability record {key!r} claims a recorded run without the "
                "build, executed SHA and run identity that attribute it."
            )


def packet_tracer_service_capabilities(
    packet_tracer_version: str = BASELINE_PACKET_TRACER_VERSION,
) -> ServiceCapabilityRecords:
    """Return the capability records for one exact Packet Tracer build.

    Only `BASELINE_PACKET_TRACER_VERSION` has evidence. Every other build gets
    a complete table in which every dimension is UNKNOWN and every source says
    so, because "we have no record of this build" is an answer and an absence
    that a caller could read as permission is not.
    """
    version = packet_tracer_version or BASELINE_PACKET_TRACER_VERSION
    if version == BASELINE_PACKET_TRACER_VERSION:
        records: list[object] = [
            *_baseline_profiles(version),
            *_mail_profiles(version),
            *_dhcp_profiles(version),
            *_baseline_client_operations(version),
            *_mail_operations(version),
            *_dhcp_operations(version),
            _native_dhcp_binding(version),
        ]
    else:
        records = _unknown_records(version)
    _validate(records, version)
    resolved: ServiceCapabilityRecords = {}
    for record in records:
        key = (
            record.key
            if isinstance(record, ClientOperationCapability)
            else f"{_SERVER_MODEL}:{record.service_type.value}"
        )
        resolved[key] = record
    return resolved


def capability_snapshot_hash(records: Mapping[str, object]) -> str:
    """Digest the exact records a run resolved, so a record can name them."""
    payload = {
        key: record.model_dump(mode="json")
        for key, record in sorted(records.items())
        if hasattr(record, "model_dump")
    }
    canonical = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
