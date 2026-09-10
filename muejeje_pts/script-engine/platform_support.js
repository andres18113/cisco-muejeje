/*
 * Muejeje runtime — the `platform.module_type_support` operation.
 *
 * Read-only. It answers one question — *does this model accept this module
 * type* — and it answers it by asking the platform through the declared
 * adapters. It names no platform symbol itself: the arrow points operation ->
 * adapter -> boundary -> platform, and never back (MJ-019).
 *
 * Both arguments are the platform's own vocabulary, and neither is translated
 * here. The model is addressed by its index in the factory enumeration, which
 * is what `platform.device_descriptors` reports; the module type is a value the
 * platform itself handed a consumer, from that same operation or from the
 * chassis of `platform.module_descriptors`. This artifact carries no table of
 * either, which is what lets it ask the question without owning an answer to
 * "which types exist" (MJ-014).
 *
 * It reaches no verdict. `resolution` says whether a reading was obtained;
 * `module_type_supported` is what the platform said, not what it establishes.
 * Python decides what an observation means, from outside the artifact (MJ-011).
 */

/* The arguments this operation admits, and the rule each value must satisfy.
 * Both are bounded by the adapter's own ceilings rather than by a second set of
 * numbers written down here: two copies of a bound are two bounds. */
var MUEJEJE_PLATFORM_SUPPORT_ARGS = {
    device_index: {
        kind: "integer",
        min: 0,
        max: MUEJEJE_PLATFORM_LIMITS.MAX_OFFSET
    },
    module_type: {
        kind: "integer",
        required: true,
        min: 0,
        max: MUEJEJE_PLATFORM_LIMITS.MAX_MODULE_TYPE
    }
};

/* `device_index` defaults to the origin of the factory enumeration, as it does
 * for the chassis reading. `module_type` is *required*, and no default would be
 * honest: every value in that space is a different question, and picking one
 * would answer a question the caller did not ask. Admission refuses a request
 * that omits it, so a value is always present here. */
function muejejePlatformModuleTypeSupport(args, context) {
    return muejejeAdapterModuleTypeSupport(
        muejejePlatformSupportArgument(args, "device_index", 0),
        muejejePlatformSupportArgument(args, "module_type", 0)
    );
}

function muejejePlatformSupplied(args, name) {
    return (
        args !== null && typeof args === "object"
        && Object.prototype.hasOwnProperty.call(args, name)
    );
}

/* V6 admission has already checked every supplied argument against the rule
 * above, so a value present here is within its bounds. This only decides
 * whether it was supplied at all. */
function muejejePlatformSupportArgument(args, name, fallback) {
    if (!muejejePlatformSupplied(args, name)) {
        return fallback;
    }
    return args[name];
}
