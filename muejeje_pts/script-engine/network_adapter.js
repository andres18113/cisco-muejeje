/*
 * Muejeje runtime — the workspace device inventory. READ-ONLY.
 *
 * A declared adapter (MJ-006, MJ-019, MJ-031), and the first that reads the
 * *workspace* rather than the hardware factory: how many devices this Packet
 * Tracer currently has, and what each one is called.
 *
 * IT READS AN INVENTORY, NOT A TOPOLOGY. It reports the devices the platform
 * lists and stops there. It assumes no count, no naming scheme, no role, no
 * ordering that outlives one reading, and it reads no link, address, port or
 * configuration — none of which it would know what to do with. Reporting what
 * is there is not assuming what is there, which is the whole of MJ-002: a
 * runtime that expected a topology would have become part of one consumer's.
 *
 * A WORKSPACE CHANGES, AND THE FACTORY DOES NOT. Every earlier reading in this
 * artifact describes what a *model* can be; this one describes what a session
 * happens to hold right now, so two readings may legitimately differ with
 * nothing wrong. It is an observation at a moment, never a fact about "the
 * network", and nothing here caches one.
 *
 * NOTHING HERE MUTATES ANYTHING. The same `Network` interface offers members
 * that create a device or a link; none of them is on the boundary's read-only
 * allowlist, so this file could not reach one if it tried — which is exactly
 * what an allowlist is for (MJ-031).
 *
 * It names no platform object: every call goes through `muejejeAdapterCall` in
 * `platform_adapter.js`.
 */

/* One result shape for every outcome, so a consumer parses one thing whether
 * the platform answered or not. */
function muejejeAdapterInventoryUnavailable(reason, offset, limit) {
    return {
        resolution: MUEJEJE_PLATFORM_UNAVAILABLE,
        unavailable_reason: reason,
        available_count: null,
        offset: offset,
        limit: limit,
        devices: [],
        window_truncated: false
    };
}

/* The requested window, checked rather than clamped: a value outside these
 * bounds reached this adapter from our own code (MJ-029). */
function muejejeAdapterInventoryWindow(offset, limit) {
    return {
        offset: muejejeReadingArgument(
            offset, 0, MUEJEJE_PLATFORM_LIMITS.MAX_OFFSET
        ),
        limit: muejejeReadingArgument(
            limit, 1, MUEJEJE_PLATFORM_LIMITS.MAX_DEVICE_WINDOW
        )
    };
}

/* The one entry point. An unreadable platform is an observation about the
 * platform, not an exception for the caller. */
function muejejeAdapterDeviceInventory(offset, limit) {
    var window = muejejeAdapterInventoryWindow(offset, limit);
    var platform = muejejeAdapterPlatform();
    if (platform === null) {
        return muejejeAdapterInventoryUnavailable(
            MUEJEJE_PLATFORM_ABSENT, window.offset, window.limit
        );
    }
    try {
        return muejejeAdapterInventoryRead(platform, window);
    } catch (platformError) {
        return muejejeAdapterInventoryUnavailable(
            muejejeReadingReason(platformError), window.offset, window.limit
        );
    }
}

function muejejeAdapterInventoryRead(platform, window) {
    var network = muejejeAdapterCall(platform, "network");
    var count = muejejeReadingCount(
        muejejeAdapterCall(network, "getDeviceCount")
    );
    var last = Math.min(count, window.offset + window.limit);
    var devices = [];
    for (var index = window.offset; index < last; index++) {
        devices.push(muejejeAdapterInventoryEntry(network, index));
    }
    return {
        resolution: MUEJEJE_PLATFORM_OBSERVED,
        unavailable_reason: null,
        available_count: count,
        offset: window.offset,
        limit: window.limit,
        devices: devices,
        window_truncated: count > last
    };
}

/* One device: the index it was read at, and the name the platform gave for it.
 *
 * The index is not an identity — a workspace can change between readings, and
 * nothing here claims otherwise — so it is reported as what it is: where this
 * device was in this reading. A device inside the count that the platform will
 * not hand over is an answer that cannot be attributed, exactly as a missing
 * descriptor inside the device count is. */
function muejejeAdapterInventoryEntry(network, index) {
    var device = muejejeAdapterCallAt(network, "getDeviceAt", index);
    if (!device) {
        throw MUEJEJE_PLATFORM_UNUSABLE;
    }
    return {
        index: index,
        name: muejejeReadingText(
            muejejeAdapterCall(device, "getName"),
            MUEJEJE_PLATFORM_LIMITS.MAX_NAME_CHARS
        )
    };
}
