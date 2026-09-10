/*
 * Muejeje runtime — the Cisco platform adapter. READ-ONLY.
 *
 * The only file in this artifact that reaches Packet Tracer. It is declared as
 * an adapter in the architecture gates, which is what makes naming `ipc` legal
 * here and a violation everywhere else (MJ-006, MJ-019). It adapts and nothing
 * more: it shapes no envelope, admits no request, dispatches nothing, and
 * reads no kernel state.
 *
 * NOTHING HERE MUTATES ANYTHING. Every call below is a documented getter on a
 * *descriptor* — a description of what a model can accept — so no call
 * instantiates a device, powers one, or touches a workspace. A descriptor is
 * not a runtime `Module`, and no field it returns establishes installed
 * hardware (MJ-014).
 *
 * Every API used here is named in Cisco's installed IpcAPI reference for
 * 9.0.1.0858, and none is guessed (`AGENTS.md` rule 6):
 *
 *   ipc.hardwareFactory()                  -> HardwareFactory
 *   HardwareFactory.devices()              -> DeviceFactory
 *   DeviceFactory.getAvailableDeviceCount()          -> int
 *   DeviceFactory.getAvailableDeviceAt(int)          -> DeviceDescriptor
 *   DeviceDescriptor.getModel()                      -> string
 *   DeviceDescriptor.getType()                       -> DeviceType
 *   DeviceDescriptor.isModelSupported()              -> bool
 *   DeviceDescriptor.getSupportedModuleTypeCount()   -> int
 *   DeviceDescriptor.getSupportedModuleTypeAt(int)   -> ModuleType
 *
 * The enumeration is deliberately the *unqualified* pair — count and index —
 * because it needs no DeviceType argument. Asking for a type would mean
 * carrying a numeric Cisco enum table as the authority for which types exist,
 * and a mirrored constant is correct only until Packet Tracer changes
 * (MJ-014). The numbers this adapter reports are read back out of the
 * platform, never matched against a table of our own.
 *
 * IT REPORTS OBSERVATIONS AND REACHES NO VERDICT. Whether an answer qualifies
 * anything is decided in Python, from outside the artifact (MJ-011). And the
 * module requests no privilege, so on a real target these calls are denied
 * until a privilege is evidenced — which this reports as an unavailable
 * reading rather than as a failure of the platform (MJ-032).
 */

/* Bounds, and they are Muejeje's own. Nothing here has measured how many
 * models the factory offers or how many module types a descriptor lists, so
 * each number is a limit on what this adapter will do in one call and never a
 * claim about the platform (MJ-029). A read past a bound is reported as
 * truncated, so an omitted tail stays visibly absent and can never be read as
 * an observed absence. */
var MUEJEJE_PLATFORM_LIMITS = {
    MAX_WINDOW: 32,
    MAX_OFFSET: 4096,
    MAX_MODULE_TYPES: 64,
    MAX_COUNT: 65536,
    MAX_MODEL_CHARS: 256
};

/* Why a reading is unavailable. Three different facts, kept apart because a
 * consumer acts differently on each.
 *
 * ABSENT       there is no platform object here at all.
 * CALL_FAILED  the platform was asked and the call did not return. A denied
 *              privilege is one cause; so is any other engine-side refusal,
 *              and this adapter cannot tell which, so it does not say.
 * UNUSABLE     the platform answered, and the answer could not be attributed:
 *              a count that is not a whole number, a missing descriptor. */
var MUEJEJE_PLATFORM_ABSENT = "PLATFORM_ABSENT";
var MUEJEJE_PLATFORM_CALL_FAILED = "PLATFORM_CALL_FAILED";
var MUEJEJE_PLATFORM_UNUSABLE = "PLATFORM_ANSWER_UNUSABLE";

var MUEJEJE_PLATFORM_OBSERVED = "OBSERVED";
var MUEJEJE_PLATFORM_UNAVAILABLE = "UNAVAILABLE";

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

/* The one entry point. It never throws: an unreadable platform is an
 * observation about the platform, not an exception for the caller. */
function muejejeAdapterDeviceDescriptors(offset, limit) {
    var window = muejejeAdapterWindow(offset, limit);
    if (typeof ipc === "undefined" || ipc === null) {
        return muejejeAdapterUnavailable(
            MUEJEJE_PLATFORM_ABSENT, window.offset, window.limit
        );
    }
    try {
        return muejejeAdapterRead(window);
    } catch (platformError) {
        /* The thrown value is engine-internal and never reaches the result: a
         * consumer that could read it would be depending on an internal
         * (MJ-005). Only our own sentinel is distinguished. */
        return muejejeAdapterUnavailable(
            platformError === MUEJEJE_PLATFORM_UNUSABLE
                ? MUEJEJE_PLATFORM_UNUSABLE
                : MUEJEJE_PLATFORM_CALL_FAILED,
            window.offset,
            window.limit
        );
    }
}

function muejejeAdapterRead(window) {
    var factory = ipc.hardwareFactory().devices();
    if (!factory) {
        throw MUEJEJE_PLATFORM_UNUSABLE;
    }
    var count = muejejeAdapterCount(factory.getAvailableDeviceCount());
    var last = Math.min(count, window.offset + window.limit);
    var descriptors = [];
    for (var index = window.offset; index < last; index++) {
        descriptors.push(
            muejejeAdapterDescriptor(factory.getAvailableDeviceAt(index))
        );
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
    if (!descriptor) {
        throw MUEJEJE_PLATFORM_UNUSABLE;
    }
    var supported = muejejeAdapterModuleTypes(descriptor);
    return {
        model: muejejeAdapterModel(descriptor.getModel()),
        device_type: muejejeAdapterWholeNumber(descriptor.getType()),
        model_supported: muejejeAdapterFlag(descriptor.isModelSupported()),
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
    var count = muejejeAdapterCount(descriptor.getSupportedModuleTypeCount());
    var readable = Math.min(count, MUEJEJE_PLATFORM_LIMITS.MAX_MODULE_TYPES);
    var types = [];
    for (var index = 0; index < readable; index++) {
        types.push(
            muejejeAdapterWholeNumber(descriptor.getSupportedModuleTypeAt(index))
        );
    }
    return {types: types, truncated: count > readable};
}

function muejejeAdapterCount(value) {
    if (
        typeof value !== "number" || value % 1 !== 0 || value < 0
        || value > MUEJEJE_PLATFORM_LIMITS.MAX_COUNT
    ) {
        throw MUEJEJE_PLATFORM_UNUSABLE;
    }
    return value;
}

function muejejeAdapterWholeNumber(value) {
    if (typeof value !== "number" || value % 1 !== 0) {
        throw MUEJEJE_PLATFORM_UNUSABLE;
    }
    return value;
}

/* An empty model is a real answer, not a malformed one: on 9.0.1 a chassis
 * root can report "". Requiring a name here discarded correct metadata once
 * already, so the only thing checked is that it is a bounded string — and the
 * bound is a length of its own, not a count reused as one. */
function muejejeAdapterModel(value) {
    if (
        typeof value !== "string"
        || value.length > MUEJEJE_PLATFORM_LIMITS.MAX_MODEL_CHARS
    ) {
        throw MUEJEJE_PLATFORM_UNUSABLE;
    }
    return value;
}

function muejejeAdapterFlag(value) {
    if (typeof value !== "boolean") {
        throw MUEJEJE_PLATFORM_UNUSABLE;
    }
    return value;
}
