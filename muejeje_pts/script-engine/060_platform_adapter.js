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
 * A CALL IS AN INTERFACE MEMBER, NEVER A BARE NAME. `getType` is a member of
 * `Device`, `DeviceDescriptor`, `ModuleDescriptor` and `Port`, and `getRootModule`
 * hands over a runtime `Module` on `Device` but a `ModuleDescriptor` on
 * `DeviceDescriptor`. Each is its own signature with its own evidence, so each
 * is admitted — or not — on its own. A call site names the member it means as
 * `Interface.member`; every platform object this boundary hands out carries
 * the interface its producing member's entry names; and nothing is called until
 * the two agree. A name never inherits another interface's admission, and no
 * interface inherits another's members (MJ-031).
 *
 * EVERY PLATFORM CALL GOES THROUGH THIS FILE, so "what does this artifact do
 * to Packet Tracer" is answered by the list below rather than by reading every
 * call site. Each admitted member is a getter, so no call instantiates a
 * device, powers one, or touches a workspace (MJ-014, MJ-031).
 *
 * WHOSE FAILURE WAS IT. Only two things become an unavailable reading: a call
 * made at this boundary, and an answer a reading's validators refused. Anything
 * else that throws in a platform adapter is a defect in this artifact, and it
 * reaches the dispatcher as `ENGINE_EXCEPTION` — reporting it as
 * `PLATFORM_CALL_FAILED` would manufacture an observation about Packet Tracer
 * that Packet Tracer never produced (MJ-022). *Where* a reading failed is
 * recorded in `muejejeReadingStage`, since only this file knows.
 *
 * WHAT IS READ THROUGH IT lives beside it, one adapter per subject, naming no
 * platform object of its own (MJ-018, MJ-020). IT REACHES NO VERDICT: Python
 * decides what an answer qualifies (MJ-011). The module runs with Packet
 * Tracer's full privilege set, so the selection bounds none of this — the list
 * below does (MJ-032) — and what a target does with a call is reported as a
 * reading with its reason, never predicted here.
 */

/* The platform members this artifact may call, and the whole of what it may
 * call: one entry per interface member, none guessed (`AGENTS.md` rule 6).
 *
 * TWO BASES, AND EACH ENTRY STANDS ON ONE. Every entry above the marker is
 * DOCUMENTED: on its own interface's page of Cisco's installed IpcAPI reference
 * for 9.0.1.0858 (`help/default/IpcAPI/class_*.html`), taking that many
 * arguments and handing over that interface. Every entry below it is
 * TARGET_EVIDENCED: absent from its own interface's page, and observed on that
 * build answering on the object this boundary hands out as that interface. A
 * gate holds each entry to its basis, so a page never vouches for another
 * interface's member — `Cable` documenting `getPort1()` is not why
 * `Link.getPort1` is admitted, and nothing here decides a link is a cable.
 *
 * `arity` is how many arguments the signature takes, so a call that forgot one
 * is refused rather than becoming a different call. `hands_over` names the
 * interface of the object the member returns, or is null for a value: it is how
 * the boundary knows the next receiver, since the object cannot be asked.
 *
 * Every entry is a getter; the members that create, move, power, rename or
 * configure are not here. An allowlist, not a list of forbidden verbs: a name
 * nobody thought to forbid is refused by this. The factory is enumerated by
 * count and index, with no DeviceType argument, so no numeric Cisco enum table
 * decides which types exist (MJ-014).
 *
 * Deliberately absent, each a further subject with its own evidence:
 * `Device.getDescriptor()`, the documented relation from a workspace device to
 * a factory descriptor, named so nothing manufactures one without it;
 * `Device.getRootModule()`, installed hardware rather than its description;
 * `getSerialNumber()`, `getPower()` and `getUpTime()`; `Port.getLink()`, a
 * second route to a link; `Port.getRemotePortName()` and `Cable.getOtherPort()`,
 * which address an end by name; and a port's type, state and addresses
 * (MJ-002, MJ-015). Which entries answered through which channel is the
 * evidence table in `docs/qa/muejeje-pts-offline.md`, not a claim this makes. */
var MUEJEJE_PLATFORM_READ_ONLY_CALLS = {
    "IPC.hardwareFactory": {arity: 0, hands_over: "HardwareFactory"},
    "IPC.network": {arity: 0, hands_over: "Network"},
    "HardwareFactory.devices": {arity: 0, hands_over: "DeviceFactory"},
    "DeviceFactory.getAvailableDeviceCount": {arity: 0, hands_over: null},
    "DeviceFactory.getAvailableDeviceAt": {arity: 1, hands_over: "DeviceDescriptor"},
    "DeviceDescriptor.getModel": {arity: 0, hands_over: null},
    "DeviceDescriptor.getType": {arity: 0, hands_over: null},
    "DeviceDescriptor.isModelSupported": {arity: 0, hands_over: null},
    "DeviceDescriptor.isModuleTypeSupported": {arity: 1, hands_over: null},
    "DeviceDescriptor.getSupportedModuleTypeCount": {arity: 0, hands_over: null},
    "DeviceDescriptor.getSupportedModuleTypeAt": {arity: 1, hands_over: null},
    "DeviceDescriptor.getRootModule": {arity: 0, hands_over: "ModuleDescriptor"},
    "ModuleDescriptor.getModel": {arity: 0, hands_over: null},
    "ModuleDescriptor.getType": {arity: 0, hands_over: null},
    "ModuleDescriptor.isHotSwappable": {arity: 0, hands_over: null},
    "ModuleDescriptor.getSlotCount": {arity: 0, hands_over: null},
    "ModuleDescriptor.getSlotTypeAt": {arity: 1, hands_over: null},
    "ModuleDescriptor.getModuleCount": {arity: 0, hands_over: null},
    "ModuleDescriptor.getModuleAt": {arity: 1, hands_over: "ModuleDescriptor"},
    "Network.getDeviceCount": {arity: 0, hands_over: null},
    "Network.getDeviceAt": {arity: 1, hands_over: "Device"},
    "Network.getLinkCount": {arity: 0, hands_over: null},
    "Network.getLinkAt": {arity: 1, hands_over: "Link"},
    "Link.getConnectionType": {arity: 0, hands_over: null},
    "Device.getName": {arity: 0, hands_over: null},
    "Device.getModel": {arity: 0, hands_over: null},
    "Device.getType": {arity: 0, hands_over: null},
    "Device.getPortCount": {arity: 0, hands_over: null},
    "Device.getPortAt": {arity: 1, hands_over: "Port"},
    "Port.getName": {arity: 0, hands_over: null},
    "Port.getOwnerDevice": {arity: 0, hands_over: "Device"},
    /* TARGET_EVIDENCED: every entry below this marker, and none above it. */
    "Link.getObjectUuid": {arity: 0, hands_over: null},
    "Link.getPort1": {arity: 0, hands_over: "Port"},
    "Link.getPort2": {arity: 0, hands_over: "Port"},
    "Device.getObjectUuid": {arity: 0, hands_over: null},
    "Port.getObjectUuid": {arity: 0, hands_over: null}
};

/* The mark this boundary puts on every platform object it hands out.
 *
 * A receiver's interface is decided in exactly one place — from the entry of
 * the member that produced the object — and never asserted by an adapter: a
 * gate holds this name, and the function that applies it, to this file. An
 * object without the mark was not handed out here, so calling it would be
 * calling the platform from outside the boundary. */
var MUEJEJE_PLATFORM_HANDLE = {};

function muejejeAdapterHandle(platformInterface, platformObject) {
    return {
        mark: MUEJEJE_PLATFORM_HANDLE,
        platform_interface: platformInterface,
        platform_object: platformObject
    };
}

/* THE PLATFORM-CALL BOUNDARY. One interface member, called on a platform
 * object this boundary handed out, with the reason it can fail decided here
 * rather than by whoever wrote the call site.
 *
 * A member outside the allowlist, a call with the wrong number of arguments, a
 * receiver this boundary never handed out, and a member asked of an interface
 * that does not declare it are all refused with a plain error before anything
 * is touched: each is a defect in this artifact, so none may come back looking
 * like something Packet Tracer did. A member that is not there is reported as
 * absent rather than as a failed call, because nothing was called: "this
 * object does not offer that member" and "the call did not return" are
 * different observations with different next steps. */
function muejejeAdapterCall(receiver, member) {
    var name = muejejeAdapterAdmitted(receiver, member, 0, null);
    var answer;
    try {
        answer = receiver.platform_object[name]();
    } catch (platformError) {
        throw MUEJEJE_PLATFORM_CALL_FAILED;
    }
    return muejejeAdapterAnswer(member, answer);
}

/* The same boundary for a member whose documented signature takes one
 * argument. A separate function rather than an optional parameter, and the
 * entry says which of the two a member needs, so a call site that forgets the
 * argument is refused rather than silently becoming the no-argument call.
 *
 * The argument is named `argument` and not `index` because it is not always
 * one: `getAvailableDeviceAt(int)` is addressed by position, while
 * `isModuleTypeSupported(ModuleType)` is handed a *value* the platform itself
 * produced. Calling that value an index would say the type space is an
 * enumeration this artifact walks, which is the reading MJ-014 prevents. */
function muejejeAdapterCallWith(receiver, member, argument) {
    var name = muejejeAdapterAdmitted(receiver, member, 1, argument);
    var answer;
    try {
        answer = receiver.platform_object[name](argument);
    } catch (platformError) {
        throw MUEJEJE_PLATFORM_CALL_FAILED;
    }
    return muejejeAdapterAnswer(member, answer);
}

/* Everything checked before a member is called, in the order that keeps the
 * attribution honest: what this artifact asked for, then what it asked it of,
 * then what the platform object offers. Returns the bare member name.
 *
 * A null receiver is the one receiver problem that is the platform's: it is
 * what a member that handed over nothing returned, relayed by an adapter that
 * needed an object there. Every other receiver problem is ours. */
function muejejeAdapterAdmitted(receiver, member, arity, argument) {
    if (!Object.prototype.hasOwnProperty.call(
        MUEJEJE_PLATFORM_READ_ONLY_CALLS, member
    )) {
        throw new Error("muejeje: platform call outside the read-only boundary");
    }
    if (MUEJEJE_PLATFORM_READ_ONLY_CALLS[member].arity !== arity) {
        throw new Error("muejeje: platform call with the wrong number of arguments");
    }
    /* Both checks above are defects here and become no reading, so the stage
     * starts below them. From here on this member is where a reading stopped,
     * an adapter's own validator included: it refused this call's answer. */
    muejejeReadingStage(member, argument);
    if (receiver === null) {
        throw MUEJEJE_PLATFORM_UNUSABLE;
    }
    if (typeof receiver !== "object" || receiver.mark !== MUEJEJE_PLATFORM_HANDLE) {
        throw new Error("muejeje: platform call on an object this boundary did not hand out");
    }
    var parts = member.split(".");
    if (receiver.platform_interface !== parts[0]) {
        throw new Error("muejeje: platform member asked of an interface that does not declare it");
    }
    if (typeof receiver.platform_object !== "object") {
        throw MUEJEJE_PLATFORM_UNUSABLE;
    }
    if (typeof receiver.platform_object[parts[1]] !== "function") {
        throw MUEJEJE_PLATFORM_MEMBER_ABSENT;
    }
    return parts[1];
}

/* What the member handed back.
 *
 * A value is returned as it came, for a reading's own validators to hold to
 * their rules. An object is handed over marked with the interface its entry
 * names, the only place a receiver's interface is ever decided. `null` is the
 * platform handing over nothing and comes back as null, for the adapter to
 * read as what the platform said — an absent root module, a null module
 * position, a missing device inside a count — since only it knows which it
 * asked for. `undefined` is not `null`: like any other value in an object's
 * place it cannot be attributed, and that holds for every member alike. */
function muejejeAdapterAnswer(member, answer) {
    var handsOver = MUEJEJE_PLATFORM_READ_ONLY_CALLS[member].hands_over;
    if (handsOver === null) {
        return answer;
    }
    if (answer === null) {
        return null;
    }
    if (typeof answer !== "object") {
        throw MUEJEJE_PLATFORM_UNUSABLE;
    }
    return muejejeAdapterHandle(handsOver, answer);
}

/* The platform object, or null when there is none. Asking "is there a Packet
 * Tracer here" is a platform question, so it is answered here rather than in
 * every adapter that would otherwise have to name `ipc` to ask it — and what
 * comes back is already marked as the interface Cisco documents `ipc` to be.
 * Every reading starts here, so the stage is cleared here too. */
function muejejeAdapterPlatform() {
    muejejeReadingStage(null, null);
    if (typeof ipc === "undefined" || ipc === null) {
        return null;
    }
    return muejejeAdapterHandle("IPC", ipc);
}
