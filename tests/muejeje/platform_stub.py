"""The platform this repository hands its kernel offline, and nothing more.

A **stub**, and it stays one. It establishes what an adapter does with an answer
of a given shape and nothing whatever about Packet Tracer, whose engine and
hardware factory are a different implementation (MJ-015). The call log is what
stops it from quietly becoming evidence about the platform: a caller compares
the recorded calls against Cisco's documented members, so an undocumented call
fails here rather than on a target (`AGENTS.md` rule 6).

**Every object logs the interface it plays, not only the member.** A call is an
interface member (MJ-031): `getModel` on a workspace device and `getModel` on a
factory descriptor are two contracts with two citations, and a log of bare
names would let one stand in for the other. So every entry is written
`Interface.member`, by the object that implements that interface.

Every fixture lives here rather than in the modules that use it, so two test
modules cannot drift into describing two different chassis or two different
workspaces — and so a shape read from a recording stays one shape.

Split out of `engine_harness` when that module crossed its own line budget:
running the kernel and building a platform for it to talk to are two
responsibilities (MJ-018, MJ-020).
"""

from __future__ import annotations


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
        "      log('ModuleDescriptor.getSlotCount'); return node.slot_types.length;",
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


def _network_js(dense: bool, reported: str) -> list[str]:
    """`Network` and the devices it enumerates, as this repository drives them.

    A workspace, not a catalogue: the names are neutral on purpose, because a
    stub carrying one topology's device names would be a consumer's identifiers
    living in the test area (MJ-004). `dense` cycles the list so the workspace
    answers at every index, exactly as the factory does.

    A device offers a getter only when its spec carries the field, so a
    fixture never answers a question nobody put to it: an inventory device is
    a name, and an identity device also has a model and a DeviceType.
    """
    pick = "DEVICES[index % DEVICES.length]" if dense else "DEVICES[index]"
    return [
        "function workspaceDevice(spec) {",
        "  var device = {getName: function () {",
        "    log('Device.getName'); return spec.name;",
        "  }};",
        "  if ('model' in spec) {",
        "    device.getModel = function () {",
        "      log('Device.getModel'); return spec.model;",
        "    };",
        "  }",
        "  if ('device_type' in spec) {",
        "    device.getType = function () {",
        "      log('Device.getType'); return spec.device_type;",
        "    };",
        "  }",
        "  return device;",
        "}",
        "var NETWORK = {",
        "  getDeviceCount: function () {",
        f"    log('Network.getDeviceCount'); return {reported};",
        "  },",
        "  getDeviceAt: function (index) {",
        "    log('Network.getDeviceAt');",
        f"    var spec = {pick};",
        "    return spec ? workspaceDevice(spec) : null;",
        "  }",
        "};",
    ]


def _factory_js(reported: str, refuses: str, dense: bool) -> list[str]:
    """The factory enumeration, and the platform object that answers for it.

    `dense` makes it answer at *every* index by cycling the models, which is
    how a reading at the far end of an address domain is driven: with a literal
    array the index under test would be bounded by the stub's length rather
    than by what Muejeje admits.
    """
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


# A workspace whose devices answer the three identity getters as well as the
# name, and the models a relay-closure gate needs: types at both ends of the
# published domain, and a chassis whose own type and slot types are there too.
# They live here for the same reason `CHASSIS_MODELS` does — two test modules
# must not drift into describing two different fixtures — and they are still
# stub input, which is a claim about our code and never about the platform.
IDENTITY_DEVICES = (
    "[{name: 'a', model: 'PT-Router', device_type: 1},"
    " {name: 'b', model: '', device_type: 7}]"
)
EXTREME_ROOT = (
    "{model: 'root', module_type: -1, hot_swappable: false,"
    " slot_types: [0, 70000], modules: []}"
)
EXTREME_MODELS = (
    "[{model: 'wide', type: 1, supported: true,"
    f" module_types: [-1, 0, 70000], root: {EXTREME_ROOT}}}]"
)


def identity_stub(**kwargs) -> str:
    """The workspace stub, whose devices answer the identity getters too.

    A device offers only the getters its spec has fields for, so these answer
    a model and a DeviceType because `IDENTITY_DEVICES` carries both — and an
    inventory fixture, which carries only names, still cannot look as though
    it had been asked for them.
    """
    return platform_stub(CHASSIS_MODELS, devices=IDENTITY_DEVICES, **kwargs)


def platform_stub(
    models: str,
    *,
    count: str | None = None,
    fail: bool = False,
    devices: str = "[{name: 'n1'}, {name: 'n2'}, {name: 'n3'}]",
    device_count: str | None = None,
    dense: bool = False,
) -> str:
    """A platform stub built from the documented getters, plus a call log.

    It is a *stub*, and it stays one: it establishes what an adapter does with
    a well-formed answer and nothing whatever about Packet Tracer, whose engine
    and hardware factory are a different implementation (MJ-015). The call log
    is what stops it from quietly becoming evidence about the platform — the
    caller compares the recorded `Interface.member` calls against Cisco's
    documented members, so an undocumented call fails here rather than on a
    target.

    `models` is a JavaScript array literal of
    `{model, type, supported, module_types}` objects, each optionally carrying
    `root`: a chassis-module tree of
    `{model, module_type, hot_swappable, slot_types, modules}` nodes, where a
    `null` entry in `modules` makes `getModuleAt` answer nothing at that index,
    and `module_count` overrides what `getModuleCount()` answers. `count`
    overrides what `getAvailableDeviceCount()` answers, which is how an
    unusable answer is delivered; `fail` makes the first factory call throw,
    which is how a refused call is delivered. `devices` is the workspace
    `Network` enumerates, as `{name, model?, device_type?}` objects — a device
    offers a getter only for a field it carries, a `null` entry is a device the
    platform will not hand over, and `device_count` overrides what
    `getDeviceCount()` answers.

    `dense` makes both enumerations answer at *every* index by cycling their
    lists, so a reading can be driven at the far end of an address domain.
    """
    return "\n".join([
        f"var MODELS = {models};",
        f"var DEVICES = {devices};",
        "var CALLS = [];",
        "function log(name) { CALLS.push(name); }",
        *_module_descriptor_js(),
        *_device_descriptor_js(),
        *_network_js(
            dense, "DEVICES.length" if device_count is None else device_count,
        ),
        *_factory_js("MODELS.length" if count is None else count,
                     "true" if fail else "false", dense),
    ])
