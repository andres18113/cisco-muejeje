/*
 * Muejeje runtime — the `runtime.capabilities` operation.
 *
 * Read-only. It answers one question — *what does this kernel admit right
 * now* — and it answers it from the kernel itself, so it performs no Cisco IPC
 * call and the module needs no privilege to serve it.
 *
 * Everything reported here exists in this artifact. Nothing here is a roadmap:
 * a transport and every mutating operation are absent, and the honest way to
 * say so is to leave them out of the answer rather than to list them as
 * pending. A capability report that names what is coming is a report a
 * consumer cannot act on.
 *
 * A platform adapter *does* exist now, and that changes nothing here. Which
 * operations are admitted, and which kernel features stand behind them, are
 * facts about this artifact and are reported; whether Packet Tracer answers
 * one of them is not, and is never folded in. Discovery that depended on a
 * platform call would turn one unavailable platform into "this runtime has no
 * capabilities" (MJ-028, MJ-031).
 *
 * It also reaches no verdict. A verification outcome is not something this
 * runtime may certify about itself — the engine cannot audit the engine — so
 * it reports observations and Python decides what they establish (MJ-011).
 *
 * As with `runtime.identify`, the whitelist is handed in by the dispatcher
 * rather than read from it. The arrow points from dispatch to operation and
 * never back (MJ-019).
 */

/* `args` is validated against the empty whitelist before this runs, so it is
 * always an empty object here; it stays in the signature because every V6
 * handler has the same shape. */
function muejejeRuntimeCapabilities(args, context) {
    return {
        runtime_session_id: muejejeCoreSession().id,
        protocol_versions: MUEJEJE_CORE.PROTOCOL_VERSIONS.slice(0),
        operations: muejejeCapabilityOperations(context),
        supported_features: MUEJEJE_CORE.SUPPORTED_FEATURES.slice(0)
    };
}

/* The admitted operations, each with the one property a caller must know
 * before sending it: whether it can change anything. `runtime.identify`
 * reports the same set as bare names; this is that set with its read-only
 * flag, and the two can never disagree because both come from the dispatcher.
 *
 * The entries are rebuilt rather than passed through, so the answer shares no
 * object with the whitelist and a consumer cannot reach the table through it.
 */
function muejejeCapabilityOperations(context) {
    if (context === null || typeof context !== "object") {
        return [];
    }
    var catalog = context.operation_catalog;
    if (Object.prototype.toString.call(catalog) !== "[object Array]") {
        return [];
    }
    var operations = [];
    for (var i = 0; i < catalog.length; i++) {
        operations.push({
            op: catalog[i].op,
            read_only: catalog[i].read_only === true
        });
    }
    return operations;
}
