/*
 * Muejeje runtime — the `network.device_ports` operation.
 *
 * Read-only. It answers one question — *what ports does the device at this
 * position have, and which device is that* — and it answers it by asking the
 * platform through the declared adapter. It names no platform symbol itself:
 * the arrow points operation -> adapter -> boundary -> platform, and never back
 * (MJ-019).
 *
 * ONE OBSERVATION. The device is selected, what it says it is is read, and its
 * ports are read off that same device, in one call, and reported together. A
 * consumer never has to combine `network.device_identity` from one moment with
 * a port reading from another to know whose ports these are, and no answer
 * here is completed out of another operation's (MJ-031).
 *
 * THE ARGUMENTS ARE POSITIONS. `workspace_index` is where to look on the
 * workspace in this reading, and `port_offset` where to start among that
 * device's ports. Neither is stable across readings, and neither is a name —
 * which is what keeps this generic: no consumer's device or interface names
 * live in the runtime (MJ-002, MJ-004).
 *
 * It reaches no verdict. `resolution` says whether a reading was obtained, not
 * what it establishes — Python decides that from outside the artifact (MJ-011).
 */

/* The arguments this operation admits, and the rule each value must satisfy.
 * Declared here, by the operation they belong to, and handed to the dispatcher
 * — which owns *which* operations exist, not what each one's arguments mean.
 *
 * `workspace_index` is REQUIRED: every position holds a different device, so no
 * default could be honest, and a request that names none is refused before
 * anything is read (MJ-029). It is bounded by the exact-integer limit, the
 * domain `network.device_inventory` publishes positions in.
 *
 * `port_offset` and `limit` are the port window, and both have honest defaults:
 * the start of the device's ports, and the widest window this runtime reads.
 * `port_offset` is bounded only by the exact-integer limit — the domain this
 * reading publishes `port_index` in — so a device with more ports than one
 * window is paged as far as its ports go. Its name keeps it apart from a
 * workspace or a factory offset, so neither can be relayed here by accident. */
var MUEJEJE_NETWORK_PORTS_ARGS = {
    workspace_index: {
        kind: "integer",
        required: true,
        min: 0,
        max: MUEJEJE_PLATFORM_LIMITS.EXACT_INTEGER_MAX
    },
    port_offset: {
        kind: "integer",
        min: 0,
        max: MUEJEJE_PLATFORM_LIMITS.EXACT_INTEGER_MAX
    },
    limit: {
        kind: "integer",
        min: 1,
        max: MUEJEJE_PLATFORM_LIMITS.MAX_PORT_WINDOW
    }
};

function muejejeNetworkDevicePorts(args, context) {
    return muejejeAdapterDevicePorts(
        muejejeV6RequiredArgument(args, "workspace_index"),
        muejejeV6OptionalArgument(args, "port_offset", 0),
        muejejeV6OptionalArgument(
            args, "limit", MUEJEJE_PLATFORM_LIMITS.MAX_PORT_WINDOW
        )
    );
}
