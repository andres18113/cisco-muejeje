"""S2 mail through the product entry point, with only external seams injected.

The intent is composed, compiled, admitted, applied and recorded by the real
components. The E5 runtime is the recording fake every S1 entry test uses; the
E6 runtime is split so that DNS/HTTP go to the S1 recording fake and mail goes
to the REAL `PacketTracerEnterpriseServiceRuntime` over the Node mail stub, so
every mail row below comes from a generated script that actually ran.

Two catalogs appear. The default one is the product: every mail operation is
UNKNOWN, so mail can never reach an effect. The candidate path needs mail
operations marked SUPPORTED, which this module does with an explicit test-bound
catalog passed to the use case -- a parameter the MCP tool does not expose. A
green result on that path is candidate-runtime evidence, never product
acceptance.
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import quote

import pytest
from service_entry_fixture import (
    BACKEND_VERSION,
    DEPLOYMENT_ID,
    FINGERPRINT,
    EndpointObserver,
    IsolationPreflight,
    ManifestStore,
    RecordingConfigurationRuntime,
    RecordingServiceRuntime,
    deployment_manifest,
    intent_payload,
)
from test_service_mail_script_harness import PASSWORD, _MailEngine, _needs_node

from packet_tracer_mcp.application.ports.service_run_record import (
    RunRecordPersistenceError,
)
from packet_tracer_mcp.application.use_cases.apply_enterprise_services import (
    ServiceStageRuntimes,
    TransportSelection,
    apply_enterprise_services,
)
from packet_tracer_mcp.application.use_cases.compose_enterprise_reference import (
    compose_enterprise_reference,
)
from packet_tracer_mcp.domain.enterprise.models.capabilities import CapabilityStatus
from packet_tracer_mcp.domain.enterprise.models.configuration_runtime import (
    ActionExecutionStatus,
)
from packet_tracer_mcp.domain.enterprise.models.intent import EnterpriseIntent
from packet_tracer_mcp.domain.enterprise.models.service_entry import (
    ServiceEntryRefusal,
    ServiceRunStatus,
    ServiceStage,
)
from packet_tracer_mcp.domain.enterprise.models.service_plan import (
    ServiceActionType,
    ServiceType,
    ServiceVerificationKind,
)
from packet_tracer_mcp.domain.enterprise.models.service_run_record import (
    ServiceRunRecord,
    SourceTreeIdentity,
)
from packet_tracer_mcp.infrastructure.catalog.service_capabilities import (
    packet_tracer_service_capabilities,
)
from packet_tracer_mcp.infrastructure.execution.enterprise_service_runtime import (
    PacketTracerEnterpriseServiceRuntime,
)
from packet_tracer_mcp.infrastructure.execution.secret_resolver import (
    EnvironmentSecretResolver,
)
from packet_tracer_mcp.infrastructure.persistence.service_run_record_store import (
    ServiceRunRecordStore,
)

DOMAIN = "lab.example"
SERVER_NAME = "HQ-DEFAULT-SERVER-01"
PC_NAMES = ("HQ-DEFAULT-PC-01", "HQ-DEFAULT-PC-02")
SMTP_SERVICE = "service/hq/lab-mail"
SECRETS = {"PT_MCP_SECRET_MAIL_USER1": PASSWORD, "PT_MCP_SECRET_MAIL_USER2": "pw-two"}
_MAIL_TYPES = {ServiceType.SMTP, ServiceType.POP3}
_MAIL_KINDS = {
    ServiceVerificationKind.EMAIL_CLIENT_STATE,
    ServiceVerificationKind.SMTP_SEND,
    ServiceVerificationKind.SMTP_DELIVERED,
    ServiceVerificationKind.POP3_RETRIEVE,
    ServiceVerificationKind.EMAIL_END_TO_END,
}


def _pc(index: int) -> str:
    return f"endpoint/hq/default/user_pc/{index:03d}"


def _mail_payload(*, required: bool = True, pop3: bool = True) -> dict[str, Any]:
    """Return the S1 fixture's DNS and HTTP, plus mail for its two PCs."""
    payload = copy.deepcopy(intent_payload())
    services = payload["sites"][0]["services"]
    services.append(
        {
            "name": "lab-mail",
            "service_type": "smtp",
            "required": required,
            "domain_name": DOMAIN,
            "email_accounts": [
                {"username": "user1", "secret_ref": "mail.user1"},
                {"username": "user2", "secret_ref": "mail.user2"},
            ],
            "email_clients": [
                {"client_device_id": _pc(1), "username": "user1"},
                {"client_device_id": _pc(2), "username": "user2"},
            ],
        }
    )
    if pop3:
        services.append(
            {"name": "lab-pop3", "service_type": "pop3", "required": required}
        )
    return payload


def _candidate_catalog(version: str):
    """Return the default catalog with the mail candidate operations SUPPORTED.

    Explicit and local to this module. The event-dependent kinds stay UNKNOWN:
    nothing here pretends an observer exists.
    """
    records = dict(packet_tracer_service_capabilities(version))
    supported = CapabilityStatus.SUPPORTED
    for service_type, actions in (
        (
            ServiceType.SMTP,
            (ServiceActionType.ENABLE_SMTP, ServiceActionType.ENSURE_EMAIL_ACCOUNT),
        ),
        (ServiceType.POP3, (ServiceActionType.ENABLE_POP3,)),
    ):
        key = f"Server-PT:{service_type.value}"
        records[key] = records[key].model_copy(
            update={
                "application_support": supported,
                "direct_readback_support": supported,
                "action_application_support": {
                    item.value: supported for item in actions
                },
            }
        )
    for key in (
        "PC-PT:configure_email_client",
        "PC-PT:send_mail_message",
        "PC-PT:email_client_state",
        "Server-PT:smtp_delivered",
    ):
        records[key] = records[key].model_copy(update={"support": supported})
    return records


@dataclass
class _SplitServiceRuntime:
    """DNS/HTTP through the S1 recording fake; mail through the real runtime."""

    recording: RecordingServiceRuntime
    mail: PacketTracerEnterpriseServiceRuntime
    applied: list[list[str]] = field(default_factory=list)

    def inventory(self):
        """Return the deployed targets."""
        return self.recording.inventory()

    def apply_actions(self, actions):
        """Split one batch by family and keep the order of its rows."""
        self.applied.append([item.id for item in actions])
        mail = [item for item in actions if item.service_type in _MAIL_TYPES]
        other = [item for item in actions if item.service_type not in _MAIL_TYPES]
        rows = self.recording.apply_actions(other) if other else []
        return [*rows, *(self.mail.apply_actions(mail) if mail else [])]

    def verify(self, expectation):
        """Route mail reads to the real runtime."""
        if expectation.kind in _MAIL_KINDS or expectation.expected.get(
            "service_type"
        ) in {"smtp", "pop3"}:
            return self.mail.verify(expectation)
        return self.recording.verify(expectation)


@dataclass
class _Run:
    """One invocation's collaborators, with the recorded calls kept."""

    tmp_path: Path
    payload: dict[str, Any]
    engine: _MailEngine | None = None
    configuration: RecordingConfigurationRuntime | None = None
    services: _SplitServiceRuntime | None = None
    record_store: Any = None
    nonces: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        """Build the deployment, the stub network and both runtimes."""
        self.manifest, inventory = deployment_manifest(self.payload)
        self.configuration = RecordingConfigurationRuntime(targets=inventory)
        self.engine = _MailEngine()
        self.engine.state["devices"] = {
            SERVER_NAME: self.engine.state["devices"]["__MCP_E6_SERVER"],
            PC_NAMES[0]: self.engine.state["devices"]["__MCP_E6_PC1"],
            PC_NAMES[1]: self.engine.state["devices"]["__MCP_E6_PC2"],
        }
        self.services = _SplitServiceRuntime(
            recording=RecordingServiceRuntime(targets=inventory),
            mail=PacketTracerEnterpriseServiceRuntime(
                lambda: [],
                lambda script, timeout: None,
                dispatch_and_wait=self.engine.dispatch_and_wait,
                secret_resolver=EnvironmentSecretResolver(SECRETS),
                mail_timeout_seconds=0.0,
            ),
        )
        self.record_store = ServiceRunRecordStore(self.tmp_path)

    @property
    def mail_batches(self) -> list[list[str]]:
        """Every E6 batch that contained a mail action."""
        mail_ids = {
            item.id for item in self._plan_actions() if item.service_type in _MAIL_TYPES
        }
        return [batch for batch in self.services.applied if set(batch) & mail_ids]

    def _plan_actions(self):
        composed = compose_enterprise_reference(
            EnterpriseIntent.model_validate(self.payload),
            packet_tracer_version=BACKEND_VERSION,
            deployment_manifest=self.manifest,
            services=True,
            service_capabilities=packet_tracer_service_capabilities(BACKEND_VERSION),
        )
        assert composed.services is not None, composed.issues
        return composed.services.actions

    def run(self, **overrides: Any):
        """Invoke the product use case through its real components."""
        counter = iter(range(1000))

        def nonce() -> str:
            value = f"nonce{next(counter):03d}"
            self.nonces.append(value)
            return value

        arguments: dict[str, Any] = dict(
            deployment_id=DEPLOYMENT_ID,
            packet_tracer_version=BACKEND_VERSION,
            runtimes=ServiceStageRuntimes(
                configuration=self.configuration, services=self.services
            ),
            manifest_store=ManifestStore(manifest=self.manifest),
            record_store=self.record_store,
            import_preflight=IsolationPreflight(),
            environment_fingerprint=FINGERPRINT,
            transport_selection=TransportSelection(channel="http"),
            endpoint_observer=EndpointObserver(address=""),
            source_tree=SourceTreeIdentity(sha="test-source", dirty=True),
            secret_resolver=EnvironmentSecretResolver(SECRETS),
            message_nonce_factory=nonce,
        )
        arguments.update(overrides)
        return apply_enterprise_services(json.dumps(self.payload), **arguments)


def _rows(result, kind: ServiceVerificationKind):
    return [
        check
        for client in result.clients
        for outcome in client.results.values()
        for check in outcome.checks
        if check.kind is kind
    ]


def _credential_forms() -> list[str]:
    return [
        PASSWORD,
        json.dumps(PASSWORD)[1:-1],
        json.dumps(PASSWORD, ensure_ascii=False)[1:-1],
        quote(PASSWORD, safe=""),
    ]


# -- the default catalog: no mail effect can exist --------------------------------


def test_a_required_mail_service_refuses_before_e5_on_the_default_catalog(tmp_path):
    """S2-08: required and UNKNOWN is SERVICE_INELIGIBLE, with zero effects."""
    run = _Run(tmp_path, _mail_payload(required=True))

    result = run.run()

    assert result.refusal_code is ServiceEntryRefusal.SERVICE_INELIGIBLE
    assert "smtp" in result.blocked_reason
    assert run.configuration.applied == []
    assert run.services.applied == []
    assert run.engine.scripts == []


def test_an_optional_mail_service_is_excluded_and_its_clients_keep_their_rows(
    tmp_path,
):
    """S2-08 and R-COV-01: excluded before E5, reported per selected client."""
    run = _Run(tmp_path, _mail_payload(required=False))

    result = run.run()

    assert result.refusal_code is ServiceEntryRefusal.NONE
    assert run.mail_batches == []
    assert run.engine.scripts == []
    for client in result.clients:
        outcome = client.results[SMTP_SERVICE]
        assert outcome.status is ActionExecutionStatus.SKIPPED
        assert outcome.checks
        assert {check.status for check in outcome.checks} == {
            ActionExecutionStatus.SKIPPED
        }


# -- admission of secret-bearing work ------------------------------------------------


def test_a_file_channel_refuses_secret_bearing_mail_before_any_effect(tmp_path):
    """S2-09: no file fallback for a credential, refused before E5."""
    run = _Run(tmp_path, _mail_payload())

    result = run.run(
        capability_catalog=_candidate_catalog,
        transport_selection=TransportSelection(channel="file"),
    )

    assert result.refusal_code is ServiceEntryRefusal.SECRET_TRANSPORT_UNAVAILABLE
    assert run.configuration.applied == []
    assert run.services.applied == []


def test_an_unresolved_credential_refuses_before_any_effect_and_leaks_nothing(
    tmp_path,
):
    """S2-09: every reference resolves first; the refusal names refs only."""
    run = _Run(tmp_path, _mail_payload())

    result = run.run(
        capability_catalog=_candidate_catalog,
        secret_resolver=EnvironmentSecretResolver(
            {"PT_MCP_SECRET_MAIL_USER1": PASSWORD}
        ),
    )

    assert result.refusal_code is ServiceEntryRefusal.SECRET_UNRESOLVED
    assert "mail.user2" in result.blocked_reason
    assert run.configuration.applied == []
    assert run.services.applied == []
    rendered = result.model_dump_json()
    for form in _credential_forms():
        assert form not in rendered


# -- entry controls bind mail ----------------------------------------------------------


def test_e5_uncertainty_dispatches_no_mail_effect(tmp_path):
    """S2-10: an E5 effect nobody can describe admits no E6 effect at all."""
    run = _Run(tmp_path, _mail_payload())
    run.configuration.raise_after_dispatch = True

    result = run.run(capability_catalog=_candidate_catalog)

    assert result.refusal_code is ServiceEntryRefusal.E5_EFFECT_UNCERTAIN
    assert run.services.applied == []
    assert run.engine.scripts == []
    assert run.engine.state["sends"] == []


def test_a_lost_record_rewrite_stops_every_mail_effect(tmp_path):
    """S2-10: after persistence is lost, no further mutation is dispatched."""

    class FailAfterFirstAdvance(ServiceRunRecordStore):
        def __init__(self, base):
            super().__init__(base)
            self.advances = 0

        def advance(self, record):
            self.advances += 1
            if self.advances > 1:
                raise RunRecordPersistenceError("volume went read-only")
            return super().advance(record)

    run = _Run(tmp_path, _mail_payload())
    run.record_store = FailAfterFirstAdvance(tmp_path)

    result = run.run(capability_catalog=_candidate_catalog)

    assert result.refusal_code is ServiceEntryRefusal.EFFECT_HALTED
    assert run.services.applied == []
    assert run.engine.state["sends"] == []
    assert run.engine.state["add_user_calls"] == []


# -- the injected candidate path ----------------------------------------------------------


def test_the_candidate_path_sends_once_per_pair_and_claims_no_success(tmp_path):
    """S2-04/05/06/07 through the real product path and the real scripts."""
    _needs_node()
    run = _Run(tmp_path, _mail_payload())

    result = run.run(capability_catalog=_candidate_catalog)

    sends = run.engine.state["sends"]
    assert sorted((item["device"], item["to"]) for item in sends) == [
        (PC_NAMES[0], f"user2@{DOMAIN}"),
        (PC_NAMES[1], f"user1@{DOMAIN}"),
    ]
    assert sorted(item["subject"] for item in sends) == sorted(
        f"MCP-E6-MAIL-{value}" for value in run.nonces
    )
    record = ServiceRunRecordStore(tmp_path).load(DEPLOYMENT_ID, result.run_id)
    assert sorted(record.nonces.values()) == sorted(run.nonces)
    send_rows = [
        item
        for item in result.service_result.action_results
        if item.action_id.startswith("svc/email-send/")
    ]
    assert len(send_rows) == 2
    for row in send_rows:
        assert row.status is ActionExecutionStatus.APPLIED
        assert row.cause == "effect_unobservable:no_qualified_observation"
    delivered = _rows(result, ServiceVerificationKind.SMTP_DELIVERED)
    assert len(delivered) == 2
    for row in delivered:
        assert row.observation.value == "observed"
        assert row.status is ActionExecutionStatus.PARTIAL
        assert row.claim_level == "server_mailbox_presence"
        assert any(
            item.startswith("recovery_read_after_unresolved_action:")
            for item in row.limitations
        )
    for kind in (
        ServiceVerificationKind.SMTP_SEND,
        ServiceVerificationKind.POP3_RETRIEVE,
        ServiceVerificationKind.EMAIL_END_TO_END,
    ):
        rows = _rows(result, kind)
        assert len(rows) == 2
        assert all(row.status is not ActionExecutionStatus.VERIFIED for row in rows)
    # The send's uncertainty is sticky: a supporting read never lifts the run.
    assert result.status is not ServiceRunStatus.VERIFIED
    assert result.stage is ServiceStage.COMPLETED


def test_unrelated_dns_and_http_success_never_upgrades_mail(tmp_path):
    """S2-10: DNS/HTTP verify; the mail service and the run stay below it."""
    _needs_node()
    run = _Run(tmp_path, _mail_payload())

    result = run.run(capability_catalog=_candidate_catalog)

    by_service = {item.service_id: item for item in result.services}
    assert by_service["service/hq/lab-dns"].usability_status is (
        ActionExecutionStatus.VERIFIED
    )
    assert by_service["service/hq/lab-web"].usability_status is (
        ActionExecutionStatus.VERIFIED
    )
    assert by_service[SMTP_SERVICE].usability_status is not (
        ActionExecutionStatus.VERIFIED
    )
    assert result.status is not ServiceRunStatus.VERIFIED


def test_the_record_holds_no_credential_and_round_trips_cause_and_limitation(
    tmp_path,
):
    """S2-09: every stored form is clean, and JSON keeps what the row said."""
    _needs_node()
    run = _Run(tmp_path, _mail_payload())
    run.engine.state["send_throws_after_effect"] = True

    result = run.run(capability_catalog=_candidate_catalog)

    stored_bytes = b"".join(
        path.read_bytes() for path in tmp_path.rglob("*.json")
    ).decode("utf-8")
    rendered = result.model_dump_json()
    for form in _credential_forms():
        assert form not in stored_bytes
        assert form not in rendered
    record = ServiceRunRecord.model_validate_json(
        ServiceRunRecordStore(tmp_path)
        .load(DEPLOYMENT_ID, result.run_id)
        .model_dump_json()
    )
    send = next(
        item
        for item in record.service_result.action_results
        if item.action_id.startswith("svc/email-send/")
    )
    assert send.cause == "effect_unobservable:no_qualified_observation"
    assert send.received_mutation is not None
    assert send.received_mutation.call_error
    delivered = next(
        item
        for item in record.service_result.verification_results
        if item.expectation_id.startswith("svc/verify-smtp-delivered/")
    )
    assert any(
        item.startswith("recovery_read_after_unresolved_action:")
        for item in delivered.limitations
    )


def test_a_lost_send_answer_is_never_resent(tmp_path):
    """No automatic resend: each pair's message is dispatched exactly once."""
    _needs_node()
    run = _Run(tmp_path, _mail_payload())
    run.engine.lose_answers_for = "sendMail"

    result = run.run(capability_catalog=_candidate_catalog)

    assert len(run.engine.state["sends"]) == 2
    assert sum("sendMail" in script for script in run.engine.scripts) == 2
    assert result.status is not ServiceRunStatus.VERIFIED


@pytest.mark.parametrize("pop3", [True, False], ids=["with_pop3", "smtp_only"])
def test_every_pair_keeps_a_row_when_blocked(tmp_path, pop3):
    """R-COV-01: blocked and gated pair rows are still reported."""
    _needs_node()
    run = _Run(tmp_path, _mail_payload(pop3=pop3))

    result = run.run(capability_catalog=_candidate_catalog)

    assert len(_rows(result, ServiceVerificationKind.SMTP_SEND)) == 2
    assert len(_rows(result, ServiceVerificationKind.SMTP_DELIVERED)) == 2
    expected = 2 if pop3 else 0
    assert len(_rows(result, ServiceVerificationKind.POP3_RETRIEVE)) == expected
