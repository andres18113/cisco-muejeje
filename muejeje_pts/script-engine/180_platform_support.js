/*
 * Muejeje runtime — the `platform.module_type_support` operation.
 *
 * Read-only. It answers one question — *does this model accept this module
 * type* — and it answers it by asking the platform through the declared
 * adapters. It names no platform symbol itself: the arrow points operation ->
 * adapter -> boundary -> platform, and never back (MJ-019).
 *
 * Both arguments are the platform's own vocabulary, and neither is translated
 * here. The model is addressed by its `factory_index`, which is what
 * `platform.device_descriptors` reports; the module type is a value the
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
 * Both are bounded by the declared domains rather than by a second set of
 * numbers written down here: two copies of a bound are two bounds.
 *
 * RELAY CLOSURE. Both arguments are values this artifact *publishes*.
 * `factory_index` is what `platform.device_descriptors` reports for a model;
 * `module_type` is what that operation and `platform.module_descriptors`
 * report as a type. So each rule names the domain those readings publish in,
 * and cannot narrow it: a bound of its own here would refuse a value a
 * consumer read out of a reading this same artifact produced (MJ-029).
 *
 * BOTH ARE REQUIRED, and for the same reason: every value of either is a
 * different question. Which model, and which type — defaulting either would
 * answer a question the caller did not ask and report the answer as an
 * observation. */
var MUEJEJE_PLATFORM_SUPPORT_ARGS = {
    factory_index: {
        kind: "integer",
        required: true,
        min: 0,
        max: MUEJEJE_PLATFORM_LIMITS.EXACT_INTEGER_MAX
    },
    module_type: {
        kind: "integer",
        required: true,
        min: MUEJEJE_PLATFORM_LIMITS.EXACT_INTEGER_MIN,
        max: MUEJEJE_PLATFORM_LIMITS.EXACT_INTEGER_MAX
    }
};

/* Admission has refused a request that omits either argument, so both are read
 * with no fallback: a fallback here would be a stand-in value answering for the
 * one the caller did not send (MJ-022, MJ-029). */
function muejejePlatformModuleTypeSupport(args, context) {
    return muejejeAdapterModuleTypeSupport(
        muejejeV6RequiredArgument(args, "factory_index"),
        muejejeV6RequiredArgument(args, "module_type")
    );
}
