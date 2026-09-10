/*
 * Muejeje runtime — the V6 dispatcher.
 *
 * The one entry point consumers call, and the one place that decides whether
 * an operation is admitted. It whitelists and dispatches; it implements no
 * operation and validates no envelope, because both belong elsewhere.
 *
 * `mcpDispatchV6` is declared exactly once in this artifact. Two dispatchers
 * would mean two answers to "what actually ran", and evidence would stop being
 * attributable (MJ-007).
 */

/* Built on first use rather than at evaluation time, so this file makes no
 * assumption about the order Packet Tracer evaluated the others in. */
var MUEJEJE_V6_DISPATCH = {table: null};

function muejejeV6OperationTable() {
    if (MUEJEJE_V6_DISPATCH.table === null) {
        MUEJEJE_V6_DISPATCH.table = {
            "runtime.capabilities": {
                read_only: true,
                args: {},
                handler: function (args, context) {
                    return muejejeRuntimeCapabilities(args, context);
                }
            },
            "runtime.identify": {
                read_only: true,
                args: {},
                handler: function (args, context) {
                    return muejejeRuntimeIdentify(args, context);
                }
            }
        };
    }
    return MUEJEJE_V6_DISPATCH.table;
}

function muejejeV6OperationNames() {
    var table = muejejeV6OperationTable();
    var names = [];
    for (var name in table) {
        if (Object.prototype.hasOwnProperty.call(table, name)) {
            names.push(name);
        }
    }
    names.sort();
    return names;
}

/* The whitelist as data a caller may be told about: each admitted name with
 * the property that bounds what sending it can do. Derived here, where the
 * whitelist lives, so no operation can publish a claim about admission that
 * the dispatcher would not honour.
 *
 * The argument rules stay behind: they are how a request is refused, not
 * something a caller is invited to reason about, and publishing them would
 * make the kernel's own validation part of the consumer contract (MJ-005). */
function muejejeV6OperationCatalog() {
    var table = muejejeV6OperationTable();
    var names = muejejeV6OperationNames();
    var catalog = [];
    for (var i = 0; i < names.length; i++) {
        catalog.push({
            op: names[i],
            read_only: table[names[i]].read_only === true
        });
    }
    return catalog;
}

/* The single V6 entry point. Takes a JSON string, returns a JSON string.
 *
 * It never throws: every outcome the engine can reach is an envelope, because
 * an uncaught error inside a Script Engine call is not something a consumer
 * can correlate, diagnose or retry. */
function mcpDispatchV6(requestJson) {
    var parsed = muejejeV6ParseRequest(requestJson);
    if (!parsed.ok) {
        return muejejeV6Encode(parsed.envelope);
    }
    var request = parsed.request;
    var table = muejejeV6OperationTable();
    if (!Object.prototype.hasOwnProperty.call(table, request.op)) {
        return muejejeV6Encode(muejejeV6Fail(
            request.operation_rid, request.op,
            MUEJEJE_V6_ERRORS.UNKNOWN_OPERATION,
            "operation is not admitted by the V6 whitelist"
        ));
    }
    var operation = table[request.op];
    var argsError = muejejeV6ArgsError(request.args, operation.args);
    if (argsError !== null) {
        return muejejeV6Encode(muejejeV6Fail(
            request.operation_rid, request.op,
            MUEJEJE_V6_ERRORS.INVALID_ARGS, argsError
        ));
    }
    return muejejeV6Encode(muejejeV6Run(request, operation));
}

/* The handler runs behind one boundary, and its failure is the only thing in
 * V6 that may be reported as an engine exception. The thrown value is not
 * carried into the envelope: it is engine-internal, and a consumer that could
 * read it would be depending on an internal (MJ-005). */
function muejejeV6Run(request, operation) {
    var context = {
        operations: muejejeV6OperationNames(),
        operation_catalog: muejejeV6OperationCatalog()
    };
    try {
        return muejejeV6Ok(
            request.operation_rid, request.op,
            operation.handler(request.args, context)
        );
    } catch (handlerError) {
        return muejejeV6Fail(
            request.operation_rid, request.op,
            MUEJEJE_V6_ERRORS.ENGINE_EXCEPTION,
            "the operation handler failed"
        );
    }
}
