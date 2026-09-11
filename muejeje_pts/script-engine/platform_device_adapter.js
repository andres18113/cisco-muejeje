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
        max_device_index: MUEJEJE_PLATFORM_LIMITS.MAX_FACTORY_INDEX,
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
            offset, 0, MUEJEJE_PLATFORM_LIMITS.MAX_FACTORY_INDEX
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

/* RELAY CLOSURE FOR AN INDEX. The window stops at the highest factory index
 * this runtime addresses, not merely at `offset + limit`: bounding the first
 * index of a window and not its last let a window at the ceiling publish
 * indexes above it, and `platform.module_descriptors` and
 * `platform.module_type_support` would then refuse an index this very
 * operation had just handed out (MJ-029).
 *
 * The ceiling is reported rather than left to be inferred from a count. A
 * consumer paging the factory has to know where the addressable range ends,
 * and `available_count` is the platform's answer about how many models exist —
 * not a statement about which of them this runtime will address. */
function muejejeAdapterRead(platform, window) {
    var factory = muejejeAdapterCall(
        muejejeAdapterCall(platform, "hardwareFactory"), "devices"
    );
    var count = muejejeReadingCount(
        muejejeAdapterCall(factory, "getAvailableDeviceCount")
    );
    var last = Math.min(
        count, window.offset + window.limit,
        MUEJEJE_PLATFORM_LIMITS.MAX_FACTORY_INDEX + 1
    );
    var descriptors = [];
    for (var index = window.offset; index < last; index++) {
        descriptors.push(muejejeAdapterDescriptor(
            muejejeAdapterCallWith(factory, "getAvailableDeviceAt", index),
            index
        ));
    }
    return {
        resolution: MUEJEJE_PLATFORM_OBSERVED,
        unavailable_reason: null,
        available_count: count,
        offset: window.offset,
        limit: window.limit,
        max_device_index: MUEJEJE_PLATFORM_LIMITS.MAX_FACTORY_INDEX,
        descriptors: descriptors,
        window_truncated: count > last
    };
}

/* One model, and the index it was read at.
 *
 * The index is reported explicitly rather than left to be counted off from
 * `offset`: it is the value a consumer sends back to ask about this model, and
 * a reusable input a reader has to derive is one two readers will derive
 * differently. */
function muejejeAdapterDescriptor(descriptor, index) {
    if (!descriptor) {
        throw MUEJEJE_PLATFORM_UNUSABLE;
    }
    var supported = muejejeAdapterModuleTypes(descriptor);
    return {
        device_index: index,
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
        types.push(muejejeReadingModuleType(
            muejejeAdapterCallWith(descriptor, "getSupportedModuleTypeAt", index)
        ));
    }
    return {types: types, truncated: count > readable};
}

