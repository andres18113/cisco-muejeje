/*
 * Muejeje runtime — bounded V6 request admission.
 *
 * Decides whether a caller's string may be answered at all, and refuses it
 * with the envelope `020_protocol_v6.js` shapes when it may not. It knows nothing
 * about which operations exist: it is handed an operation's argument rules by
 * the dispatcher and never reads the whitelist itself (MJ-019).
 *
 * A caller-supplied string is only ever parsed as data. Nothing here executes
 * it, and nothing here reflects it back (MJ-009).
 *
 * EVERY BOUND BELOW IS MUEJEJE'S OWN. None of them is a Packet Tracer limit:
 * nothing in this repository has measured what PT's Script Engine accepts, so
 * a number presented as the platform's would be a claim about `9.0.1.0858`
 * with no evidence behind it (MJ-015). They exist for two reasons that hold
 * whatever the platform allows — refusing an input should cost one comparison
 * rather than a full parse, and what one request can cost the engine should be
 * decided here rather than by whoever sent it. A consumer that needs more than
 * a bound allows is a reason to revisit that number with a stated case, never
 * a reason to accept an unbounded input (MJ-029).
 */

var MUEJEJE_V6_LIMITS = {
    /* The request string, measured before it is parsed. */
    REQUEST_CHARS: 65536,
    /* A correlation id is compared, echoed and written into evidence. */
    RID_CHARS: 128,
    /* An operation name is `namespace.name`; this bounds the whole. */
    OP_CHARS: 64,
    /* How many fields `args` may carry at all. Which of them an operation
     * admits is the operation's own answer, and a different refusal. */
    ARG_COUNT: 8,
    ARG_STRING_CHARS: 256
};

/* Printable ASCII, and nothing else. A rid and an op are compared, echoed and
 * recorded, and holding them to one encoding keeps those three readings of the
 * same value identical. */
var MUEJEJE_V6_PRINTABLE = /^[\x20-\x7e]+$/;
/* `namespace.name`: two lowercase segments, one separator. Which namespaces
 * exist is the dispatcher's answer, so none is enumerated here and an
 * unadmitted one fails closed there. */
var MUEJEJE_V6_OP_NAME = /^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$/;

var MUEJEJE_V6_ENVELOPE_FIELDS = ["v", "operation_rid", "op", "args"];

function muejejeV6IsPlainObject(value) {
    return (
        value !== null
        && typeof value === "object"
        && Object.prototype.toString.call(value) !== "[object Array]"
    );
}

function muejejeV6OwnKeys(value) {
    var keys = [];
    for (var key in value) {
        if (Object.prototype.hasOwnProperty.call(value, key)) {
            keys.push(key);
        }
    }
    return keys;
}

function muejejeV6Rejected(rid, op, code, message) {
    return {ok: false, envelope: muejejeV6Fail(rid, op, code, message)};
}

/* A caller-supplied string that is not a usable value becomes null rather than
 * a partial one: an id we will not accept is not an id. */
function muejejeV6BoundedString(value, limit) {
    if (typeof value !== "string" || value.length === 0 || value.length > limit) {
        return null;
    }
    if (!MUEJEJE_V6_PRINTABLE.test(value)) {
        return null;
    }
    return value;
}

/* Turn the caller's string into an object, or refuse it. Everything this step
 * can reject is MALFORMED_REQUEST: nothing was readable, so there is no
 * protocol version to disagree with and no correlation id to preserve. Length
 * is checked first, so an oversized payload never reaches the parser. */
function muejejeV6DecodeRequest(requestJson) {
    if (typeof requestJson !== "string") {
        return muejejeV6Rejected(
            null, null, MUEJEJE_V6_ERRORS.MALFORMED_REQUEST,
            "request must be a JSON string"
        );
    }
    if (requestJson.length > MUEJEJE_V6_LIMITS.REQUEST_CHARS) {
        return muejejeV6Rejected(
            null, null, MUEJEJE_V6_ERRORS.MALFORMED_REQUEST,
            "request is longer than this runtime accepts"
        );
    }
    var parsed;
    try {
        parsed = JSON.parse(requestJson);
    } catch (parseError) {
        return muejejeV6Rejected(
            null, null, MUEJEJE_V6_ERRORS.MALFORMED_REQUEST,
            "request is not valid JSON"
        );
    }
    if (!muejejeV6IsPlainObject(parsed)) {
        return muejejeV6Rejected(
            null, null, MUEJEJE_V6_ERRORS.MALFORMED_REQUEST,
            "request must be a JSON object"
        );
    }
    return {ok: true, request: parsed};
}

/* Validate the envelope. Returns either `{ok: true, request: ...}` or
 * `{ok: false, envelope: ...}`; it never throws and never dispatches.
 *
 * The order matters and is part of the contract. `operation_rid` is recovered
 * before anything can reject, so a refusal is still correlatable — but only if
 * the caller supplied a usable one. A rid is never generated: an answer
 * correlated to a request nobody made is worse than an uncorrelated one. */
function muejejeV6ParseRequest(requestJson) {
    var decoded = muejejeV6DecodeRequest(requestJson);
    if (!decoded.ok) {
        return decoded;
    }
    var parsed = decoded.request;
    var rid = muejejeV6BoundedString(
        parsed.operation_rid, MUEJEJE_V6_LIMITS.RID_CHARS
    );
    var op = muejejeV6OperationName(parsed.op);
    if (parsed.v !== MUEJEJE_CORE.PROTOCOL_VERSION) {
        return muejejeV6Rejected(
            rid, op, MUEJEJE_V6_ERRORS.PROTOCOL_MISMATCH,
            "request must declare protocol 6"
        );
    }
    var shapeError = muejejeV6EnvelopeShapeError(parsed, rid, op);
    if (shapeError !== null) {
        return muejejeV6Rejected(
            rid, op, MUEJEJE_V6_ERRORS.INVALID_REQUEST, shapeError
        );
    }
    return {
        ok: true,
        request: {operation_rid: rid, op: op, args: parsed.args}
    };
}

/* An operation name, or null. A name the envelope could not carry is not an
 * unknown operation: it never reached the whitelist, and reporting it as
 * unknown would send a caller looking for an operation. */
function muejejeV6OperationName(value) {
    var bounded = muejejeV6BoundedString(value, MUEJEJE_V6_LIMITS.OP_CHARS);
    if (bounded === null || !MUEJEJE_V6_OP_NAME.test(bounded)) {
        return null;
    }
    return bounded;
}

/* The envelope carries exactly four fields, all of them required, all of them
 * bounded. Returns the fixed message for the first violation, or null. */
function muejejeV6EnvelopeShapeError(parsed, rid, op) {
    var present = muejejeV6OwnKeys(parsed);
    if (present.length !== MUEJEJE_V6_ENVELOPE_FIELDS.length) {
        return "envelope must carry exactly v, operation_rid, op and args";
    }
    for (var i = 0; i < MUEJEJE_V6_ENVELOPE_FIELDS.length; i++) {
        if (!Object.prototype.hasOwnProperty.call(
            parsed, MUEJEJE_V6_ENVELOPE_FIELDS[i]
        )) {
            return "envelope must carry exactly v, operation_rid, op and args";
        }
    }
    if (rid === null) {
        return "operation_rid must be a bounded printable string";
    }
    if (op === null) {
        return "op must be a bounded printable namespace.name";
    }
    return muejejeV6ArgsShapeError(parsed.args);
}

/* `args` is a bounded, flat object of bounded scalars. Flat on purpose: a
 * nested value has no bound of its own, so admitting one would put the cost of
 * reading a request back in the caller's hands. An operation that one day
 * needs structure gets it as a declared rule, never as an unbounded object
 * nobody validated. */
function muejejeV6ArgsShapeError(args) {
    if (!muejejeV6IsPlainObject(args)) {
        return "args must be an object";
    }
    var supplied = muejejeV6OwnKeys(args);
    if (supplied.length > MUEJEJE_V6_LIMITS.ARG_COUNT) {
        return "args carries more fields than the envelope admits";
    }
    for (var i = 0; i < supplied.length; i++) {
        if (!muejejeV6IsBoundedScalar(args[supplied[i]])) {
            return "args values must be bounded scalars";
        }
    }
    return null;
}

function muejejeV6IsBoundedScalar(value) {
    if (value === null || typeof value === "boolean") {
        return true;
    }
    if (typeof value === "number") {
        return isFinite(value);
    }
    return (
        typeof value === "string"
        && value.length <= MUEJEJE_V6_LIMITS.ARG_STRING_CHARS
    );
}
