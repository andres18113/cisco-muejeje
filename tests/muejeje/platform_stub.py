"""The platform this repository hands its kernel offline, and nothing more.

A **stub**, and it stays one. It establishes what an adapter does with an answer
of a given shape and nothing whatever about Packet Tracer, whose engine and
hardware factory are a different implementation (MJ-015). The call log is what
stops it from quietly becoming evidence about the platform: a caller compares
the recorded calls against the members this repository can cite, so an
uncited call fails here rather than on a target (`AGENTS.md` rule 6).

**Every object logs the interface it plays, not only the member.** A call is an
interface member (MJ-031): `getModel` on a workspace device and `getModel` on a
factory descriptor are two contracts with two citations, and a log of bare
names would let one stand in for the other. So every entry is written
`Interface.member`, by the object that implements that interface.

Every fixture lives here rather than in the modules that use it, so two test
modules cannot drift into describing two different chassis or two different
workspaces — and so a shape read from a recording stays one shape. Split out of
`engine_harness` at its line budget: running the kernel and building a platform
for it to talk to are two responsibilities; the workspace half of the platform
was split again into `workspace_stub` at this module's own (MJ-018, MJ-020).
"""

from __future__ import annotations

from tests.muejeje.workspace_stub import workspace_js

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
        "    getModel: function () {",
        "      log('ModuleDescriptor.getModel'); return node.model;",
        "    },",
        "    getType: function () {",
        "      log('ModuleDescriptor.getType'); return node.module_type;",
        "    },",
        "    isHotSwappable: function () {",
        "      log('ModuleDescriptor.isHotSwappable'); return node.hot_swappable;",
        "    },",
        "    getSlotCount: function () {",
        "      log('ModuleDescriptor.getSlotCount');",
        "      return node.slot_count === undefined",
        "        ? node.slot_types.length : node.slot_count;",
        "    },",
        "    getSlotTypeAt: function (index) {",
        "      log('ModuleDescriptor.getSlotTypeAt'); return node.slot_types[index];",
        "    },",
        "    getModuleCount: function () {",
        "      log('ModuleDescriptor.getModuleCount');",
        "      return node.module_count === undefined",
        "        ? node.modules.length : node.module_count;",
        "    },",
        "    getModuleAt: function (index) {",
        "      log('ModuleDescriptor.getModuleAt');",
        "      var entry = node.modules[index];",
        "      if (index >= node.modules.length || (entry && entry.throws)) {",
        "        throw new Error('the platform refused this call');",
        "      }",
        "      return entry !== null && typeof entry === 'object'",
        "        ? moduleDescriptor(entry) : entry;",
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
        "      log('DeviceDescriptor.getRootModule');",
        "      return spec.root ? moduleDescriptor(spec.root) : null;",
        "    },",
        "    getModel: function () {",
        "      log('DeviceDescriptor.getModel'); return spec.model;",
        "    },",
        "    getType: function () {",
        "      log('DeviceDescriptor.getType'); return spec.type;",
        "    },",
        "    isModelSupported: function () {",
        "      log('DeviceDescriptor.isModelSupported'); return spec.supported;",
        "    },",
        "    isModuleTypeSupported: function (type) {",
        "      log('DeviceDescriptor.isModuleTypeSupported');",
        "      return spec.module_types.indexOf(type) !== -1;",
        "    },",
        "    getSupportedModuleTypeCount: function () {",
        "      log('DeviceDescriptor.getSupportedModuleTypeCount');",
        "      return spec.module_types.length;",
        "    },",
        "    getSupportedModuleTypeAt: function (index) {",
        "      log('DeviceDescriptor.getSupportedModuleTypeAt');",
        "      return spec.module_types[index];",
        "    }",
        "  };",
        "}",
    ]


def _factory_js(reported: str, refuses: str, dense: bool) -> list[str]:
    """The factory enumeration, and the platform object that answers for it."""
    pick = "MODELS[index % MODELS.length]" if dense else "MODELS[index]"
    return [
        "var FACTORY = {",
        "  getAvailableDeviceCount: function () {",
        f"    log('DeviceFactory.getAvailableDeviceCount'); return {reported};",
        "  },",
        "  getAvailableDeviceAt: function (index) {",
        "    log('DeviceFactory.getAvailableDeviceAt');",
        f"    var spec = {pick};",
        "    return spec ? descriptor(spec) : null;",
        "  }",
        "};",
        "var ipc = {hardwareFactory: function () {",
        "  log('IPC.hardwareFactory');",
        f"  if ({refuses}) {{",
        "    throw new Error('the platform refused this call');",
        "  }",
        "  return {devices: function () {",
        "    log('HardwareFactory.devices'); return FACTORY;",
        "  }};",
        "}, network: function () { log('IPC.network'); return NETWORK; }};",
    ]


# A workspace whose devices answer the identity getters as well as the name, and
# the models a relay-closure gate needs: types at both ends of the published
# domain, and a chassis whose own type and slot types are there too. They live
# here for the same reason `CHASSIS_MODELS` does, and they are still stub input,
# which is a claim about our code and never about the platform.
IDENTITY_DEVICES = (
    "[{name: 'a', model: 'PT-Router', device_type: 1, object_uuid: 'uuid-a'},"
    " {name: 'b', model: '', device_type: 7, object_uuid: 'uuid-b'}]"
)
# The same workspace with ports: named ones and an unnamed one on the first
# device, and none on the second, so an empty port list is a reading too.
PORT_DEVICES = (
    "[{name: 'a', model: 'PT-Router', device_type: 1, object_uuid: 'uuid-a',"
    " ports: [{name: 'port-0', object_uuid: 'uuid-a-0'},"
    " {name: 'port-1', object_uuid: 'uuid-a-1'}, {name: '', object_uuid: ''}]},"
    " {name: 'b', model: '', device_type: 7, object_uuid: 'uuid-b', ports: []}]"
)
# A workspace of two devices joined by two links. Every UUID is distinct, so a
# correlation that matched the wrong object could not pass by coincidence, and
# the connection types are arbitrary: the platform's own numbers, which nothing
# may read a medium into (MJ-014). `ends` are `[device, port]` positions.
LINKED_DEVICES = (
    "[{name: 'a', model: 'model-a', device_type: 1, object_uuid: 'device-uuid-a',"
    " ports: [{name: 'a-0', object_uuid: 'port-uuid-a0'},"
    " {name: 'a-1', object_uuid: 'port-uuid-a1'}]},"
    " {name: 'b', model: 'model-b', device_type: 2, object_uuid: 'device-uuid-b',"
    " ports: [{name: 'b-0', object_uuid: 'port-uuid-b0'},"
    " {name: 'b-1', object_uuid: 'port-uuid-b1'}]}]"
)
LINKS = (
    "[{connection_type: 5, object_uuid: 'link-uuid-0', ends: [[0, 0], [1, 1]]},"
    " {connection_type: 6, object_uuid: 'link-uuid-1', ends: [[1, 0], [0, 1]]}]"
)
# The last whole number JSON carries exactly. Written out rather than read
# from the kernel, so a fixture cannot move with the bound it exists to test;
# `test_relay_closure` holds the two equal.
EXACT_INTEGER_END = 9007199254740991
EXTREME_ROOT = (
    f"{{model: 'root', module_type: -{EXACT_INTEGER_END}, hot_swappable: false,"
    f" slot_types: [0, {EXACT_INTEGER_END}], modules: []}}"
)
EXTREME_MODELS = (
    "[{model: 'wide', type: 1, supported: true,"
    f" module_types: [-{EXACT_INTEGER_END}, 0, {EXACT_INTEGER_END}],"
    f" root: {EXTREME_ROOT}}}]"
)


def identity_stub(**kwargs) -> str:
    """The workspace stub, whose devices answer the identity getters too."""
    return platform_stub(CHASSIS_MODELS, devices=IDENTITY_DEVICES, **kwargs)


def linked_stub(models: str = CHASSIS_MODELS, **kwargs) -> str:
    """A factory and the linked workspace, so every reading has something to read."""
    return platform_stub(models, devices=LINKED_DEVICES, links=LINKS, **kwargs)


def platform_stub(
    models: str,
    *,
    count: str | None = None,
    fail: bool = False,
    devices: str = (
        "[{name: 'n1', object_uuid: 'u1'}, {name: 'n2', object_uuid: 'u2'},"
        " {name: 'n3', object_uuid: 'u3'}]"
    ),
    device_count: str | None = None,
    links: str = "[]",
    link_count: str | None = None,
    dense: bool = False,
) -> str:
    """A platform stub built from the cited getters, plus a call log.

    `models` is a JavaScript array literal of
    `{model, type, supported, module_types}` objects, each optionally carrying
    `root`: a tree of `{model, module_type, hot_swappable, slot_types, modules}`
    nodes. An entry of `modules` that is not an object — `null`, `undefined`, a
    primitive — is what `getModuleAt` answers there, as it is; `{throws: true}`,
    or a position past the list, makes that call throw, so a hole never reads as
    a null. `module_count`, `slot_count` and `count` override `getModuleCount()`,
    `getSlotCount()` and `getAvailableDeviceCount()`; `fail` makes the first
    factory call throw.

    `devices` and `links` are the workspace `Network` enumerates, as
    `workspace_stub` builds it: a `null` entry is one the platform will not hand
    over, and `device_count` and `link_count` override the two counts. `dense`
    makes every enumeration answer at *every* index by cycling its list.
    """
    return "\n".join([
        f"var MODELS = {models};",
        f"var DEVICES = {devices};",
        f"var LINKS = {links};",
        "var CALLS = [];",
        "function log(name) { CALLS.push(name); }",
        *_module_descriptor_js(),
        *_device_descriptor_js(),
        *workspace_js(
            dense=dense,
            devices="DEVICES.length" if device_count is None else device_count,
            links="LINKS.length" if link_count is None else link_count,
        ),
        *_factory_js("MODELS.length" if count is None else count,
                     "true" if fail else "false", dense),
    ])
