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
 * EVERY BOUND HERE IS MUEJEJE'S OWN. None of them is a Packet Tracer limit:
 * nothing in this repository has measured how many models the factory offers
 * or how large a chassis descriptor can be, so a number presented as the
 * platform's would be a claim about `9.0.1.0858` with no evidence behind it
 * (MJ-015). Each is a limit on what one call will do, and a read past one is
 * reported as truncated, so an omitted tail stays visibly absent and can never
 * be read as an observed absence (MJ-029).
 *
 * A VALIDATOR REFUSING AN ANSWER IS A READING; a validator throwing for any
 * other reason is not. The distinction is `muejejeReadingReason` below, and it
 * is the whole of why a bug in this artifact cannot leave it wearing Packet
 * Tracer's name (MJ-022, MJ-031).
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
    MAX_MODEL_CHARS: 256,
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
    MAX_SLOTS: 64
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
 * platform: two raised at the call boundary, one raised by a validator below.
 * Anything else got there from our own code, so it is rethrown for the
 * dispatcher to report as an engine exception. Swallowing it would publish a
 * platform observation nobody observed (MJ-031). */
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

function muejejeReadingCount(value) {
    if (
        typeof value !== "number" || value % 1 !== 0 || value < 0
        || value > MUEJEJE_PLATFORM_LIMITS.MAX_COUNT
    ) {
        throw MUEJEJE_PLATFORM_UNUSABLE;
    }
    return value;
}

function muejejeReadingWholeNumber(value) {
    if (typeof value !== "number" || value % 1 !== 0) {
        throw MUEJEJE_PLATFORM_UNUSABLE;
    }
    return value;
}

/* An empty model is a real answer, not a malformed one: on 9.0.1 a chassis
 * root can report "". Requiring a name here discarded correct metadata once
 * already, so the only thing checked is that it is a bounded string — and the
 * bound is a length of its own, not a count reused as one. */
function muejejeReadingModel(value) {
    if (
        typeof value !== "string"
        || value.length > MUEJEJE_PLATFORM_LIMITS.MAX_MODEL_CHARS
    ) {
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
