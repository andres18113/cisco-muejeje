/*
 * Muejeje runtime — Runtime Protocol V6 envelope and failure taxonomy.
 *
 * One envelope shape and one code per cause, and nothing else. This file does
 * not read a request, does not decide whether one is admissible, does not know
 * which operations exist, and never calls a handler: it shapes the answer.
 * Whether a request may be answered at all is `validation_v6.js`.
 *
 * The whole surface is JSON in, JSON out. There is no code path that executes
 * a caller's JavaScript, because there is no code path that treats a caller's
 * string as anything but data (MJ-009).
 *
 * Error messages are fixed strings. A message never echoes a field name, an
 * operation name or a value the caller supplied: failing closed includes not
 * reflecting what was refused. A message is diagnostic prose rather than a
 * contract field — `error.code` is what a consumer branches on (MJ-030).
 */

var MUEJEJE_V6_ERRORS = {
    /* Not a JSON string, not a JSON object, or longer than this runtime
     * accepts. Nothing could be read. */
    MALFORMED_REQUEST: "MALFORMED_REQUEST",
    /* Read, but not addressed to protocol 6. Never reinterpreted. */
    PROTOCOL_MISMATCH: "PROTOCOL_MISMATCH",
    /* A V6 envelope that does not satisfy the envelope contract, including its
     * bounds: an envelope too large to carry is not a valid envelope. */
    INVALID_REQUEST: "INVALID_REQUEST",
    /* A V6 envelope naming an operation the whitelist does not admit. */
    UNKNOWN_OPERATION: "UNKNOWN_OPERATION",
    /* A whitelisted operation given an argument it does not support, or one
     * whose value falls outside the rule the operation declares for it. */
    INVALID_ARGS: "INVALID_ARGS",
    /* The only code that means "the engine itself broke". No validation
     * failure may use it: nothing went wrong inside the engine when a request
     * was simply not admissible, and a bound is a validation failure. */
    ENGINE_EXCEPTION: "ENGINE_EXCEPTION"
};

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
