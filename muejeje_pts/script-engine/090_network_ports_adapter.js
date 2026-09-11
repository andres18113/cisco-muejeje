/*
 * Muejeje runtime — one workspace device's ports, in the same reading as its
 * identity. READ-ONLY.
 *
 * A declared adapter (MJ-006, MJ-019, MJ-031). It selects one device on the
 * workspace, reads what that device says it is, and reads that same device's
 * ports — and reports all of it as one observation, without deciding what any
 * of it establishes (MJ-011).
 *
 * It names no platform object. Every call goes through the boundary in
 * `060_platform_adapter.js`, which admits only the read-only interface members on
 * its list.
 *
 * ONE OBSERVATION, SO THE PORTS ARE ATTRIBUTABLE. A workspace changes between
 * readings and a position is not an identity: the device at position 3 now need
 * not be the device that stood there when `network.device_identity` was asked.
 * A consumer that joined an identity read at one moment with ports read at
 * another would be describing a device that may never have existed in that
 * state. So the identity needed to say *whose* ports these are — the name and
 * the model — is read again here, off the very device the ports are read from,
 * after one hand-over, in the same call. That is snapshot consistency, not
 * duplication: the two operations answer different questions, and neither is
 * ever completed out of the other.
 *
 * The DeviceType is deliberately not re-read. It is not needed to attribute a
 * port, and `Device.getType()` has less standing than the name and the model —
 * documented, and observed on no channel — so including it would make every
 * port reading all-or-nothing on the weakest getter in it.
 *
 * THE PORT WINDOW IS BOUNDED, AND SAYS SO. How many ports a device has is the
 * platform's answer; how many one reading carries is Muejeje's
 * (`MAX_PORT_WINDOW`). A device with more is read one window at a time from
 * `port_offset`, and a window that stops short of the count reports
 * `window_truncated`. Each page is its own observation, and carries the
 * identity it was read with.
 *
 * A PORT INDEX IS A POSITION, NOT A NAME AND NOT AN IDENTITY. `port_index` is
 * the argument the port was handed over at, in this reading, and nothing more.
 * The name is what the platform called the port; nothing here parses it into a
 * slot, a module or a kind (MJ-002, MJ-014).
 *
 * NOTHING HERE FOLLOWS A LINK, READS AN ADDRESS OR A STATE, OR MUTATES. `Port`
 * offers members that return its link and the device at the other end, its
 * addresses and whether it is up, and members that set its bandwidth, duplex,
 * clock rate and addresses; none of them is on the boundary's list, so this
 * file could not reach one if it tried. A link is topology, and topology is
 * what this runtime reads nothing into (MJ-002, MJ-031). Nor does it relate the
 * device to the hardware factory: a `workspace_index` is not a `factory_index`,
 * and a model string is not a descriptor.
 */

/* One result shape for every outcome, so a consumer parses one thing whether
 * the platform answered or not. It starts with every fact empty: a field is
 * filled in only once it was read, in this reading, so nothing this adapter
 * never obtained can be left looking like an answer. */
function muejejeAdapterPortsReading(resolution, reason, workspaceIndex, window) {
    return {
        resolution: resolution,
        unavailable_reason: reason,
        workspace_index: workspaceIndex,
        available_count: null,
        device_present: false,
        name: null,
        model: null,
        port_offset: window.offset,
        limit: window.limit,
        port_count: null,
        ports: [],
        window_truncated: false
    };
}

function muejejeAdapterPortsUnavailable(reason, workspaceIndex, window) {
    return muejejeAdapterPortsReading(
        MUEJEJE_PLATFORM_UNAVAILABLE, reason, workspaceIndex, window
    );
}

/* The one entry point. An unreadable platform is an observation about the
 * platform, not an exception for the caller; an argument outside this adapter's
 * own bounds is a defect in this artifact, and fails as one (MJ-022, MJ-031).
 *
 * Both positions are bounded by the exact-integer limit: the domain
 * `network.device_inventory` publishes the device's position in, and the one
 * this reading publishes each `port_index` in. So every position either reading
 * hands out is one this adapter admits back (MJ-029). */
function muejejeAdapterDevicePorts(workspaceIndex, portOffset, limit) {
    var index = muejejeReadingArgument(
        workspaceIndex, 0, MUEJEJE_PLATFORM_LIMITS.EXACT_INTEGER_MAX
    );
    var window = {
        offset: muejejeReadingArgument(
            portOffset, 0, MUEJEJE_PLATFORM_LIMITS.EXACT_INTEGER_MAX
        ),
        limit: muejejeReadingArgument(
            limit, 1, MUEJEJE_PLATFORM_LIMITS.MAX_PORT_WINDOW
        )
    };
    var platform = muejejeAdapterPlatform();
    if (platform === null) {
        return muejejeAdapterPortsUnavailable(
            MUEJEJE_PLATFORM_ABSENT, index, window
        );
    }
    try {
        return muejejeAdapterPortsRead(platform, index, window);
    } catch (platformError) {
        return muejejeAdapterPortsUnavailable(
            muejejeReadingReason(platformError), index, window
        );
    }
}

/* A position past the end is an answer, not a failure: the workspace said how
 * many devices it holds, in this same reading, and holds none there. */
function muejejeAdapterPortsRead(platform, index, window) {
    var network = muejejeAdapterCall(platform, "IPC.network");
    var reading = muejejeAdapterPortsReading(
        MUEJEJE_PLATFORM_OBSERVED, null, index, window
    );
    reading.available_count = muejejeReadingCount(
        muejejeAdapterCall(network, "Network.getDeviceCount")
    );
    if (index >= reading.available_count) {
        return reading;
    }
    return muejejeAdapterPortsOfDevice(
        reading, muejejeAdapterCallWith(network, "Network.getDeviceAt", index),
        window
    );
}

/* The identity first, then the ports, all off the one device handed over. A
 * device inside the count that the platform will not hand over cannot be
 * attributed, exactly as it cannot be for the identity reading. The window
 * alone bounds how many ports are read (MJ-029). */
function muejejeAdapterPortsOfDevice(reading, device, window) {
    if (!device) {
        throw MUEJEJE_PLATFORM_UNUSABLE;
    }
    reading.device_present = true;
    reading.name = muejejeReadingText(
        muejejeAdapterCall(device, "Device.getName"),
        MUEJEJE_PLATFORM_LIMITS.MAX_NAME_CHARS
    );
    reading.model = muejejeReadingText(
        muejejeAdapterCall(device, "Device.getModel"),
        MUEJEJE_PLATFORM_LIMITS.MAX_MODEL_CHARS
    );
    reading.port_count = muejejeReadingCount(
        muejejeAdapterCall(device, "Device.getPortCount")
    );
    var last = Math.min(reading.port_count, window.offset + window.limit);
    for (var position = window.offset; position < last; position++) {
        reading.ports.push(muejejeAdapterPort(device, position));
    }
    reading.window_truncated = reading.port_count > last;
    return reading;
}

/* One port: the position it was handed over at, and the name the platform gave
 * it. A port inside the count that the platform will not hand over is a hole,
 * and a hole is not an absence — reporting fewer ports would invent an answer. */
function muejejeAdapterPort(device, position) {
    var port = muejejeAdapterCallWith(device, "Device.getPortAt", position);
    if (!port) {
        throw MUEJEJE_PLATFORM_UNUSABLE;
    }
    return {
        port_index: position,
        name: muejejeReadingText(
            muejejeAdapterCall(port, "Port.getName"),
            MUEJEJE_PLATFORM_LIMITS.MAX_NAME_CHARS
        )
    };
}
