/*
 * Muejeje runtime — the `platform.device_descriptors` operation.
 *
 * Read-only. It answers one question — *what device models does this Packet
 * Tracer offer, and what module types does each one support* — and it answers
 * it by asking the platform through the declared adapter. It names no platform
 * symbol itself: the arrow points operation -> adapter -> platform, and never
 * back (MJ-019).
 *
 * This is the first capability that is *discovered* rather than declared,
 * which is what MJ-003 asks for: behaviour selected from what the platform
 * reports, not from what a table in this repository assumes it supports.
 *
 * It reaches no verdict. `resolution` says whether a reading was obtained, not
 * whether anything is qualified by it — the engine cannot audit the engine, so
 * Python decides what an observation establishes (MJ-011).
 *
 * A reading may be unavailable, and that is an answer. This module declares
 * the one privilege a recorded reading of the pinned binary says this call's
 * root requires — and what a target then does with the call is not something
 * this artifact knows in advance. Whatever comes back is reported as a reading
 * with its reason, and never as a claim about what the platform does or does
 * not have (MJ-032).
 */

/* The arguments this operation admits, and the rule each value must satisfy.
 * Declared here, by the operation they belong to, and handed to the dispatcher
 * — which owns *which* operations exist, not what each one's arguments mean.
 *
 * `factory_offset` names the enumeration it addresses. A window over the
 * factory and a window over the workspace start at positions in two different
 * domains, and an argument called `offset` in both let a position read from
 * one be sent to the other with nothing to refuse it (MJ-029).
 *
 * `limit` is bounded by the adapter's own window rather than by a second number
 * written down here: two copies of a bound are two bounds. `factory_offset` is
 * bounded only by the exact-integer limit — the same declaration the operations
 * that consume a `factory_index` name — so a consumer may page as far as the
 * factory goes, and every index this operation publishes is one they admit. */
var MUEJEJE_PLATFORM_DESCRIPTOR_ARGS = {
    factory_offset: {
        kind: "integer",
        min: 0,
        max: MUEJEJE_PLATFORM_LIMITS.EXACT_INTEGER_MAX
    },
    limit: {
        kind: "integer",
        min: 1,
        max: MUEJEJE_PLATFORM_LIMITS.MAX_FACTORY_WINDOW
    }
};

/* Both arguments are optional, and each default is the origin of what is read:
 * the start of the factory, and a window at its widest. That is honest here in
 * a way it is not for an index — a first window over an enumeration *is* the
 * question a consumer discovering the platform is asking (MJ-029). */
function muejejePlatformDeviceDescriptors(args, context) {
    return muejejeAdapterDeviceDescriptors(
        muejejeV6OptionalArgument(args, "factory_offset", 0),
        muejejeV6OptionalArgument(
            args, "limit", MUEJEJE_PLATFORM_LIMITS.MAX_FACTORY_WINDOW
        )
    );
}
