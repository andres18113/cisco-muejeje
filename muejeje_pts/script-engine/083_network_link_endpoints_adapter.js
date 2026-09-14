/*
 * Muejeje runtime — one workspace link's two ends, in one reading. READ-ONLY.
 *
 * A declared adapter (MJ-006, MJ-019, MJ-031). It selects one link on the
 * workspace by position, reads what Packet Tracer reports as that link's object
 * UUID, and reads the port at each end — its name, its object UUID and the
 * object UUID of the device that owns it — and reports all of it as one
 * observation, without deciding what any of it establishes (MJ-011).
 *
 * It names no platform object. Every call goes through the boundary in
 * `060_platform_adapter.js`, which admits only the members on its list.
 *
 * THE ENDS ARE READ OFF THE LINK THAT WAS HANDED OVER, AND NOTHING DECIDES WHAT
 * KIND OF LINK IT IS. `Network.getLinkAt(int)` is documented to hand over a
 * `Link`, and the `Link` page documents only its connection type; the endpoint
 * getters are admitted on `Link` because they answered on that object on
 * 9.0.1.0858, not because another interface documents them. No class name is
 * asked, no connection type is looked up in a table and no member is probed,
 * so a link that does not offer an end is `PLATFORM_MEMBER_ABSENT` at
 * `Link.getPort1`, and one whose getter throws is `PLATFORM_CALL_FAILED` there.
 * Neither is a link without ends: reporting that would invent an answer
 * (MJ-014, MJ-022).
 *
 * CORRELATION IS BY WHAT THE PLATFORM REPORTS ON BOTH SIDES. An end's port is
 * related to `network.device_ports`, and its owner to the device readings,
 * through the object UUIDs Packet Tracer answers there — never by a name, a
 * position, or JavaScript reference equality, which two wrappers of one
 * platform object need not satisfy. What a UUID means across a restart, a save
 * or a re-creation has not been observed, and nothing here claims it.
 *
 * NOTHING HERE MUTATES OR READS STATE. A link that exists is not a link that
 * converged, and no address, up/down state or configuration of either port is
 * read.
 */

/* One result shape for every outcome. Every fact starts empty and is filled in
 * only once it was read in this reading, so nothing this adapter never obtained
 * is left looking like an answer — in particular, an unavailable reading never
 * carries one end without the other. */
function muejejeAdapterLinkEndpointsReading(resolution, reason, linkIndex) {
    return {
        resolution: resolution,
        unavailable_reason: reason,
        unavailable_member: muejejeReadingStageMember(reason),
        unavailable_argument: muejejeReadingStageArgument(reason),
        workspace_link_index: linkIndex,
        available_count: null,
        link_present: false,
        object_uuid: null,
        port1: null,
        port2: null
    };
}

function muejejeAdapterLinkEndpointsUnavailable(reason, linkIndex) {
    return muejejeAdapterLinkEndpointsReading(
        MUEJEJE_PLATFORM_UNAVAILABLE, reason, linkIndex
    );
}

/* The one entry point. The position is bounded by the exact-integer limit, the
 * domain `network.link_inventory` publishes it in, so every position that
 * reading hands out is one this adapter admits back (MJ-029). */
function muejejeAdapterLinkEndpoints(workspaceLinkIndex) {
    var index = muejejeReadingArgument(
        workspaceLinkIndex, 0, MUEJEJE_PLATFORM_LIMITS.EXACT_INTEGER_MAX
    );
    var platform = muejejeAdapterPlatform();
    if (platform === null) {
        return muejejeAdapterLinkEndpointsUnavailable(
            MUEJEJE_PLATFORM_ABSENT, index
        );
    }
    try {
        return muejejeAdapterLinkEndpointsRead(platform, index);
    } catch (platformError) {
        return muejejeAdapterLinkEndpointsUnavailable(
            muejejeReadingReason(platformError), index
        );
    }
}

/* A position past the end is an answer: the workspace said how many links it
 * holds, in this same reading, and holds none there. Inside the count the link
 * is handed over once, and both ends are read off that one hand-over. */
function muejejeAdapterLinkEndpointsRead(platform, index) {
    var network = muejejeAdapterCall(platform, "IPC.network");
    var reading = muejejeAdapterLinkEndpointsReading(
        MUEJEJE_PLATFORM_OBSERVED, null, index
    );
    reading.available_count = muejejeReadingCount(
        muejejeAdapterCall(network, "Network.getLinkCount")
    );
    if (index >= reading.available_count) {
        return reading;
    }
    var link = muejejeAdapterCallWith(network, "Network.getLinkAt", index);
    if (!link) {
        throw MUEJEJE_PLATFORM_UNUSABLE;
    }
    reading.link_present = true;
    reading.object_uuid = muejejeReadingText(
        muejejeAdapterCall(link, "Link.getObjectUuid"),
        MUEJEJE_PLATFORM_LIMITS.MAX_OBJECT_UUID_CHARS
    );
    reading.port1 = muejejeAdapterLinkEnd(muejejeAdapterCall(link, "Link.getPort1"));
    reading.port2 = muejejeAdapterLinkEnd(muejejeAdapterCall(link, "Link.getPort2"));
    return reading;
}

/* One end. A link inside the count whose end the platform will not hand over,
 * or whose port names no owner, cannot be attributed — a hole is not an absence. */
function muejejeAdapterLinkEnd(port) {
    if (!port) {
        throw MUEJEJE_PLATFORM_UNUSABLE;
    }
    var end = {
        name: muejejeReadingText(
            muejejeAdapterCall(port, "Port.getName"),
            MUEJEJE_PLATFORM_LIMITS.MAX_NAME_CHARS
        ),
        object_uuid: muejejeReadingText(
            muejejeAdapterCall(port, "Port.getObjectUuid"),
            MUEJEJE_PLATFORM_LIMITS.MAX_OBJECT_UUID_CHARS
        ),
        owner_device_object_uuid: null
    };
    var owner = muejejeAdapterCall(port, "Port.getOwnerDevice");
    if (!owner) {
        throw MUEJEJE_PLATFORM_UNUSABLE;
    }
    end.owner_device_object_uuid = muejejeReadingText(
        muejejeAdapterCall(owner, "Device.getObjectUuid"),
        MUEJEJE_PLATFORM_LIMITS.MAX_OBJECT_UUID_CHARS
    );
    return end;
}
