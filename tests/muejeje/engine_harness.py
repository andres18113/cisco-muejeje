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


# One chassis shape this repository actually recorded against 9.0.1.0858 — a
# generic access point: a root reporting `model: ""` with slot types [6, 18],
# carrying a repeater module and one non-removable module
# (`docs/reference/cp-scale/ROUTER0_POE_FACTORY_STRUCTURE_20260907.md`). It is
# here so two test modules cannot drift into describing two different chassis,
# and it is still stub input: a shape read from a recording is the least
# misleading kind, and remains a claim about our code (MJ-015).
ACCESS_POINT_ROOT = (
    "{model: '', module_type: 18, hot_swappable: false, slot_types: [6, 18],"
    " modules: ["
    "{model: 'PT-REPEATER-NM-1CFE', module_type: 6, hot_swappable: false,"
    " slot_types: [], modules: []},"
    "{model: '', module_type: 18, hot_swappable: false,"
    " slot_types: [], modules: []}]}"
)
CHASSIS_MODELS = (
    "[{model: 'AccessPoint-PT', type: 7, supported: true, module_types: [6],"
    f" root: {ACCESS_POINT_ROOT}}},"
    " {model: 'bare', type: 1, supported: true, module_types: []}]"
)


def _module_descriptor_js() -> list[str]:
    """The `ModuleDescriptor` getters, as Cisco's reference names them."""
    return [
        "function moduleDescriptor(node) {",
        "  return {",
        "    getModel: function () { log('getModel'); return node.model; },",
        "    getType: function () { log('getType'); return node.module_type; },",
        "    isHotSwappable: function () {",
        "      log('isHotSwappable'); return node.hot_swappable;",
        "    },",
        "    getSlotCount: function () {",
        "      log('getSlotCount'); return node.slot_types.length;",
        "    },",
        "    getSlotTypeAt: function (index) {",
        "      log('getSlotTypeAt'); return node.slot_types[index];",
        "    },",
        "    getModuleCount: function () {",
        "      log('getModuleCount');",
        "      return node.module_count === undefined",
        "        ? node.modules.length : node.module_count;",
        "    },",
        "    getModuleAt: function (index) {",
        "      log('getModuleAt');",
        "      return node.modules[index]",
        "        ? moduleDescriptor(node.modules[index]) : null;",
        "    }",
        "  };",
        "}",
    ]


def _device_descriptor_js() -> list[str]:
    """The `DeviceDescriptor` getters, including the root of its chassis."""
    return [
        "function descriptor(spec) {",
        "  return {",
        "    getRootModule: function () {",
        "      log('getRootModule');",
        "      return spec.root ? moduleDescriptor(spec.root) : null;",
        "    },",
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
    ]


def _factory_js(reported: str, refuses: str) -> list[str]:
    """The factory enumeration, and the platform object that answers for it."""
    return [
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
    ]


def platform_stub(models: str, *, count: str | None = None, fail: bool = False) -> str:
    """A platform stub built from the documented getters, plus a call log.

    It is a *stub*, and it stays one: it establishes what an adapter does with
    a well-formed answer and nothing whatever about Packet Tracer, whose engine
    and hardware factory are a different implementation (MJ-015). The call log
    is what stops it from quietly becoming evidence about the platform — the
    caller compares the recorded calls against Cisco's documented getters, so
    an undocumented call fails here rather than on a target.

    `models` is a JavaScript array literal of
    `{model, type, supported, module_types}` objects, each optionally carrying
    `root`: a chassis-module tree of
    `{model, module_type, hot_swappable, slot_types, modules}` nodes, where a
    `null` entry in `modules` makes `getModuleAt` answer nothing at that index,
    and `module_count` overrides what `getModuleCount()` answers. `count` overrides what
    `getAvailableDeviceCount()` answers, which is how an unusable answer is
    delivered; `fail` makes the first platform call throw, which is how a
    denied or otherwise refused call is delivered.
    """
    return "\n".join([
        f"var MODELS = {models};",
        "var CALLS = [];",
        "function log(name) { CALLS.push(name); }",
        *_module_descriptor_js(),
        *_device_descriptor_js(),
        *_factory_js("MODELS.length" if count is None else count,
                     "true" if fail else "false"),
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
