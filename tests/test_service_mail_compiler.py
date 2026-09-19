"""S2 mail compilation: accounts, clients, message pairs and plan content.

Every plan here is compiled from an intent through the real designer, E5
compiler and service compiler, so a pair, an id or a hash is the one the
product would produce. Expected values come from the requirement, never from a
second copy of the pairing algorithm.
"""

from __future__ import annotations

import copy
import json
from typing import Any

import pytest
from service_entry_fixture import BACKEND_VERSION, deployment_manifest, intent_payload

from packet_tracer_mcp.application.use_cases.compose_enterprise_reference import (
    compose_enterprise_reference,
)
from packet_tracer_mcp.domain.enterprise.models.configuration import (
    ConfigurationIssueCode,
)
from packet_tracer_mcp.domain.enterprise.models.execution import OperationSemantics
from packet_tracer_mcp.domain.enterprise.models.intent import EnterpriseIntent
from packet_tracer_mcp.domain.enterprise.models.service_plan import (
    ConfigureEmailClient,
    EnablePop3Service,
    EnableSmtpService,
    EnsureEmailAccount,
    SendMailMessage,
    ServicePhase,
    ServiceVerificationKind,
    secret_refs,
)
from packet_tracer_mcp.domain.enterprise.services.service_compiler import (
    ServiceCompiler,
)
from packet_tracer_mcp.infrastructure.catalog.service_capabilities import (
    packet_tracer_service_capabilities,
)

DOMAIN = "lab.example"
SERVER = "endpoint/hq/default/server/001"


def _pc(index: int) -> str:
    return f"endpoint/hq/default/user_pc/{index:03d}"


def _payload(
    clients: int = 2,
    *,
    pcs: int | None = None,
    pairs: list[tuple[int, int]] | None = None,
    accounts: list[dict[str, str]] | None = None,
    email_clients: list[dict[str, str]] | None = None,
    pop3: bool = True,
    mode: str | None = None,
    domain: str = DOMAIN,
) -> dict[str, Any]:
    """One segment, one server and `pcs` PCs, of which `clients` use mail."""
    payload = copy.deepcopy(intent_payload())
    site = payload["sites"][0]
    site["endpoints"][0]["count"] = pcs if pcs is not None else max(clients, 1)
    users = [f"user{index}" for index in range(1, clients + 1)]
    smtp: dict[str, Any] = {
        "name": "lab-mail",
        "service_type": "smtp",
        "domain_name": domain,
        "email_accounts": (
            accounts
            if accounts is not None
            else [{"username": name, "secret_ref": f"mail.{name}"} for name in users]
        ),
        "email_clients": (
            email_clients
            if email_clients is not None
            else [
                {"client_device_id": _pc(index), "username": name}
                for index, name in enumerate(users, start=1)
            ]
        ),
    }
    if pairs is not None:
        smtp["email_pairs"] = [
            {"sender_device_id": _pc(a), "recipient_device_id": _pc(b)}
            for a, b in pairs
        ]
    if mode is not None:
        smtp["verification_mode"] = mode
    services: list[dict[str, Any]] = [smtp]
    if pop3:
        services.append({"name": "lab-pop3", "service_type": "pop3"})
    site["services"] = services
    return payload


def _compile(payload: dict[str, Any]):
    """Compile through the real composition, then the real service compiler."""
    intent = EnterpriseIntent.model_validate(payload)
    manifest, _ = deployment_manifest(payload)
    composed = compose_enterprise_reference(
        intent, packet_tracer_version=BACKEND_VERSION, deployment_manifest=manifest
    )
    assert composed.configuration is not None, composed.issues
    return ServiceCompiler().compile(
        composed.enterprise,
        composed.topology,
        composed.configuration,
        capabilities=packet_tracer_service_capabilities(BACKEND_VERSION),
    )


def _plan(payload: dict[str, Any]):
    result = _compile(payload)
    assert result.is_valid, [item.model_dump() for item in result.issues]
    return result.plan


def _sends(plan) -> list[SendMailMessage]:
    return [item for item in plan.actions if isinstance(item, SendMailMessage)]


def _pairs(plan) -> set[tuple[str, str]]:
    configured = {
        item.host_device_id: item.mail_id
        for item in plan.actions
        if isinstance(item, ConfigureEmailClient)
    }
    by_mail = {mail: device for device, mail in configured.items()}
    return {
        (item.host_device_id, by_mail[item.recipient_mail_id]) for item in _sends(plan)
    }


def _error_codes(payload: dict[str, Any]) -> set[ConfigurationIssueCode]:
    result = _compile(payload)
    assert not result.is_valid
    return {item.code for item in result.issues if item.severity.value == "error"}


# -- pairing ------------------------------------------------------------------


def test_one_client_sends_to_itself():
    """R-MAIL-06: n=1 is a self-send, the only pair a lone client can have."""
    plan = _plan(_payload(1))

    assert _pairs(plan) == {(_pc(1), _pc(1))}


def test_two_clients_form_a_ring_of_two_pairs():
    """n=2: each client sends to the other exactly once."""
    plan = _plan(_payload(2))

    assert _pairs(plan) == {(_pc(1), _pc(2)), (_pc(2), _pc(1))}


def test_n_clients_form_a_ring_and_never_all_pairs():
    """n=4 yields n pairs, each client sending once and receiving once."""
    plan = _plan(_payload(4))
    pairs = _pairs(plan)

    assert len(pairs) == 4
    assert sorted(sender for sender, _ in pairs) == [_pc(i) for i in range(1, 5)]
    assert sorted(receiver for _, receiver in pairs) == [_pc(i) for i in range(1, 5)]
    assert all(sender != receiver for sender, receiver in pairs)
    # The all-pairs workload would be n*(n-1) = 12 sends.
    assert len(_sends(plan)) == 4


def test_explicit_pairs_replace_the_default_ring():
    """An explicit pair list is the workload, exactly as written."""
    plan = _plan(_payload(3, pairs=[(1, 3), (2, 2)]))

    assert _pairs(plan) == {(_pc(1), _pc(3)), (_pc(2), _pc(2))}


@pytest.mark.parametrize(
    "pairs",
    [[(1, 2), (1, 2)], [(1, 3)]],
    ids=["duplicate_pair", "recipient_is_not_an_email_client"],
)
def test_an_inadmissible_pair_is_a_compile_error(pairs):
    """A repeated pair or a pair outside the selected clients is refused."""
    assert ConfigurationIssueCode.EMAIL_PAIR_INVALID in _error_codes(
        _payload(2, pcs=3, pairs=pairs)
    )


def test_configure_only_compiles_no_message():
    """`configure_only` configures and reads back; it sends nothing."""
    plan = _plan(_payload(2, mode="configure_only"))

    assert _sends(plan) == []
    kinds = {item.kind for item in plan.verification_expectations}
    assert ServiceVerificationKind.SMTP_DELIVERED not in kinds
    assert ServiceVerificationKind.EMAIL_CLIENT_STATE in kinds


# -- accounts, clients and validation ------------------------------------------


def test_a_client_whose_account_is_missing_is_a_compile_error():
    """A client may only use an account the requirement declares."""
    codes = _error_codes(
        _payload(
            2,
            accounts=[{"username": "user1", "secret_ref": "mail.user1"}],
        )
    )

    assert ConfigurationIssueCode.EMAIL_ACCOUNT_MISSING in codes


@pytest.mark.parametrize(
    ("overrides", "code"),
    [
        ({"domain": "not a domain"}, ConfigurationIssueCode.EMAIL_DOMAIN_INVALID),
        ({"domain": ""}, ConfigurationIssueCode.EMAIL_DOMAIN_INVALID),
        (
            {
                "accounts": [
                    {"username": "user1", "secret_ref": "has space"},
                    {"username": "user2", "secret_ref": "mail.user2"},
                ]
            },
            ConfigurationIssueCode.SECRET_REF_INVALID,
        ),
        (
            {
                "accounts": [
                    {"username": "user1", "secret_ref": "a"},
                    {"username": "USER1", "secret_ref": "b"},
                    {"username": "user2", "secret_ref": "c"},
                ]
            },
            ConfigurationIssueCode.EMAIL_ACCOUNT_INVALID,
        ),
        (
            {
                "email_clients": [
                    {"client_device_id": _pc(1), "username": "user1"},
                    {"client_device_id": _pc(1), "username": "user2"},
                ]
            },
            ConfigurationIssueCode.EMAIL_CLIENT_INVALID,
        ),
    ],
    ids=[
        "invalid_domain",
        "missing_domain",
        "invalid_secret_ref",
        "duplicate_account",
        "client_listed_twice",
    ],
)
def test_invalid_mail_requirements_are_typed_compile_errors(overrides, code):
    """Each malformed field has its own code, so a caller can act on it."""
    assert code in _error_codes(_payload(2, **overrides))


def test_unselected_clients_receive_no_mail_action():
    """A PC that is not an email client is never configured or messaged."""
    plan = _plan(_payload(2, pcs=3))
    touched = {
        item.host_device_id
        for item in plan.actions
        if isinstance(item, (ConfigureEmailClient, SendMailMessage))
    }

    assert touched == {_pc(1), _pc(2)}
    smtp = next(item for item in plan.services if item.service_type.value == "smtp")
    assert smtp.client_device_ids == [_pc(1), _pc(2)]


def test_actions_run_server_first_then_clients_then_messages():
    """Accounts precede the clients that use them; clients precede sends."""
    plan = _plan(_payload(2))
    by_id = {item.id: item for item in plan.actions}
    enable = next(item for item in plan.actions if isinstance(item, EnableSmtpService))
    pop3 = next(item for item in plan.actions if isinstance(item, EnablePop3Service))

    assert enable.domain_name == DOMAIN
    assert enable.phase is ServicePhase.ENABLE
    assert pop3.phase is ServicePhase.ENABLE
    for account in (a for a in plan.actions if isinstance(a, EnsureEmailAccount)):
        assert account.phase is ServicePhase.CONTENT
        assert account.operation is OperationSemantics.ENSURE_PRESENT
        assert enable.id in account.depends_on
    for client in (a for a in plan.actions if isinstance(a, ConfigureEmailClient)):
        assert client.phase is ServicePhase.CLIENT
        assert client.host_device_id != SERVER
        assert client.mail_id == f"{client.username}@{DOMAIN}"
        assert all(
            isinstance(by_id[item], EnsureEmailAccount) for item in client.depends_on
        )
    for send in _sends(plan):
        assert send.phase is ServicePhase.MESSAGE
        assert send.operation is OperationSemantics.EXECUTE_ONCE
        assert any(
            isinstance(by_id[item], ConfigureEmailClient)
            and by_id[item].host_device_id == send.host_device_id
            for item in send.depends_on
        )
    order = [item.id for item in plan.actions]
    assert order.index(enable.id) < min(order.index(item.id) for item in _sends(plan))


# -- identity, hash content and message references -----------------------------


def test_ids_and_the_semantic_hash_are_stable_across_compilations():
    """Two compilations of one intent are the same plan."""
    first, second = _plan(_payload(3)), _plan(_payload(3))

    assert [item.id for item in first.actions] == [item.id for item in second.actions]
    assert [item.id for item in first.verification_expectations] == [
        item.id for item in second.verification_expectations
    ]
    assert first.semantic_hash == second.semantic_hash


def test_the_plan_and_its_hash_carry_opaque_references_only():
    """R-SEC-01: a plan holds `secret_ref` strings and no nonce at all."""
    plan = _plan(_payload(2))
    dumped = plan.model_dump_json()

    assert secret_refs(plan.actions) == ["mail.user1", "mail.user2"]
    assert all(item.nonce == "" for item in _sends(plan))
    for expectation in plan.verification_expectations:
        assert "nonce" not in expectation.expected
    assert "password" not in dumped.casefold()
    # The references themselves are opaque names, which the hash may bind.
    assert "mail.user1" in dumped


def test_every_pair_shares_one_message_ref_across_its_rows():
    """R-EVT-04: send, delivery and retrieval of one pair name one message."""
    plan = _plan(_payload(3))
    refs = {send.id: send.message_ref for send in _sends(plan)}

    assert len(set(refs.values())) == len(refs) == 3
    for send in _sends(plan):
        rows = [
            item for item in plan.verification_expectations if item.action_id == send.id
        ]
        kinds = {item.kind for item in rows}
        assert kinds == {
            ServiceVerificationKind.SMTP_SEND,
            ServiceVerificationKind.SMTP_DELIVERED,
            ServiceVerificationKind.POP3_RETRIEVE,
            ServiceVerificationKind.EMAIL_END_TO_END,
        }
        assert {item.expected["message_ref"] for item in rows} == {send.message_ref}


def test_only_mailbox_presence_gates_the_mail_service():
    """R-EVT-05 fallback: event-dependent rows compile optional and gated."""
    plan = _plan(_payload(2))
    by_kind: dict[ServiceVerificationKind, list] = {}
    for item in plan.verification_expectations:
        by_kind.setdefault(item.kind, []).append(item)

    assert all(
        item.required for item in by_kind[ServiceVerificationKind.SMTP_DELIVERED]
    )
    for kind in (
        ServiceVerificationKind.SMTP_SEND,
        ServiceVerificationKind.POP3_RETRIEVE,
        ServiceVerificationKind.EMAIL_END_TO_END,
    ):
        assert by_kind[kind] and not any(item.required for item in by_kind[kind])
    send_rows = {item.id for item in by_kind[ServiceVerificationKind.SMTP_SEND]}
    for retrieve in by_kind[ServiceVerificationKind.POP3_RETRIEVE]:
        assert set(retrieve.depends_on) & send_rows


def test_pop3_rows_exist_only_with_a_pop3_service_on_the_host():
    """Without a POP3 service there is no retrieval row to report."""
    kinds = {
        item.kind for item in _plan(_payload(2, pop3=False)).verification_expectations
    }

    assert ServiceVerificationKind.POP3_RETRIEVE not in kinds
    assert ServiceVerificationKind.EMAIL_END_TO_END not in kinds
    assert ServiceVerificationKind.SMTP_DELIVERED in kinds


def test_mailbox_presence_is_performed_on_the_server_and_reported_on_the_recipient():
    """The row belongs to the recipient; the capability is the server's."""
    plan = _plan(_payload(2))
    delivered = [
        item
        for item in plan.verification_expectations
        if item.kind is ServiceVerificationKind.SMTP_DELIVERED
    ]
    receivers = {receiver for _, receiver in _pairs(plan)}

    assert {item.client_device_id for item in delivered} == receivers
    assert {item.target_model for item in delivered} == {"Server-PT"}
    client_state = [
        item
        for item in plan.verification_expectations
        if item.kind is ServiceVerificationKind.EMAIL_CLIENT_STATE
    ]
    assert {item.target_model for item in client_state} == {"PC-PT"}


def test_binding_nonces_changes_a_copy_and_never_the_compiled_plan():
    """Per-run nonces reach the send and its rows without entering the plan."""
    plan = _plan(_payload(2))
    before = plan.model_dump_json()
    nonces = {send.message_ref: f"n{index}" for index, send in enumerate(_sends(plan))}

    bound = plan.with_message_nonces(nonces)

    assert plan.model_dump_json() == before
    assert bound.semantic_hash == plan.semantic_hash
    for send in _sends(bound):
        assert send.nonce == nonces[send.message_ref]
    for item in bound.verification_expectations:
        if "message_ref" in item.expected:
            assert item.expected["nonce"] == nonces[item.expected["message_ref"]]
    assert json.loads(before)["id"] == bound.id
