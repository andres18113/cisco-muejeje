/*
 * Muejeje runtime — Runtime Protocol V6 envelope.
 *
 * Request validation and response envelopes, and nothing else. This file does
 * not know which operations exist, does not dispatch, and never calls a
 * handler: it decides whether a request is admissible and shapes the answer.
 *
 * The whole surface is JSON in, JSON out. There is no code path that executes
 * a caller's JavaScript, because there is no code path that treats a caller's
 * string as anything but data (MJ-009).
 *
 * Error messages are fixed strings. A message never echoes a field name, an
 * operation name or a value the caller supplied: failing closed includes not
 * reflecting what was refused.
 */

var MUEJEJE_V6_ERRORS = {
    /* Not a JSON string, or not a JSON object. Nothing could be read. */
    MALFORMED_REQUEST: "MALFORMED_REQUEST",
    /* Read, but not addressed to protocol 6. Never reinterpreted. */
    PROTOCOL_MISMATCH: "PROTOCOL_MISMATCH",
    /* A V6 envelope that does not satisfy the envelope contract. */
    INVALID_REQUEST: "INVALID_REQUEST",
    /* A V6 envelope naming an operation the whitelist does not admit. */
    UNKNOWN_OPERATION: "UNKNOWN_OPERATION",
    /* A whitelisted operation given arguments it does not support. */
    INVALID_ARGS: "INVALID_ARGS",
    /* The only code that means "the engine itself broke". No validation
     * failure may use it: nothing went wrong inside the engine when a request
     * was simply not admissible. */
    ENGINE_EXCEPTION: "ENGINE_EXCEPTION"
};

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

/* One envelope shape for every outcome, so a caller parses one thing. */
function muejejeV6Envelope(rid, op, ok, result, error) {
    return {
        v: MUEJEJE_CORE.PROTOCOL_VERSION,
        operation_rid: rid,
        op: op,
        ok: ok,
        result: result,
        error: error
    };
}

function muejejeV6Ok(rid, op, result) {
    return muejejeV6Envelope(rid, op, true, result, null);
}

function muejejeV6Fail(rid, op, code, message) {
    return muejejeV6Envelope(rid, op, false, null, {
        code: code,
        message: message
    });
}

/* The response leaves the engine as a string, symmetrically with the request.
 *
 * A handler that returns something unencodable would otherwise throw out of
 * the dispatcher and reach Packet Tracer as an uncaught error, so the failure
 * is converted here into the one envelope that is always encodable: a failure
 * carries no result. */
function muejejeV6Encode(envelope) {
    try {
        return JSON.stringify(envelope);
    } catch (encodeError) {
        return JSON.stringify(muejejeV6Fail(
            envelope.operation_rid,
            envelope.op,
            MUEJEJE_V6_ERRORS.ENGINE_EXCEPTION,
            "the response could not be encoded"
        ));
    }
}

function muejejeV6Rejected(rid, op, code, message) {
    return {ok: false, envelope: muejejeV6Fail(rid, op, code, message)};
}

/* A caller-supplied string that is not a usable value becomes null rather than
 * a partial one: an id we cannot trust is not an id. */
function muejejeV6NonEmptyString(value) {
    if (typeof value !== "string" || value.length === 0) {
        return null;
    }
    return value;
}

/* Turn the caller's string into an object, or refuse it.
 *
 * Everything this step can reject is MALFORMED_REQUEST: nothing was readable,
 * so there is no protocol version to disagree with and no correlation id to
 * preserve. A caller-supplied string is only ever parsed as data. */
function muejejeV6DecodeRequest(requestJson) {
    if (typeof requestJson !== "string") {
        return muejejeV6Rejected(
            null, null, MUEJEJE_V6_ERRORS.MALFORMED_REQUEST,
            "request must be a JSON string"
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
 * the caller actually supplied a usable one. A rid is never generated: an
 * answer correlated to a request nobody made is worse than an uncorrelated
 * one. */
function muejejeV6ParseRequest(requestJson) {
    var decoded = muejejeV6DecodeRequest(requestJson);
    if (!decoded.ok) {
        return decoded;
    }
    var parsed = decoded.request;
    var rid = muejejeV6NonEmptyString(parsed.operation_rid);
    var op = muejejeV6NonEmptyString(parsed.op);
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

/* The envelope carries exactly four fields, all of them required. Returns the
 * fixed message for the first violation, or null. */
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
        return "operation_rid must be a non-empty string";
    }
    if (op === null) {
        return "op must be a non-empty string";
    }
    if (!muejejeV6IsPlainObject(parsed.args)) {
        return "args must be an object";
    }
    return null;
}

/* Arguments are whitelisted per operation, by name, with no exceptions. An
 * operation that takes none accepts an empty object and nothing else. */
function muejejeV6ArgsError(args, allowed) {
    var supplied = muejejeV6OwnKeys(args);
    for (var i = 0; i < supplied.length; i++) {
        var admitted = false;
        for (var j = 0; j < allowed.length; j++) {
            if (allowed[j] === supplied[i]) {
                admitted = true;
            }
        }
        if (!admitted) {
            return "args carries a field this operation does not support";
        }
    }
    return null;
}
