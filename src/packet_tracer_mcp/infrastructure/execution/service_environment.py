"""The executable-version reader shared by the product tool and the runner.

S1 corrected the reader to call `AppWindow.getVersion()`, which Cisco documents
as the running Packet Tracer version, instead of `NetworkFile.getVersion()`,
which is the version a file was saved with (`help/default/IpcAPI`,
`class_app_window.html` and `class_network_file.html`). The script and its
parse rule moved here unchanged from `tool_registry.py` so that a second
consumer, the qualification runner, uses the same reader rather than a copy.

A missing getter, an exception, a missing active file, a malformed answer or
anything but one bounded four-component build is unavailable. Nothing is ever
recovered from the saved file, the caller, a manifest or an install path. What
the installed application actually returns is unmeasured until a LIVE run.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable

from ...application.ports.service_qualification import BuildReading
from ...domain.enterprise.models.deployment import EnvironmentFingerprint
from ...domain.enterprise.models.service_qualification import (
    is_exact_packet_tracer_build,
)

SERVICE_ENVIRONMENT_JS = (
    "try{var app=ipc.appWindow();var f=app.getActiveFile();"
    "if(!f){reportResult(JSON.stringify({found:false,"
    "reason:'active_file_unavailable'}));}"
    "else if(typeof app.getVersion!=='function'){"
    "reportResult(JSON.stringify({found:false,"
    "reason:'application_version_unavailable'}));}else{"
    "reportResult(JSON.stringify({found:true,backend:'packet_tracer',"
    "backend_version:String(app.getVersion()||''),"
    "extension_version:'',runtime_mode:'logical-workspace'}));}}"
    "catch(e){reportResult('PT_ERROR:'+e);}"
)
READER_ID = "AppWindow.getVersion"
READER_SHA256 = hashlib.sha256(SERVICE_ENVIRONMENT_JS.encode("utf-8")).hexdigest()
MAX_EXCERPT_CHARS = 160


def _excerpt(raw: str | None) -> str:
    """Bound one raw answer to a single printable line for the record."""
    text = " ".join(str(raw or "").split())
    return text[:MAX_EXCERPT_CHARS]


def observe_service_environment(raw: str | None) -> tuple[str, str]:
    """Return `(exact_build, reason)`; the build is empty whenever unavailable."""
    if not raw:
        return "", "no_correlated_response"
    if raw.startswith(("PT_ERROR", "ERROR")):
        return "", "engine_error"
    try:
        observed = json.loads(raw)
    except (TypeError, ValueError):
        return "", "malformed_response"
    if not isinstance(observed, dict):
        return "", "malformed_response"
    if observed.get("found") is not True:
        reason = observed.get("reason")
        return "", f"not_found:{reason}" if isinstance(reason, str) else "not_found"
    backend_version = str(observed.get("backend_version") or "").strip()
    if not backend_version:
        return "", "version_absent"
    if not is_exact_packet_tracer_build(backend_version):
        return "", "version_not_exact_build"
    return backend_version, ""


def parse_service_environment(
    raw: str | None,
    *,
    channel: str,
) -> EnvironmentFingerprint:
    """Parse one bounded executable-version observation, with no fallback."""
    backend_version, reason = observe_service_environment(raw)
    if reason:
        return EnvironmentFingerprint()
    observed = json.loads(raw or "")
    return EnvironmentFingerprint(
        backend="packet_tracer",
        backend_version=backend_version,
        bridge_transport=channel,
        extension_version=str(observed.get("extension_version") or ""),
        runtime_mode=str(observed.get("runtime_mode") or ""),
    )


class ServiceEnvironmentReader:
    """Read the executable build once over one bound channel."""

    def __init__(
        self,
        send_and_wait: Callable[[str, float], str | None],
        *,
        timeout_seconds: float = 10.0,
    ) -> None:
        """Bind the reader to the invocation's fixed, counted channel."""
        self._send_and_wait = send_and_wait
        self._timeout = timeout_seconds

    def read(self) -> BuildReading:
        """Dispatch the shared reader and keep a bounded record of the answer."""
        raw = self._send_and_wait(SERVICE_ENVIRONMENT_JS, self._timeout)
        version, reason = observe_service_environment(raw)
        return BuildReading(
            available=not reason,
            version=version,
            reason=reason,
            excerpt=_excerpt(raw),
            reader_id=READER_ID,
            reader_sha256=READER_SHA256,
        )
