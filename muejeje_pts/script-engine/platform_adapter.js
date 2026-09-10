/*
 * Muejeje runtime — the Cisco platform-call boundary. READ-ONLY.
 *
 * The only file in this artifact that names `ipc`, and the only one that
 * invokes a platform member at all. It is declared as an adapter in the
 * architecture gates, which is what makes naming the platform legal here and a
 * violation everywhere else (MJ-006, MJ-019). It adapts and nothing more: it
 * shapes no envelope, admits no request, dispatches nothing, and reads no
 * kernel state.
 *
 * EVERY PLATFORM CALL GOES THROUGH ONE FUNCTION. `muejejeAdapterCall` takes the
 * member name as data and refuses any name outside the read-only allowlist
 * below, so "what does this artifact do to Packet Tracer" is answered by one
 * list rather than by reading every call site. Nothing here mutates anything:
 * each admitted name is a documented getter, so no call instantiates a device,
 * powers one, or touches a workspace. A descriptor is not a runtime `Module`,
 * and no field it returns establishes installed hardware (MJ-014).
 *
 * WHOSE FAILURE WAS IT. Only two things become an unavailable reading: a call
 * made at the boundary below, and an answer the validators below refused.
 * Anything else that throws in a platform adapter is a defect in this
 * artifact, and it is left to reach the dispatcher as `ENGINE_EXCEPTION` —
 * reporting it as `PLATFORM_CALL_FAILED` would manufacture an observation
 * about Packet Tracer that Packet Tracer never produced, and a consumer could
 * not tell it from the real thing (MJ-022, MJ-031).
 *
 * WHAT IS READ THROUGH IT lives beside it, one adapter per subject, because a
 * boundary and the things read across it are different responsibilities and
 * this file is the one that must stay short enough to check in full (MJ-018,
 * MJ-020). Those adapters name no platform object of their own: they are
 * handed one and call it by name through `muejejeAdapterCall`.
 *
 * IT REPORTS OBSERVATIONS AND REACHES NO VERDICT. Whether an answer qualifies
 * anything is decided in Python, from outside the artifact (MJ-011). And the
 * module requests no privilege, so on a real target these calls are denied
 * until a privilege is evidenced — which is reported as an unavailable reading
 * rather than as a failure of the platform (MJ-032).
 */

/* The platform members this artifact may call, and the whole of what it may
 * call. Every name is a getter named in Cisco's installed IpcAPI reference for
 * 9.0.1.0858, and none is guessed (`AGENTS.md` rule 6):
 *
 *   ipc.hardwareFactory()                  -> HardwareFactory  (class_i_p_c)
 *   HardwareFactory.devices()              -> DeviceFactory
 *   DeviceFactory.getAvailableDeviceCount()          -> int
 *   DeviceFactory.getAvailableDeviceAt(int)          -> DeviceDescriptor
 *   DeviceDescriptor.getModel()                      -> string
 *   DeviceDescriptor.getType()                       -> DeviceType
 *   DeviceDescriptor.isModelSupported()              -> bool
 *   DeviceDescriptor.getSupportedModuleTypeCount()   -> int
 *   DeviceDescriptor.getSupportedModuleTypeAt(int)   -> ModuleType
 *
 * An allowlist rather than a list of forbidden verbs: a name nobody thought to
 * forbid is admitted by a blacklist and refused by this. The enumeration is
 * deliberately the *unqualified* pair — count and index — because it needs no
 * DeviceType argument. Asking by type would mean carrying a numeric Cisco enum
 * table as the authority for which types exist, and a mirrored constant is
 * correct only until Packet Tracer changes (MJ-014). */
var MUEJEJE_PLATFORM_READ_ONLY_CALLS = {
    hardwareFactory: true,
    devices: true,
    getAvailableDeviceCount: true,
    getAvailableDeviceAt: true,
    getModel: true,
    getType: true,
    isModelSupported: true,
    getSupportedModuleTypeCount: true,
    getSupportedModuleTypeAt: true
};

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

/* THE PLATFORM-CALL BOUNDARY. One member call, by name, with the reason it can
 * fail decided here rather than by whoever wrote the call site.
 *
 * A name outside the allowlist throws a plain error on purpose: asking for a
 * call this artifact does not admit is a defect in this artifact, so it must
 * not come back looking like something Packet Tracer did. A receiver the
 * platform did not give us is an unusable answer; a call that threw is a call
 * that did not return, whatever the engine's reason was. */
function muejejeAdapterCall(receiver, name) {
    muejejeAdapterAdmitted(receiver, name);
    try {
        return receiver[name]();
    } catch (platformError) {
        throw MUEJEJE_PLATFORM_CALL_FAILED;
    }
}

/* The same boundary for the indexed pair — `getAvailableDeviceAt(int)` and its
 * kind. A separate function rather than an optional argument, so a call site
 * that forgets the index cannot silently become the no-argument call. */
function muejejeAdapterCallAt(receiver, name, index) {
    muejejeAdapterAdmitted(receiver, name);
    try {
        return receiver[name](index);
    } catch (platformError) {
        throw MUEJEJE_PLATFORM_CALL_FAILED;
    }
}

function muejejeAdapterAdmitted(receiver, name) {
    if (!Object.prototype.hasOwnProperty.call(
        MUEJEJE_PLATFORM_READ_ONLY_CALLS, name
    )) {
        throw new Error("muejeje: platform call outside the read-only boundary");
    }
    if (receiver === null || typeof receiver !== "object") {
        throw MUEJEJE_PLATFORM_UNUSABLE;
    }
}

/* The platform object, or null when there is none. Asking "is there a Packet
 * Tracer here" is a platform question, so it is answered here rather than in
 * every adapter that would otherwise have to name `ipc` to ask it. */
function muejejeAdapterPlatform() {
    if (typeof ipc === "undefined" || ipc === null) {
        return null;
    }
    return ipc;
}

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

/* Which thrown values are a reading, and which are this artifact's own bug.
 *
 * The two sentinels are the only failures this adapter attributed to the
 * platform: one at the call boundary, one at a validator. Anything else got
 * here from our own code, so it is rethrown for the dispatcher to report as an
 * engine exception. Swallowing it would publish a platform observation nobody
 * observed (MJ-031). */
function muejejeAdapterReading(thrown, window) {
    if (
        thrown !== MUEJEJE_PLATFORM_CALL_FAILED
        && thrown !== MUEJEJE_PLATFORM_UNUSABLE
    ) {
        throw thrown;
    }
    return muejejeAdapterUnavailable(thrown, window.offset, window.limit);
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
