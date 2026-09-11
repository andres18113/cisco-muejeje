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
 * list rather than by reading every call site. Each admitted name is a
 * documented getter, so no call instantiates a device, powers one, or touches
 * a workspace (MJ-014, MJ-031).
 *
 * WHOSE FAILURE WAS IT. Only two things become an unavailable reading: a call
 * made at the boundary below, and an answer the validators below refused.
 * Anything else that throws in a platform adapter is a defect in this
 * artifact, and it is left to reach the dispatcher as `ENGINE_EXCEPTION` —
 * reporting it as `PLATFORM_CALL_FAILED` would manufacture an observation
 * about Packet Tracer that Packet Tracer never produced, and a consumer
 * recording target evidence could not tell the two apart (MJ-022).
 *
 * WHAT IS READ THROUGH IT lives beside it, one adapter per subject: a boundary
 * and the things read across it are different responsibilities, and this file
 * is the one that has to stay short enough to check in full (MJ-018, MJ-020).
 * Those adapters name no platform object of their own.
 *
 * IT REACHES NO VERDICT. Whether an answer qualifies anything is decided in
 * Python, from outside the artifact (MJ-011). The module requests no privilege,
 * because no evidence names one these calls need; what a target actually does
 * with them is unknown until a target does it, and this artifact predicts
 * neither an answer nor a refusal. Whatever happens is reported as a reading
 * with its reason (MJ-032).
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
 *   DeviceDescriptor.isModuleTypeSupported(ModuleType) -> bool
 *   ipc.network()                          -> Network            (class_i_p_c)
 *   Network.getDeviceCount()                         -> int
 *   Network.getDeviceAt(int)                         -> Device
 *   Device.getName()                                 -> string     (class_device)
 *   Device.getModel()                                -> string     (class_device)
 *   Device.getType()                                 -> DeviceType (class_device)
 *
 * `Network.getDeviceCount`, `Network.getDeviceAt`, `Device.getName` and
 * `Device.getModel` are additionally evidenced against 9.0.1.0858 by this
 * repository's own live channel, which enumerates a workspace exactly this way
 * and reads both strings off it. `Device.getType` is documented and unmeasured
 * — which is the standing this list records, not a reason to guess at it.
 * `Network` also offers members that create a device or a link, and `Device`
 * offers members that move, power and rename one; none of them is on this
 * list. An allowlist is what makes "read-only" a property of the boundary
 * rather than a promise about call sites.
 *
 * `Device` further documents `getDescriptor()`, `getSerialNumber()`,
 * `getPower()` and `getUpTime()`. None is admitted: each is a further subject
 * with its own bounds and its own evidence, and no operation needs one yet.
 * `getDescriptor()` in particular is the only documented way to relate a
 * workspace device to a factory descriptor, so it is named here to record that
 * the relation has an API — and that nothing in this artifact manufactures one
 * without it (MJ-002, MJ-015).
 *   DeviceDescriptor.getSupportedModuleTypeCount()   -> int
 *   DeviceDescriptor.getSupportedModuleTypeAt(int)   -> ModuleType
 *   DeviceDescriptor.getRootModule()                 -> ModuleDescriptor
 *   ModuleDescriptor.getModel()                      -> string
 *   ModuleDescriptor.getType()                       -> ModuleType
 *   ModuleDescriptor.isHotSwappable()                -> bool
 *   ModuleDescriptor.getSlotCount()                  -> int
 *   ModuleDescriptor.getSlotTypeAt(int)              -> ModuleType
 *   ModuleDescriptor.getModuleCount()                -> int
 *   ModuleDescriptor.getModuleAt(int)                -> ModuleDescriptor
 *
 * `getModel` and `getType` are members of both descriptor interfaces, which is
 * why one entry serves both. The `ModuleDescriptor` getters are additionally
 * evidenced against 9.0.1.0858 by this repository's own read-only factory
 * surveys — from another channel, with its own privileges, which is evidence
 * that the getters answer on this build and none that this artifact may call
 * them (MJ-015).
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
    isModuleTypeSupported: true,
    network: true,
    getDeviceCount: true,
    getDeviceAt: true,
    getName: true,
    getSupportedModuleTypeCount: true,
    getSupportedModuleTypeAt: true,
    getRootModule: true,
    isHotSwappable: true,
    getSlotCount: true,
    getSlotTypeAt: true,
    getModuleCount: true,
    getModuleAt: true
};

/* THE PLATFORM-CALL BOUNDARY. One member call, by name, with the reason it can
 * fail decided here rather than by whoever wrote the call site.
 *
 * A name outside the allowlist throws a plain error on purpose: asking for a
 * call this artifact does not admit is a defect in this artifact, so it must
 * not come back looking like something Packet Tracer did. A receiver the
 * platform did not give us is an unusable answer. A member that is not there
 * is reported as absent rather than as a failed call, because nothing was
 * called: "this object does not offer that member" and "the call did not
 * return" are different observations with different next steps, and collapsing
 * them would invent a refusal nobody performed. */
function muejejeAdapterCall(receiver, name) {
    muejejeAdapterAdmitted(receiver, name);
    try {
        return receiver[name]();
    } catch (platformError) {
        throw MUEJEJE_PLATFORM_CALL_FAILED;
    }
}

/* The same boundary for a member that takes one argument. A separate function
 * rather than an optional parameter, so a call site that forgets the argument
 * cannot silently become the no-argument call.
 *
 * The argument is named `argument` and not `index` because it is not always
 * one: `getAvailableDeviceAt(int)` and `getSlotTypeAt(int)` are addressed by
 * position, while `isModuleTypeSupported(ModuleType)` is handed a *value* the
 * platform itself produced. Calling that value an index would say the type
 * space is an enumeration this artifact walks, which is the numeric-mirror
 * reading MJ-014 exists to prevent. */
function muejejeAdapterCallWith(receiver, name, argument) {
    muejejeAdapterAdmitted(receiver, name);
    try {
        return receiver[name](argument);
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
    if (typeof receiver[name] !== "function") {
        throw MUEJEJE_PLATFORM_MEMBER_ABSENT;
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
