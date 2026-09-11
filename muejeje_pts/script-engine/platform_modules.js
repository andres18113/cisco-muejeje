/*
 * Muejeje runtime — the `platform.module_descriptors` operation.
 *
 * Read-only. It answers one question — *what hardware is one device model
 * described as carrying* — and it answers it by asking the platform through
 * the declared adapters. It names no platform symbol itself: the arrow points
 * operation -> adapter -> boundary -> platform, and never back (MJ-019).
 *
 * The model is addressed by its index in the factory enumeration, which is
 * what `platform.device_descriptors` reports. That keeps the pair generic: no
 * DeviceType argument, so no numeric Cisco enum table has to exist, and no
 * model name, so no catalogue of somebody's hardware does either (MJ-002,
 * MJ-014). The identity actually read is reported back, so a consumer can tell
 * which model answered rather than trusting the index it sent.
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
 * `device_index` is bounded by the exact-integer limit rather than by a
 * second number written down here: two copies of a bound are two bounds, and
 * an index `platform.device_descriptors` publishes has to be one this
 * operation admits (MJ-029). */
var MUEJEJE_PLATFORM_MODULE_ARGS = {
    device_index: {
        kind: "integer",
        min: 0,
        max: MUEJEJE_PLATFORM_LIMITS.EXACT_INTEGER_MAX
    }
};

/* The argument is optional, and an omitted one is the first descriptor the
 * factory offers rather than a refusal: index 0 is the origin of an
 * enumeration, not a device anybody chose. Which model that turned out to be
 * is in the answer. */
function muejejePlatformModuleDescriptors(args, context) {
    return muejejeAdapterModuleDescriptors(
        muejejePlatformModuleArgument(args, "device_index", 0)
    );
}

/* V6 admission has already checked every supplied argument against the rule
 * above, so a value present here is within its bounds. This only decides
 * whether it was supplied at all. */
function muejejePlatformModuleArgument(args, name, fallback) {
    if (
        args === null || typeof args !== "object"
        || !Object.prototype.hasOwnProperty.call(args, name)
    ) {
        return fallback;
    }
    return args[name];
}
