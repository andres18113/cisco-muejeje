"""The workspace a platform stub hands the kernel: devices, ports and links.

Split out of `platform_stub` when the first link reading pushed that module past
its line budget (MJ-018, MJ-020). Building the hardware factory and building a
workspace are two responsibilities, and the fixtures both are driven with stay
in `platform_stub`, so two test modules still cannot drift into two workspaces.

A **stub**, and it stays one: it establishes what an adapter does with an answer
of a given shape and nothing about Packet Tracer (MJ-015). Every object logs the
interface it plays, as `Interface.member`, so a call nobody can cite fails in
the call-log gates rather than on a target (`AGENTS.md` rule 6).

**An object offers a getter only for a field its spec carries**, so a fixture
never answers a question nobody put to it — and a link spec without `ends` is
exactly the object a reading must report as not offering its endpoints, never
as a link without any. **Every hand-over builds a fresh wrapper**, as Packet
Tracer's does, so no reading can rest on two hand-overs of one platform object
being the same JavaScript object.
"""

from __future__ import annotations


def _port_js() -> list[str]:
    """A port, and the device that owns it; `orphan` makes its owner absent."""
    return [
        "function workspacePort(spec, owner) {",
        "  var port = {getName: function () { log('Port.getName'); return spec.name; }};",
        "  if ('object_uuid' in spec) {",
        "    port.getObjectUuid = function () {",
        "      log('Port.getObjectUuid'); return spec.object_uuid;",
        "    };",
        "  }",
        "  port.getOwnerDevice = function () {",
        "    log('Port.getOwnerDevice');",
        "    return spec.orphan ? null : workspaceDevice(owner);",
        "  };",
        "  return port;",
        "}",
    ]


def _device_js() -> list[str]:
    """A workspace device: `port_count` overrides `getPortCount()`, a `null` port
    is one the platform will not hand over, and `dense_ports` cycles the list."""
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
        "  if ('object_uuid' in spec) {",
        "    device.getObjectUuid = function () {",
        "      log('Device.getObjectUuid'); return spec.object_uuid;",
        "    };",
        "  }",
        "  if ('ports' in spec) {",
        "    device.getPortCount = function () {",
        "      log('Device.getPortCount');",
        "      return 'port_count' in spec ? spec.port_count : spec.ports.length;",
        "    };",
        "    device.getPortAt = function (index) {",
        "      log('Device.getPortAt');",
        "      var port = spec.dense_ports",
        "        ? spec.ports[index % spec.ports.length] : spec.ports[index];",
        "      return port ? workspacePort(port, spec) : null;",
        "    };",
        "  }",
        "  return device;",
        "}",
    ]


def _link_js() -> list[str]:
    """A link. `ends` holds `[device position, port position]` pairs into
    `DEVICES`, so an end is handed over as the very port a device reading reads
    there; a `null` end is one the platform will not hand over."""
    return [
        "function workspaceEnd(end) {",
        "  if (end === null) { return null; }",
        "  var owner = DEVICES[end[0]];",
        "  return workspacePort(owner.ports[end[1]], owner);",
        "}",
        "function workspaceLink(spec) {",
        "  var link = {getConnectionType: function () {",
        "    log('Link.getConnectionType'); return spec.connection_type;",
        "  }};",
        "  if ('object_uuid' in spec) {",
        "    link.getObjectUuid = function () {",
        "      log('Link.getObjectUuid'); return spec.object_uuid;",
        "    };",
        "  }",
        "  if ('ends' in spec) {",
        "    link.getPort1 = function () {",
        "      log('Link.getPort1'); return workspaceEnd(spec.ends[0]);",
        "    };",
        "    link.getPort2 = function () {",
        "      log('Link.getPort2'); return workspaceEnd(spec.ends[1]);",
        "    };",
        "  }",
        "  return link;",
        "}",
    ]


def workspace_js(*, dense: bool, devices: str, links: str) -> list[str]:
    """`Network` and everything it enumerates, as this repository drives it.

    `devices` and `links` are what `getDeviceCount()` and `getLinkCount()`
    report. `dense` cycles both lists, so the workspace answers at every
    position and a reading can be driven at the far end of an address domain.
    """
    device = "DEVICES[index % DEVICES.length]" if dense else "DEVICES[index]"
    link = "LINKS[index % LINKS.length]" if dense else "LINKS[index]"
    return [
        *_port_js(),
        *_device_js(),
        *_link_js(),
        "var NETWORK = {",
        "  getDeviceCount: function () {",
        f"    log('Network.getDeviceCount'); return {devices};",
        "  },",
        "  getDeviceAt: function (index) {",
        "    log('Network.getDeviceAt');",
        f"    var spec = {device};",
        "    return spec ? workspaceDevice(spec) : null;",
        "  },",
        "  getLinkCount: function () {",
        f"    log('Network.getLinkCount'); return {links};",
        "  },",
        "  getLinkAt: function (index) {",
        "    log('Network.getLinkAt');",
        f"    var spec = {link};",
        "    return spec ? workspaceLink(spec) : null;",
        "  }",
        "};",
    ]
