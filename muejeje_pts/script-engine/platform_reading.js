/*
 * Muejeje runtime — what a platform reading is.
 *
 * The vocabulary and the value rules every platform reading in this artifact
 * is held to, and nothing else: it names no platform object, makes no call,
 * reads no request and shapes no envelope. The adapters that do call Packet
 * Tracer are declared elsewhere (MJ-031); this file is what they report *in*,
 * so that readings of different subjects cannot quietly come to mean different
 * things.
 *
 * THREE DIFFERENT THINGS LIMIT A READING, AND ONLY TWO OF THEM ARE OURS.
 *
 *   work per request   how much one call does: how many entries one window
 *                      carries, how far one walk goes, how long one string
 *                      may be. Muejeje's own, and a reading that stops at one
 *                      says so, so an omitted tail stays visibly absent and is
 *                      never read as an observed absence.
 *   numeric fidelity   which numbers this runtime can carry and hand back
 *                      unchanged. Muejeje's own too — a fact about how a JSON
 *                      number travels, not about Packet Tracer — and not a
 *                      work bound: a request costs the same at position three
 *                      as at position three trillion.
 *   capacity           how many models, devices or ports exist. Only the
 *                      platform answers that, nothing here bounds it, and a
 *                      consumer pages through it one window at a time.
 *
 * Nothing in this repository has measured a Packet Tracer limit, so no number
 * here is presented as one (MJ-015, MJ-029). An earlier revision capped every
 * index at 4096 and refused any count above 65536. Neither bounded work — the
 * window already did — and together they made a large enough workspace
 * unreadable rather than paged.
 *
 * A VALIDATOR REFUSING AN ANSWER IS A READING; a validator throwing for any
 * other reason is not. The distinction is `muejejeReadingReason` below, and it
 * is the whole of why a bug in this artifact cannot leave it wearing Packet
 * Tracer's name (MJ-022, MJ-031).
 */

var MUEJEJE_PLATFORM_LIMITS = {
    /* WORK PER REQUEST: how many entries one reading of each enumeration
     * carries. More entries past a window are reported, and a consumer asks
     * for the next window; none of these says how many models a factory
     * offers or how many devices a workspace holds. */
    MAX_FACTORY_WINDOW: 32,
    MAX_WORKSPACE_WINDOW: 64,
    MAX_MODULE_TYPES: 64,
    MAX_SLOTS: 64,
    /* A chassis descriptor is a tree, and a tree has no bound this repository
     * has measured either. These two are what one call will walk. They are
     * not small: this repository's own recorded factory survey against
     * 9.0.1.0858 found real chassis trees that a 64-node, depth-8 ceiling
     * truncated, and a bound that routinely truncates a correct answer teaches
     * a reader to ignore the truncation mark. So they are set well clear of
     * the largest tree anybody here has recorded, and every subtree they do
     * omit is still marked. */
    MAX_MODULE_NODES: 512,
    MAX_MODULE_DEPTH: 12,
    /* How long a model or a name in one reading may be. Devices are named
     * however somebody named them and no ceiling on a name has been measured;
     * this bounds the size of an answer, and the caller says which. */
    MAX_MODEL_CHARS: 256,
    MAX_NAME_CHARS: 256,
    /* NUMERIC FIDELITY: one domain for every number this artifact publishes
     * or admits back — an index, a count, a DeviceType, a ModuleType.
     *
     * It is the range in which a whole number is still exactly the number
     * that was sent. Past it, a JSON number no longer round-trips — one past
     * the end is indistinguishable from two past it — so what came back would
     * not be what went out, and a consumer relaying a value could not tell.
     * Indexes and counts take the non-negative half; platform values take
     * both, because the platform is the authority on their sign.
     *
     * RELAY CLOSURE turns on this being one declaration (MJ-029). A value a
     * reading publishes is held to it here, and every operation that admits
     * such a value back names the same two bounds, so this runtime can never
     * emit a number it then refuses. */
    EXACT_INTEGER_MIN: -9007199254740991,
    EXACT_INTEGER_MAX: 9007199254740991
};

/* Why a reading is unavailable. Four different facts, kept apart because a
 * consumer acts differently on each.
 *
 * ABSENT         there is no platform object here at all.
 * MEMBER_ABSENT  the object is here and does not offer the member. Nothing was
 *                called, so nothing failed: this says the interface is not the
 *                one this artifact was written against, which is a different
 *                next step from a call that was refused.
 * CALL_FAILED    the member was called and the call did not return. What made
 *                it fail is not something this adapter can see, so it does not
 *                say — and in particular it does not name a privilege.
 * UNUSABLE       the platform answered, and the answer could not be attributed:
 *                a count that is not a whole number, a missing descriptor. */
var MUEJEJE_PLATFORM_ABSENT = "PLATFORM_ABSENT";
var MUEJEJE_PLATFORM_MEMBER_ABSENT = "PLATFORM_MEMBER_ABSENT";
var MUEJEJE_PLATFORM_CALL_FAILED = "PLATFORM_CALL_FAILED";
var MUEJEJE_PLATFORM_UNUSABLE = "PLATFORM_ANSWER_UNUSABLE";

var MUEJEJE_PLATFORM_OBSERVED = "OBSERVED";
var MUEJEJE_PLATFORM_UNAVAILABLE = "UNAVAILABLE";

/* Which thrown values are a reading, and which are this artifact's own bug.
 *
 * These three sentinels are the only failures an adapter attributed to the
 * platform: raised at the call boundary, or by a validator below. Anything
 * else got there from our own code, so it is rethrown for the dispatcher to
 * report as an engine exception. Swallowing it would publish a platform
 * observation nobody observed (MJ-031). */
function muejejeReadingReason(thrown) {
    if (
        thrown !== MUEJEJE_PLATFORM_MEMBER_ABSENT
        && thrown !== MUEJEJE_PLATFORM_CALL_FAILED
        && thrown !== MUEJEJE_PLATFORM_UNUSABLE
    ) {
        throw thrown;
    }
    return thrown;
}

/* An argument this artifact handed one of its own adapters.
 *
 * It is neither a platform answer nor a caller's input: V6 admission has
 * already refused anything outside the rule an operation declares, and an
 * operation supplies its own default for an argument nobody sent. So a value
 * outside these bounds reached here from our own code, and the honest thing to
 * do with it is fail. Clamping it would answer a different question from the
 * one asked and then report the answer as an observation — the same class of
 * mistake as reporting our own bug as a platform failure (MJ-022, MJ-031). */
function muejejeReadingArgument(value, min, max) {
    if (
        typeof value !== "number" || value % 1 !== 0
        || value < min || value > max
    ) {
        throw new Error("muejeje: adapter argument outside its declared bounds");
    }
    return value;
}

/* A count the platform answered: a whole number this runtime can carry
 * exactly, and nothing more is asked of it. How large it is belongs to the
 * platform; a reading that stops short of it says so rather than refusing it. */
function muejejeReadingCount(value) {
    if (
        typeof value !== "number" || value % 1 !== 0 || value < 0
        || value > MUEJEJE_PLATFORM_LIMITS.EXACT_INTEGER_MAX
    ) {
        throw MUEJEJE_PLATFORM_UNUSABLE;
    }
    return value;
}

/* A number the platform answered in its own vocabulary — a DeviceType, a
 * ModuleType, a slot type — held to the one published domain, and never
 * translated: naming a value is a consumer's job, against Cisco's
 * documentation (MJ-014).
 *
 * RELAY CLOSURE. This is the producing half of it: every such value this
 * artifact publishes comes through here, and an operation that admits one back
 * names the same bounds. A producer that validated its own way would be a
 * second domain, and the two would drift apart the first time either was
 * edited.
 *
 * A value outside it is `PLATFORM_ANSWER_UNUSABLE` and not a refusal: the
 * platform answered, and the answer is one this runtime cannot carry back
 * unchanged, so it cannot be attributed. */
function muejejeReadingExactInteger(value) {
    if (
        typeof value !== "number" || value % 1 !== 0
        || value < MUEJEJE_PLATFORM_LIMITS.EXACT_INTEGER_MIN
        || value > MUEJEJE_PLATFORM_LIMITS.EXACT_INTEGER_MAX
    ) {
        throw MUEJEJE_PLATFORM_UNUSABLE;
    }
    return value;
}

/* A bounded string, and nothing else asked of it.
 *
 * An empty one is a real answer, not a malformed one: on 9.0.1 a chassis root
 * reports `model: ""`. Requiring a non-empty value discarded correct metadata
 * once already, so the only thing checked is the bound — and the caller passes
 * which bound, because a model name and a device name are different subjects
 * with different reasons for their length. */
function muejejeReadingText(value, limit) {
    if (typeof value !== "string" || value.length > limit) {
        throw MUEJEJE_PLATFORM_UNUSABLE;
    }
    return value;
}

function muejejeReadingFlag(value) {
    if (typeof value !== "boolean") {
        throw MUEJEJE_PLATFORM_UNUSABLE;
    }
    return value;
}
