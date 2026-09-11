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
 * THE ARGUMENT IS A POSITION, NOT A NAME AND NOT AN IDENTITY. `workspace_index`
 * is where to look in this reading. It is not stable across readings — a
 * workspace changes, and a consumer that stored an index is addressing whatever
 * occupies that position later — which is exactly why the identity facts come
 * back beside it: they are how a consumer tells what actually answered.
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
 * It is bounded by the exact-integer limit rather than by a second number
 * written down here: two copies of a bound are two bounds, and an index
 * `network.device_inventory` publishes has to be one this operation admits
 * (MJ-029). It is named for its domain, so a `factory_index` cannot be sent here
 * by the name it was published under.
 *
 * It is REQUIRED. Every position holds a different device, so no default could
 * be honest: an earlier revision read position 0 when none was named and
 * reported whatever device stood there as the answer to a question nobody
 * asked. Admission refuses a request that omits it, and nothing is read. */
var MUEJEJE_NETWORK_IDENTITY_ARGS = {
    workspace_index: {
        kind: "integer",
        required: true,
        min: 0,
        max: MUEJEJE_PLATFORM_LIMITS.EXACT_INTEGER_MAX
    }
};

function muejejeNetworkDeviceIdentity(args, context) {
    return muejejeAdapterDeviceIdentity(
        muejejeV6RequiredArgument(args, "workspace_index")
    );
}
