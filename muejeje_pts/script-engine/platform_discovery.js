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
 * A reading may be unavailable, and that is an answer. This module requests no
 * privilege, because nothing evidences which privilege the call needs — and
 * what a target does with an unprivileged call is not something this artifact
 * knows in advance. Whatever comes back is reported as a reading with its
 * reason, and never as a claim about what the platform does or does not have
 * (MJ-032).
 */

/* The arguments this operation admits, and the rule each value must satisfy.
 * Declared here, by the operation they belong to, and handed to the dispatcher
 * — which owns *which* operations exist, not what each one's arguments mean.
 *
 * `limit` is bounded by the adapter's own window ceiling rather than by a
 * second number written down here: two copies of a bound are two bounds.
 *
 * `offset` is bounded only by the exact-integer limit — the same declaration
 * the operations that consume a `device_index` name — so a consumer may page
 * as far as the factory goes, and every index this operation publishes is one
 * they admit (MJ-029). */
var MUEJEJE_PLATFORM_DESCRIPTOR_ARGS = {
    offset: {
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

/* Both arguments are optional. An omitted one is a default, never a refusal:
 * a consumer discovering the platform for the first time has no reason to know
 * how many models there are before it asks. */
function muejejePlatformDeviceDescriptors(args, context) {
    return muejejeAdapterDeviceDescriptors(
        muejejePlatformArgument(args, "offset", 0),
        muejejePlatformArgument(args, "limit", MUEJEJE_PLATFORM_LIMITS.MAX_FACTORY_WINDOW)
    );
}

/* V6 admission has already checked every supplied argument against the rule
 * above, so a value present here is within its bounds. This only decides
 * whether it was supplied at all. */
function muejejePlatformArgument(args, name, fallback) {
    if (
        args === null || typeof args !== "object"
        || !Object.prototype.hasOwnProperty.call(args, name)
    ) {
        return fallback;
    }
    return args[name];
}
