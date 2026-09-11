/*
 * Muejeje runtime — the `network.device_inventory` operation.
 *
 * Read-only. It answers one question — *what devices does this Packet Tracer
 * currently hold* — and it answers it by asking the platform through the
 * declared adapter. It names no platform symbol itself: the arrow points
 * operation -> adapter -> boundary -> platform, and never back (MJ-019).
 *
 * This is the first operation in the `network` namespace, and the first that
 * reads a workspace rather than the hardware factory. It reports an inventory
 * and assumes no topology: no count, no naming scheme, no role, no link, no
 * address (MJ-002, MJ-004). A consumer that wants to know what is there asks;
 * it is never told what ought to be there.
 *
 * A workspace changes under a reading in a way a factory catalogue does not, so
 * the answer is an observation at a moment. `resolution` says whether a reading
 * was obtained, and nothing in it says the workspace still looks like this
 * (MJ-011).
 */

/* Both arguments are optional, and bounded by the adapter's own declarations
 * rather than by a second set of numbers here: two copies of a bound are two
 * bounds. `offset` is bounded only by the exact-integer limit, so a workspace
 * of any size is paged one window at a time (MJ-029). */
var MUEJEJE_NETWORK_INVENTORY_ARGS = {
    offset: {
        kind: "integer",
        min: 0,
        max: MUEJEJE_PLATFORM_LIMITS.EXACT_INTEGER_MAX
    },
    limit: {
        kind: "integer",
        min: 1,
        max: MUEJEJE_PLATFORM_LIMITS.MAX_WORKSPACE_WINDOW
    }
};

/* An omitted argument is a default, never a refusal: a consumer reading a
 * workspace for the first time has no count to page from yet. */
function muejejeNetworkDeviceInventory(args, context) {
    return muejejeAdapterDeviceInventory(
        muejejeNetworkArgument(args, "offset", 0),
        muejejeNetworkArgument(
            args, "limit", MUEJEJE_PLATFORM_LIMITS.MAX_WORKSPACE_WINDOW
        )
    );
}

/* V6 admission has already checked every supplied argument against the rule
 * above, so a value present here is within its bounds. This only decides
 * whether it was supplied at all. */
function muejejeNetworkArgument(args, name, fallback) {
    if (
        args === null || typeof args !== "object"
        || !Object.prototype.hasOwnProperty.call(args, name)
    ) {
        return fallback;
    }
    return args[name];
}
