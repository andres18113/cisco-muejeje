/*
 * Muejeje runtime — the `network.link_inventory` operation.
 *
 * Read-only. It answers one question — *which links does this workspace hold
 * right now* — by asking the platform through the declared adapter, and names
 * no platform symbol of its own (MJ-019).
 *
 * LINKS ARE THEIR OWN ENUMERATION. `workspace_link_offset`, and the
 * `workspace_link_index` each entry is published at, are positions among the
 * workspace's links and never among its devices, so neither shares a name with
 * `workspace_offset` or `workspace_index`: a position relayed by the name it was
 * published under reaches only the enumeration it came from (MJ-029).
 *
 * It reports what is there and assumes nothing about it — no count, no medium,
 * no pairing of devices — and a link that exists is not a link that converged
 * (MJ-002). `resolution` says whether a reading was obtained, not what it
 * establishes (MJ-011).
 */

/* Both arguments are optional. Each default is the origin of what is read, and
 * each bound is a declaration rather than a second number written here:
 * `workspace_link_offset` only by the exact-integer limit, so a workspace of
 * any size is paged one window at a time (MJ-029). */
var MUEJEJE_NETWORK_LINK_INVENTORY_ARGS = {
    workspace_link_offset: {
        kind: "integer",
        min: 0,
        max: MUEJEJE_PLATFORM_LIMITS.EXACT_INTEGER_MAX
    },
    limit: {
        kind: "integer",
        min: 1,
        max: MUEJEJE_PLATFORM_LIMITS.MAX_LINK_WINDOW
    }
};

function muejejeNetworkLinkInventory(args, context) {
    return muejejeAdapterLinkInventory(
        muejejeV6OptionalArgument(args, "workspace_link_offset", 0),
        muejejeV6OptionalArgument(
            args, "limit", MUEJEJE_PLATFORM_LIMITS.MAX_LINK_WINDOW
        )
    );
}
