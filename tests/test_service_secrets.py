"""The S2 secret port, its adapter, and the boundary every diagnostic crosses.

A credential enters the product as an opaque `secret_ref` and becomes a value
only inside infrastructure, for the one script that needs it. These tests pin
the properties everything else relies on: the value never shows itself through
a representation; every form in which it could reach text -- raw, JSON-escaped
or URL-encoded -- is redacted; and the redaction happens BEFORE the diagnostic
is folded and truncated, because both of those destroy the text a later
redactor would have to match.

The last section runs the real `PacketTracerEnterpriseServiceRuntime` over a
scripted channel, because the boundary has to hold on the verification exits
too, not only on the mutation rows of the batch that resolved the value.
"""

from __future__ import annotations

import json
from urllib.parse import quote, quote_plus

import pytest

from packet_tracer_mcp.application.ports.secret_resolver import (
    SecretUnavailable,
    SecretValue,
)
from packet_tracer_mcp.domain.enterprise.models.execution import (
    DispatchFact,
    ResultFact,
)
from packet_tracer_mcp.domain.enterprise.models.service_plan import (
    EnsureEmailAccount,
    ServiceEvidenceKind,
    ServicePhase,
    ServiceType,
    ServiceVerificationExpectation,
    ServiceVerificationKind,
)
from packet_tracer_mcp.domain.enterprise.models.service_runtime import ObservationFact
from packet_tracer_mcp.infrastructure.execution.enterprise_service_runtime import (
    PacketTracerEnterpriseServiceRuntime,
)
from packet_tracer_mcp.infrastructure.execution.secret_resolver import (
    REDACTED,
    EnvironmentSecretResolver,
    EvidenceSanitizer,
    redact_secret_values,
    secret_environment_name,
)
from packet_tracer_mcp.infrastructure.execution.transport_outcome import (
    MAX_DETAIL_CHARS,
    BridgeDispatchOutcome,
    sanitized_detail,
)

#: Quotes, a backslash, a newline, a script terminator, a percent sign, a space
#: and a non-ASCII letter: every character class a form could encode.
ADVERSARIAL = 'p"a\\s\ns</script>%20 ñ'


def test_a_secret_value_never_shows_itself():
    """`repr`, `str` and formatting show a placeholder, never the value."""
    value = SecretValue("hunter22")

    assert value.reveal() == "hunter22"
    for rendered in (repr(value), str(value), f"{value}", f"{value!r}"):
        assert "hunter22" not in rendered


def test_the_environment_name_is_derived_from_the_reference():
    """One reference maps to one bounded variable name in its own prefix."""
    assert secret_environment_name("mail.user-1") == "PT_MCP_SECRET_MAIL_USER_1"


def test_a_reference_resolves_from_its_variable_and_is_memoized():
    """Admission and dispatch of one invocation see one value."""
    environ = {"PT_MCP_SECRET_MAIL_USER1": "first-value"}
    resolver = EnvironmentSecretResolver(environ)

    assert resolver.resolve("mail.user1").reveal() == "first-value"
    environ["PT_MCP_SECRET_MAIL_USER1"] = "changed-value"
    assert resolver.resolve("mail.user1").reveal() == "first-value"


@pytest.mark.parametrize(
    ("reference", "environ", "reason"),
    [
        ("mail.user1", {}, "not_set"),
        ("has space", {"PT_MCP_SECRET_HAS_SPACE": "long-enough"}, "invalid_reference"),
        ("", {}, "invalid_reference"),
        ("x" * 65, {}, "invalid_reference"),
        ("mail.user1", {"PT_MCP_SECRET_MAIL_USER1": "abc"}, "too_short"),
    ],
    ids=["unset", "space", "empty", "too_long", "value_too_short"],
)
def test_an_unresolvable_reference_is_typed_and_leaks_nothing(
    reference, environ, reason
):
    """The failure names its category; it never carries a value."""
    resolver = EnvironmentSecretResolver(environ)

    with pytest.raises(SecretUnavailable) as caught:
        resolver.resolve(reference)

    assert caught.value.reason == reason
    for value in environ.values():
        assert value not in str(caught.value)
        assert value not in repr(caught.value)


def test_every_form_of_a_value_is_redacted():
    """Raw, JSON-escaped (both encodings) and URL-encoded forms all vanish."""
    forms = [
        ADVERSARIAL,
        json.dumps(ADVERSARIAL)[1:-1],
        json.dumps(ADVERSARIAL, ensure_ascii=False)[1:-1],
        quote(ADVERSARIAL, safe=""),
        quote_plus(ADVERSARIAL),
    ]
    text = " | ".join(f"<{form}>" for form in forms) + " | unrelated"

    redacted = redact_secret_values(text, [ADVERSARIAL])

    for form in forms:
        assert form not in redacted
    assert redacted.count("[redacted]") == len(forms)
    assert redacted.endswith("| unrelated")


def test_redaction_leaves_text_without_a_value_unchanged():
    """No value, or no occurrence, changes nothing."""
    assert redact_secret_values("plain text", []) == "plain text"
    assert redact_secret_values("plain text", ["other-value"]) == "plain text"


# -- the invocation-local evidence boundary ----------------------------------------


def _sanitizer(*values: str) -> EvidenceSanitizer:
    sanitizer = EvidenceSanitizer()
    for value in values:
        sanitizer.remember(value)
    return sanitizer


def test_the_boundary_redacts_before_it_folds_and_truncates():
    """S2-12: folding first destroys the very text the redactor must match."""
    value = "top  secret\tvalue"
    text = f"engine said {value} while setting"

    assert redact_secret_values(sanitized_detail(text), [value]) != sanitized_detail(
        redact_secret_values(text, [value])
    )
    assert value not in _sanitizer(value).safe(text)
    assert " ".join(value.split()) not in _sanitizer(value).safe(text)


def test_the_boundary_bounds_what_it_returns():
    """The diagnostic stays single-line and within the shared bound."""
    safe = _sanitizer("hunter22").safe("a\nb" + "x" * 500)

    assert "\n" not in safe
    assert len(safe) <= MAX_DETAIL_CHARS


def test_a_value_crossing_the_bound_leaves_no_prefix():
    """Truncation cannot crop a value it can no longer see."""
    value = "A" * 60 + "-tail"
    safe = _sanitizer(value).safe("x" * (MAX_DETAIL_CHARS - 20) + value)

    assert value[:12] not in safe
    assert REDACTED in safe


def test_every_form_crosses_the_boundary_redacted():
    """Raw, JSON-escaped and URL-encoded forms are all removed first."""
    forms = [
        ADVERSARIAL,
        json.dumps(ADVERSARIAL)[1:-1],
        json.dumps(ADVERSARIAL, ensure_ascii=False)[1:-1],
        quote(ADVERSARIAL, safe=""),
        quote_plus(ADVERSARIAL),
    ]

    for form in forms:
        assert form not in _sanitizer(ADVERSARIAL).redact(f"<{form}>")


def test_a_boundary_holding_nothing_changes_nothing():
    """An invocation that resolved no value mangles no diagnostic."""
    sanitizer = EvidenceSanitizer()

    assert sanitizer.redact("plain text") == "plain text"
    assert sanitizer.safe("plain  text") == "plain text"
    assert _sanitizer("hunter22").safe("unrelated failure") == "unrelated failure"


# -- the boundary inside the real runtime ------------------------------------------

SERVER = "SRV"
CLIENT = "PC"
#: Two synthetic credentials for one invocation. The first carries repeated
#: whitespace, which folding would rewrite; the second is long enough to cross
#: the shared 200-character bound when an engine error prefixes it.
ALPHA = "top  secret\tvalue"
BETA = "B" * 60 + "-tail"
ENVIRON = {
    "PT_MCP_SECRET_MAIL_ALPHA": ALPHA,
    "PT_MCP_SECRET_MAIL_BETA": BETA,
}


class _Scripted:
    """A channel that answers each command from a prepared list, in order."""

    def __init__(self, *bodies: str) -> None:
        """Bind the bodies this channel reports, newest call last."""
        self.bodies = list(bodies)
        self.scripts: list[str] = []

    def dispatch_and_wait(self, script: str, _timeout: float):
        """Return the next prepared body as a correlated answer."""
        self.scripts.append(script)
        body = self.bodies.pop(0) if self.bodies else "{}"
        return BridgeDispatchOutcome(
            dispatch=DispatchFact.ACCEPTED,
            result=ResultFact.CORRELATED,
            body=body,
        )


def _runtime(channel: _Scripted):
    return PacketTracerEnterpriseServiceRuntime(
        lambda: [],
        lambda script, timeout: None,
        dispatch_and_wait=channel.dispatch_and_wait,
        secret_resolver=EnvironmentSecretResolver(ENVIRON),
        mail_timeout_seconds=0.0,
    )


def _common(**fields):
    values = dict(
        service_id="svc/mail",
        service_type=ServiceType.SMTP,
        host_device_id=SERVER,
        host_device_name=SERVER,
        host_model="Server-PT",
        site_id="hq",
        required_capability="service_smtp_application",
    )
    values.update(fields)
    return values


def _account(reference: str = "mail.alpha") -> EnsureEmailAccount:
    return EnsureEmailAccount(
        id=f"account-{reference}",
        phase=ServicePhase.CONTENT,
        username="user1",
        secret_ref=reference,
        **_common(),
    )


def _added_row(action_id: str) -> str:
    return json.dumps(
        {
            "results": [
                {
                    "id": action_id,
                    "attempted": True,
                    "skip_reason": "",
                    "call_error": "",
                    "call_result": True,
                    "pre_read": True,
                    "post_read": True,
                    "ok": True,
                    "changed": True,
                    "pre": "0",
                    "post": "1",
                }
            ]
        }
    )


def _client_state() -> ServiceVerificationExpectation:
    return ServiceVerificationExpectation(
        id="verify-client",
        service_id="svc/mail",
        action_id="client-PC",
        kind=ServiceVerificationKind.EMAIL_CLIENT_STATE,
        evidence_kind=ServiceEvidenceKind.DIRECT_STATE,
        host_device_id=SERVER,
        host_device_name=SERVER,
        client_device_id=CLIENT,
        client_device_name=CLIENT,
        host_model="Server-PT",
        client_model="PC-PT",
        expected={"name": "User1", "user": "user1"},
    )


def _forms(value: str) -> list[str]:
    return [
        value,
        json.dumps(value)[1:-1],
        json.dumps(value, ensure_ascii=False)[1:-1],
        quote(value, safe=""),
        quote_plus(value),
    ]


def _rendered(row) -> str:
    return json.dumps(row.model_dump(mode="json"), ensure_ascii=False)


def test_a_verification_engine_error_never_carries_a_resolved_value():
    """S2-12: the read exits that skipped redaction are on the boundary too."""
    channel = _Scripted(
        _added_row("account-mail.alpha"),
        "PT_ERROR: EmailClient refused " + ALPHA + " twice",
    )
    runtime = _runtime(channel)

    [mutation] = runtime.apply_actions([_account()])
    row = runtime.verify(_client_state())

    assert mutation.applied is True
    assert row.observation is ObservationFact.ENGINE_ERROR
    assert row.cause
    for form in _forms(ALPHA):
        assert form not in _rendered(row)
    assert "EmailClient refused" in row.cause


def test_a_value_from_an_earlier_batch_does_not_escape_in_a_later_error():
    """The boundary is the invocation's, not one batch's local list."""
    channel = _Scripted(
        _added_row("account-mail.alpha"),
        _added_row("account-mail.beta"),
        "PT_ERROR: leftover " + ALPHA + " from the first batch",
    )
    runtime = _runtime(channel)

    runtime.apply_actions([_account("mail.alpha")])
    runtime.apply_actions([_account("mail.beta")])
    row = runtime.verify(_client_state())

    for form in _forms(ALPHA):
        assert form not in _rendered(row)


def test_repeated_whitespace_inside_a_value_still_matches_its_redactor():
    """Folding the diagnostic first would leave the material behind."""
    channel = _Scripted(
        _added_row("account-mail.alpha"),
        "PT_ERROR: stored " + ALPHA + " already",
    )
    runtime = _runtime(channel)

    runtime.apply_actions([_account()])
    row = runtime.verify(_client_state())
    rendered = _rendered(row)

    assert ALPHA not in rendered
    assert " ".join(ALPHA.split()) not in rendered
    assert "secret" not in rendered


def test_a_value_crossing_the_truncation_bound_leaves_no_prefix():
    """A crop cannot expose material that was removed before the crop."""
    channel = _Scripted(
        _added_row("account-mail.beta"),
        "PT_ERROR: " + "x" * (MAX_DETAIL_CHARS - 20) + BETA,
    )
    runtime = _runtime(channel)

    runtime.apply_actions([_account("mail.beta")])
    row = runtime.verify(_client_state())

    assert BETA[:12] not in _rendered(row)


def test_a_safe_diagnostic_survives_the_boundary_unchanged():
    """A batch that resolved a value still reports what it can say safely."""
    channel = _Scripted(
        _added_row("account-mail.alpha"),
        "PT_ERROR: EmailClient process is absent",
    )
    runtime = _runtime(channel)

    runtime.apply_actions([_account()])
    row = runtime.verify(_client_state())

    assert row.cause == "PT_ERROR: EmailClient process is absent"
    assert row.claim_level == "direct_client_state"
