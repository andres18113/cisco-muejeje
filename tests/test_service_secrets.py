"""The S2 secret port, its local adapter, and redaction of every value form.

A credential enters the product as an opaque `secret_ref` and becomes a value
only inside infrastructure, for the one script that needs it. These tests pin
the two properties everything else relies on: the value never shows itself
through a representation, and every form in which it could reach text -- raw,
JSON-escaped or URL-encoded -- is redacted.
"""

from __future__ import annotations

import json
from urllib.parse import quote, quote_plus

import pytest

from packet_tracer_mcp.application.ports.secret_resolver import (
    SecretUnavailable,
    SecretValue,
)
from packet_tracer_mcp.infrastructure.execution.secret_resolver import (
    EnvironmentSecretResolver,
    redact_secret_values,
    secret_environment_name,
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
