/*
 * Muejeje runtime — the device-descriptor reading. READ-ONLY.
 *
 * A declared adapter (MJ-006, MJ-019, MJ-031): it reads the Packet Tracer
 * hardware *factory* — which device models this build offers, and which module
 * types each model supports — and it reports what it read without deciding
 * what any of it establishes (MJ-011).
 *
 * It names no platform object. Every call it makes goes through
 * `muejejeAdapterCall` in `platform_adapter.js`, which admits only the
 * read-only getters on that list, so this file cannot reach past what the
 * boundary admits even by accident.
 *
 * IT READS THE FACTORY, NEVER A WORKSPACE. A descriptor describes what a model
 * can accept; nothing here instantiates a device, powers one, or looks at a
 * topology, a link or an address (MJ-002, MJ-004). And no field it returns
 * establishes installed hardware: a descriptor is not a runtime `Module`
 * (MJ-014).
 */

/* One result shape for every outcome, so a consumer parses one thing whether
 * the platform answered or not. */
function muejejeAdapterUnavailable(reason, offset, limit) {
    return {
        resolution: MUEJEJE_PLATFORM_UNAVAILABLE,
        unavailable_reason: reason,
        available_count: null,
        offset: offset,
        limit: limit,
        descriptors: [],
        window_truncated: false
    };
}

/* The requested window, checked rather than clamped.
 *
 * It used to be clamped, and that was wrong in a way worth naming: an argument
 * outside these bounds cannot come from a caller — V6 admission refuses that,
 * and the operation defaults an argument nobody sent — so it can only come
 * from our own code. Silently reading a different window and reporting the
 * result as an observation would answer a question nobody asked. */
function muejejeAdapterWindow(offset, limit) {
    return {
        offset: muejejeReadingArgument(
            offset, 0, MUEJEJE_PLATFORM_LIMITS.MAX_OFFSET
        ),
        limit: muejejeReadingArgument(
            limit, 1, MUEJEJE_PLATFORM_LIMITS.MAX_WINDOW
        )
    };
}

/* The one entry point. An unreadable platform is an observation about the
 * platform, not an exception for the caller. */
function muejejeAdapterDeviceDescriptors(offset, limit) {
    var window = muejejeAdapterWindow(offset, limit);
    var platform = muejejeAdapterPlatform();
    if (platform === null) {
        return muejejeAdapterUnavailable(
            MUEJEJE_PLATFORM_ABSENT, window.offset, window.limit
        );
    }
    try {
        return muejejeAdapterRead(platform, window);
    } catch (platformError) {
        /* The thrown value is engine-internal and never reaches the result: a
         * consumer that could read it would be depending on an internal
         * (MJ-005). Only our own sentinels are a reading; anything else is a
         * defect here and is rethrown for the dispatcher. */
        return muejejeAdapterUnavailable(
            muejejeReadingReason(platformError), window.offset, window.limit
        );
    }
}

function muejejeAdapterRead(platform, window) {
    var factory = muejejeAdapterCall(
        muejejeAdapterCall(platform, "hardwareFactory"), "devices"
    );
    var count = muejejeReadingCount(
        muejejeAdapterCall(factory, "getAvailableDeviceCount")
    );
    var last = Math.min(count, window.offset + window.limit);
    var descriptors = [];
    for (var index = window.offset; index < last; index++) {
        descriptors.push(muejejeAdapterDescriptor(
            muejejeAdapterCallAt(factory, "getAvailableDeviceAt", index)
        ));
    }
    return {
        resolution: MUEJEJE_PLATFORM_OBSERVED,
        unavailable_reason: null,
        available_count: count,
        offset: window.offset,
        limit: window.limit,
        descriptors: descriptors,
        window_truncated: count > last
    };
}

function muejejeAdapterDescriptor(descriptor) {
    var supported = muejejeAdapterModuleTypes(descriptor);
    return {
        model: muejejeReadingText(
            muejejeAdapterCall(descriptor, "getModel"),
            MUEJEJE_PLATFORM_LIMITS.MAX_MODEL_CHARS
        ),
        device_type: muejejeReadingWholeNumber(
            muejejeAdapterCall(descriptor, "getType")
        ),
        model_supported: muejejeReadingFlag(
            muejejeAdapterCall(descriptor, "isModelSupported")
        ),
        supported_module_types: supported.types,
        module_types_truncated: supported.truncated
    };
}

/* The module types a model supports, read from the descriptor that knows.
 *
 * This is the answer a numeric mirror was standing in for: the values come
 * back from Packet Tracer as Packet Tracer's own numbers, and nothing here
 * translates them (MJ-014). Naming them is a consumer's job, against the
 * platform's own documentation. */
function muejejeAdapterModuleTypes(descriptor) {
    var count = muejejeReadingCount(
        muejejeAdapterCall(descriptor, "getSupportedModuleTypeCount")
    );
    var readable = Math.min(count, MUEJEJE_PLATFORM_LIMITS.MAX_MODULE_TYPES);
    var types = [];
    for (var index = 0; index < readable; index++) {
        types.push(muejejeReadingWholeNumber(
            muejejeAdapterCallAt(descriptor, "getSupportedModuleTypeAt", index)
        ));
    }
    return {types: types, truncated: count > readable};
}

