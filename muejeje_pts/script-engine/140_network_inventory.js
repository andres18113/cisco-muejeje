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
 * bounds. `workspace_offset` is bounded only by the exact-integer limit, so a
 * workspace of any size is paged one window at a time (MJ-029).
 *
 * `workspace_offset` names the enumeration it addresses, so a position read
 * from the factory cannot be sent here by the name it was published under, and
 * a workspace position cannot be sent to the factory. */
var MUEJEJE_NETWORK_INVENTORY_ARGS = {
    workspace_offset: {
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

/* An omitted argument is a default, never a refusal, and each default is the
 * origin of what is read: a consumer reading a workspace for the first time
 * has no count to page from yet (MJ-029). */
function muejejeNetworkDeviceInventory(args, context) {
    return muejejeAdapterDeviceInventory(
        muejejeV6OptionalArgument(args, "workspace_offset", 0),
        muejejeV6OptionalArgument(
            args, "limit", MUEJEJE_PLATFORM_LIMITS.MAX_WORKSPACE_WINDOW
        )
    );
}
