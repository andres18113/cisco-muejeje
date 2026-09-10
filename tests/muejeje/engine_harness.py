"""Drive the owned Script Engine sources under Node.

Node is optional and already used this way elsewhere in the suite
(`tests/test_e95_serial_physical_product_slice.py`), so this adds no undeclared
dependency: every check here is guarded and the structural gates run without
it.

**What Node establishes, and what it does not.** It establishes what *our*
JavaScript does — the envelope, the whitelist, the failure taxonomy. It
establishes nothing about Packet Tracer, whose Script Engine is a different
implementation, so a green run here is `RUNTIME_VERIFIED` for the kernel's own
logic and never evidence about `9.0.1.0858` (MJ-015, `AGENTS.md` rule 6).

The engine files are concatenated in the manifest's `engine_script_order` and
run as one Node module, which is the closest offline analogue of how Packet
Tracer evaluates them: sequentially, into one shared scope, before anything is
called.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from tests.muejeje.support import REPO_ROOT, repo_manifest

DEFAULT_REPORT = "JSON.parse(mcpDispatchV6(REQUEST))"


def node_available() -> bool:
    return shutil.which("node") is not None


def engine_order() -> list[Path]:
    """The declared evaluation order, read from the manifest that declares it.

    The harness names no engine file of its own. Evaluation order is a build
    fact decided in one place — `build_options.engine_script_order` — so a
    harness carrying its own copy would keep evaluating yesterday's module
    after a reorder, and every offline claim would then be about a module
    nobody packages.
    """
    return [
        REPO_ROOT / logical
        for logical in repo_manifest()["build_options"]["engine_script_order"]
    ]


def engine_bundle() -> str:
    return "\n".join(
        path.read_text(encoding="utf-8") for path in engine_order()
    )


def run_engine(epilogue: str) -> Any:
    """Evaluate the kernel, run `epilogue`, and decode what it printed."""
    node = shutil.which("node")
    assert node is not None, "guard with node_available() before calling"
    script = f"{engine_bundle()}\n\n{epilogue}\n"
    with tempfile.TemporaryDirectory(prefix="muejeje-v6-") as workspace:
        path = Path(workspace) / "kernel_harness.js"
        path.write_text(script, encoding="utf-8")
        completed = subprocess.run(
            [node, str(path)], cwd=REPO_ROOT, text=True, capture_output=True,
            check=False, timeout=60,
        )
    assert completed.returncode == 0, (
        f"the kernel must never throw out of the engine: {completed.stderr}"
    )
    return json.loads(completed.stdout)


def platform_stub(models: str, *, count: str | None = None, fail: bool = False) -> str:
    """A platform stub built from the documented getters, plus a call log.

    It is a *stub*, and it stays one: it establishes what the adapter does with
    a well-formed answer and nothing whatever about Packet Tracer, whose engine
    and hardware factory are a different implementation (MJ-015). The call log
    is what stops it from quietly becoming evidence about the platform — the
    caller compares the recorded calls against Cisco's documented getters, so
    an undocumented call fails here rather than on a target.

    `models` is a JavaScript array literal of
    `{model, type, supported, module_types}` objects. `count` overrides what
    `getAvailableDeviceCount()` answers, which is how an unusable answer is
    delivered; `fail` makes the first platform call throw, which is how a
    denied or otherwise refused call is delivered.
    """
    reported = "MODELS.length" if count is None else count
    refuses = "true" if fail else "false"
    return "\n".join([
        f"var MODELS = {models};",
        "var CALLS = [];",
        "function log(name) { CALLS.push(name); }",
        "function descriptor(spec) {",
        "  return {",
        "    getModel: function () { log('getModel'); return spec.model; },",
        "    getType: function () { log('getType'); return spec.type; },",
        "    isModelSupported: function () {",
        "      log('isModelSupported'); return spec.supported;",
        "    },",
        "    getSupportedModuleTypeCount: function () {",
        "      log('getSupportedModuleTypeCount'); return spec.module_types.length;",
        "    },",
        "    getSupportedModuleTypeAt: function (index) {",
        "      log('getSupportedModuleTypeAt'); return spec.module_types[index];",
        "    }",
        "  };",
        "}",
        "var FACTORY = {",
        "  getAvailableDeviceCount: function () {",
        f"    log('getAvailableDeviceCount'); return {reported};",
        "  },",
        "  getAvailableDeviceAt: function (index) {",
        "    log('getAvailableDeviceAt');",
        "    return MODELS[index] ? descriptor(MODELS[index]) : null;",
        "  }",
        "};",
        "var ipc = {hardwareFactory: function () {",
        "  log('hardwareFactory');",
        f"  if ({refuses}) {{",
        "    throw new Error('the platform refused this call');",
        "  }",
        "  return {devices: function () { log('devices'); return FACTORY; }};",
        "}};",
    ])


def dispatch_v6(
    request: str,
    *,
    raw_argument: bool = False,
    prelude: str = "",
    report: str = DEFAULT_REPORT,
) -> Any:
    """Call `mcpDispatchV6` once and return the decoded report.

    `request` is embedded as a JavaScript string literal unless `raw_argument`
    is set, in which case it is inserted as a bare expression — that is how a
    non-string argument (`undefined`, a number, an object) is delivered.
    """
    argument = request if raw_argument else json.dumps(request)
    epilogue = "\n".join([
        f"var REQUEST = {argument};",
        prelude,
        f"var HARNESS_OUT = {report};",
        "process.stdout.write(JSON.stringify(HARNESS_OUT));",
    ])
    return run_engine(epilogue)
