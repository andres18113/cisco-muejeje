/*
 * Muejeje runtime — the workspace link inventory. READ-ONLY.
 *
 * A declared adapter (MJ-006, MJ-019, MJ-031). It reads how many links this
 * Packet Tracer's workspace currently holds and, one bounded window at a time,
 * what each one reports about itself: the connection type the platform gives it
 * and its object UUID. It names no platform object; every call goes through
 * the boundary in `060_platform_adapter.js`.
 *
 * A LINK POSITION IS ITS OWN ENUMERATION. `workspace_link_index` is the argument
 * `Network.getLinkAt(int)` handed a link over at, in this reading. It is not a
 * device position, not stable across readings and not an identity, and nothing
 * here caches a workspace: two readings may differ with nothing wrong (MJ-002).
 *
 * THE CONNECTION TYPE IS THE PLATFORM'S OWN NUMBER, AND STAYS OPAQUE. Cisco's
 * `Link` page lists names for its values, and names no interface or medium this
 * artifact could rely on for any of them; translating one would be a Cisco enum
 * mirror, correct only until Packet Tracer changes (MJ-014). It is held to the
 * published value domain and reported as it came.
 *
 * NOTHING HERE READS AN END. Which ports a link joins is `network.link_endpoints`,
 * a different subject with its own members: an inventory that also followed
 * every link to its ends would make listing links all-or-nothing on getters the
 * listing does not need. No state is read, and nothing is mutated.
 */

/* One result shape for every outcome. The stage says which `Interface.member`
 * an unavailable reading stopped at; the reason stays what happened there. */
function muejejeAdapterLinkInventoryUnavailable(reason, window) {
    return {
        resolution: MUEJEJE_PLATFORM_UNAVAILABLE,
        unavailable_reason: reason,
        unavailable_member: muejejeReadingStageMember(reason),
        unavailable_argument: muejejeReadingStageArgument(reason),
        available_count: null,
        workspace_link_offset: window.offset,
        limit: window.limit,
        links: [],
        window_truncated: false
    };
}

/* The one entry point. The window is checked rather than clamped: a value
 * outside these bounds reached this adapter from our own code (MJ-029). */
function muejejeAdapterLinkInventory(offset, limit) {
    var window = {
        offset: muejejeReadingArgument(
            offset, 0, MUEJEJE_PLATFORM_LIMITS.EXACT_INTEGER_MAX
        ),
        limit: muejejeReadingArgument(
            limit, 1, MUEJEJE_PLATFORM_LIMITS.MAX_LINK_WINDOW
        )
    };
    var platform = muejejeAdapterPlatform();
    if (platform === null) {
        return muejejeAdapterLinkInventoryUnavailable(MUEJEJE_PLATFORM_ABSENT, window);
    }
    try {
        return muejejeAdapterLinkInventoryRead(platform, window);
    } catch (platformError) {
        return muejejeAdapterLinkInventoryUnavailable(
            muejejeReadingReason(platformError), window
        );
    }
}

/* The window bounds what one reading does, and nothing else here does: every
 * position below the count stays reachable one window at a time (MJ-029). */
function muejejeAdapterLinkInventoryRead(platform, window) {
    var network = muejejeAdapterCall(platform, "IPC.network");
    var count = muejejeReadingCount(
        muejejeAdapterCall(network, "Network.getLinkCount")
    );
    var last = Math.min(count, window.offset + window.limit);
    var links = [];
    for (var index = window.offset; index < last; index++) {
        links.push(muejejeAdapterLinkInventoryEntry(network, index));
    }
    return {
        resolution: MUEJEJE_PLATFORM_OBSERVED,
        unavailable_reason: null,
        unavailable_member: null,
        unavailable_argument: null,
        available_count: count,
        workspace_link_offset: window.offset,
        limit: window.limit,
        links: links,
        window_truncated: count > last
    };
}

/* One link, at the position it was handed over at. A link inside the count the
 * platform will not hand over cannot be attributed: a hole is not an absence. */
function muejejeAdapterLinkInventoryEntry(network, index) {
    var link = muejejeAdapterCallWith(network, "Network.getLinkAt", index);
    if (!link) {
        throw MUEJEJE_PLATFORM_UNUSABLE;
    }
    return {
        workspace_link_index: index,
        connection_type: muejejeReadingExactInteger(
            muejejeAdapterCall(link, "Link.getConnectionType")
        ),
        object_uuid: muejejeReadingText(
            muejejeAdapterCall(link, "Link.getObjectUuid"),
            MUEJEJE_PLATFORM_LIMITS.MAX_OBJECT_UUID_CHARS
        )
    };
}
