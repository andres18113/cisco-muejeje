/*
 * Muejeje runtime — the `network.device_identity` operation.
 *
 * Read-only. It answers one question — *what does this Packet Tracer say the
 * device at this position is* — and it answers it by asking the platform
 * through the declared adapter. It names no platform symbol itself: the arrow
 * points operation -> adapter -> boundary -> platform, and never back (MJ-019).
 *
 * ONE READING OF ONE DEVICE. Everything it reports was obtained in a single
 * observation: the count, the device at the requested position, and each fact
 * read off that device. It is not a join of two readings, and it is not a join
 * of a workspace with the hardware factory — the two are different subjects,
 * and nothing here relates them (MJ-031).
 *
 * THE ARGUMENT IS A POSITION, NOT A NAME AND NOT AN IDENTITY. `device_index` is
 * where to look in this reading. It is not stable across readings — a workspace
 * changes, and a consumer that stored an index is addressing whatever occupies
 * that position later — which is exactly why the identity facts come back
 * beside it: they are how a consumer tells what actually answered.
 *
 * Addressing by position rather than by name is also what keeps it generic. An
 * operation that took a device name would work only for a consumer that already
 * knew the names, which is one topology's vocabulary living in the runtime
 * (MJ-002, MJ-004).
 *
 * It reaches no verdict. `resolution` says whether a reading was obtained, not
 * what it establishes — the engine cannot audit the engine, so Python decides
 * that from outside the artifact (MJ-011).
 */

/* The one argument this operation admits, and the rule its value must satisfy.
 * Declared here, by the operation it belongs to, and handed to the dispatcher —
 * which owns *which* operations exist, not what each one's arguments mean.
 *
 * It is bounded by the workspace addressing ceiling rather than by a second
 * number written down here: two copies of a bound are two bounds, and an index
 * `network.device_inventory` publishes has to be one this operation admits
 * (MJ-029). */
var MUEJEJE_NETWORK_IDENTITY_ARGS = {
    device_index: {
        kind: "integer",
        min: 0,
        max: MUEJEJE_PLATFORM_LIMITS.MAX_WORKSPACE_INDEX
    }
};

/* The argument is optional, and an omitted one is the first position the
 * workspace enumerates rather than a refusal: index 0 is the origin of an
 * enumeration, not a device anybody chose. Which device that turned out to be
 * is in the answer, which is the whole reason the identity facts are there. */
function muejejeNetworkDeviceIdentity(args, context) {
    return muejejeAdapterDeviceIdentity(
        muejejeNetworkIdentityArgument(args, "device_index", 0)
    );
}

/* V6 admission has already checked every supplied argument against the rule
 * above, so a value present here is within its bounds. This only decides
 * whether it was supplied at all. */
function muejejeNetworkIdentityArgument(args, name, fallback) {
    if (
        args === null || typeof args !== "object"
        || !Object.prototype.hasOwnProperty.call(args, name)
    ) {
        return fallback;
    }
    return args[name];
}
