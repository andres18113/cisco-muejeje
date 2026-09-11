/*
 * Muejeje runtime — the `platform.module_descriptors` operation.
 *
 * Read-only. It answers one question — *what hardware is one device model
 * described as carrying* — and it answers it by asking the platform through
 * the declared adapters. It names no platform symbol itself: the arrow points
 * operation -> adapter -> boundary -> platform, and never back (MJ-019).
 *
 * The model is addressed by its `factory_index`, which is what
 * `platform.device_descriptors` reports. That keeps the pair generic: no
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

/* The argument this operation admits, and the rule its value must satisfy.
 * Declared here, by the operation it belongs to, and handed to the dispatcher
 * — which owns *which* operations exist, not what each one's arguments mean.
 *
 * `factory_index` is bounded by the exact-integer limit rather than by a second
 * number written down here: two copies of a bound are two bounds, and an index
 * `platform.device_descriptors` publishes has to be one this operation admits
 * (MJ-029). It is named for its domain, so a `workspace_index` read off the
 * workspace cannot be sent here by the name it was published under.
 *
 * It is REQUIRED. Every index is a different model, so no default could be
 * honest: an earlier revision read the model at position 0 when none was named,
 * and reported that chassis as the answer to a question nobody asked. Admission
 * refuses a request that omits it, and nothing is read. */
var MUEJEJE_PLATFORM_MODULE_ARGS = {
    factory_index: {
        kind: "integer",
        required: true,
        min: 0,
        max: MUEJEJE_PLATFORM_LIMITS.EXACT_INTEGER_MAX
    }
};

function muejejePlatformModuleDescriptors(args, context) {
    return muejejeAdapterModuleDescriptors(
        muejejeV6RequiredArgument(args, "factory_index")
    );
}
