"""The local credential adapter and the redaction every runtime row passes.

The operator provides a credential as the environment variable
`PT_MCP_SECRET_<REF>` of the MCP process, where `<REF>` is the reference
upper-cased with every other character turned into `_`. The value never
travels through the MCP input, and nothing here writes it anywhere. Two
references that map to the same variable resolve the same value; that is an
alias, not a leak.

Redaction covers every form in which a value can reach text from a generated
script: raw, JSON-escaped (both ASCII and Unicode escaping) and URL-encoded.
A value shorter than `MIN_SECRET_LENGTH` is refused at resolution, because
redacting one or two characters would mangle every diagnostic without making
anything safer.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Iterable, Mapping
from urllib.parse import quote, quote_plus

from ...application.ports.secret_resolver import SecretUnavailable, SecretValue

SECRET_ENV_PREFIX = "PT_MCP_SECRET_"
MIN_SECRET_LENGTH = 4
REDACTED = "[redacted]"
_REFERENCE = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")


def secret_environment_name(secret_ref: str) -> str:
    """Return the environment variable one reference is read from."""
    return SECRET_ENV_PREFIX + re.sub(r"[^A-Za-z0-9]", "_", secret_ref).upper()


class EnvironmentSecretResolver:
    """Resolve references from the process environment, once per instance.

    One instance serves one invocation: admission resolves every reference
    first, and the runtime resolves again from the same instance while it
    builds a script, so both see the value admission accepted.
    """

    def __init__(self, environ: Mapping[str, str] | None = None) -> None:
        """Bind the environment to read; the process environment by default."""
        self._environ = os.environ if environ is None else environ
        self._resolved: dict[str, SecretValue] = {}

    def resolve(self, secret_ref: str) -> SecretValue:
        """Return the value for one reference, or raise `SecretUnavailable`."""
        if secret_ref in self._resolved:
            return self._resolved[secret_ref]
        if not _REFERENCE.fullmatch(secret_ref or ""):
            raise SecretUnavailable(secret_ref, "invalid_reference")
        value = self._environ.get(secret_environment_name(secret_ref))
        if value is None or value == "":
            raise SecretUnavailable(secret_ref, "not_set")
        if len(value) < MIN_SECRET_LENGTH:
            raise SecretUnavailable(secret_ref, "too_short")
        resolved = SecretValue(value)
        self._resolved[secret_ref] = resolved
        return resolved


def secret_forms(value: str) -> set[str]:
    """Return every text form in which one value could reach a diagnostic."""
    if not value:
        return set()
    return {
        value,
        json.dumps(value)[1:-1],
        json.dumps(value, ensure_ascii=False)[1:-1],
        quote(value, safe=""),
        quote_plus(value),
    }


def redact_secret_values(text: str, values: Iterable[str]) -> str:
    """Replace every form of every value in `text`, longest form first."""
    forms = sorted(
        {form for value in values for form in secret_forms(value) if form},
        key=len,
        reverse=True,
    )
    for form in forms:
        text = text.replace(form, REDACTED)
    return text
