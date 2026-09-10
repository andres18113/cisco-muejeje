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

/* Clamp the requested window. The caller's arguments were already bounded by
 * V6 admission, and they are bounded again here: what this adapter will do in
 * one call is its own decision, not the caller's. */
function muejejeAdapterWindow(offset, limit) {
    var start = typeof offset === "number" && offset % 1 === 0 && offset > 0
        ? Math.min(offset, MUEJEJE_PLATFORM_LIMITS.MAX_OFFSET)
        : 0;
    var size = typeof limit === "number" && limit % 1 === 0 && limit > 0
        ? Math.min(limit, MUEJEJE_PLATFORM_LIMITS.MAX_WINDOW)
        : MUEJEJE_PLATFORM_LIMITS.MAX_WINDOW;
    return {offset: start, limit: size};
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
        model: muejejeReadingModel(muejejeAdapterCall(descriptor, "getModel")),
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

