/*
 * Muejeje runtime — the `runtime.identify` operation.
 *
 * Read-only. It reports what this artifact can truthfully say about itself and
 * asserts nothing about Packet Tracer, so it performs no Cisco IPC call and
 * this operation needs no privilege to answer. The module declares exactly one
 * (MJ-025), the token a recorded reading of the pinned binary says both root
 * IPC calls require, and nothing wider: a name nobody can point at evidence
 * for is refused at audit time rather than shipped to find out (MJ-032).
 *
 * The operation list is handed in by the dispatcher rather than read from it.
 * The whitelist has one owner, and the arrow still points from dispatch to
 * operation and never back (MJ-019).
 */

/* `args` is validated against the empty whitelist before this runs, so it is
 * always an empty object here; it stays in the signature because every V6
 * handler has the same shape. */
function muejejeRuntimeIdentify(args, context) {
    var session = muejejeCoreSession();
    return {
        extension_name: MUEJEJE_CORE.EXTENSION_NAME,
        extension_version: MUEJEJE_CORE.EXTENSION_VERSION,
        protocol_versions: MUEJEJE_CORE.PROTOCOL_VERSIONS.slice(0),
        operations: muejejeIdentityOperations(context),
        supported_features: MUEJEJE_CORE.SUPPORTED_FEATURES.slice(0),
        runtime_session_id: session.id,
        provenance: muejejeIdentityProvenance(),
        lifecycle: {
            started: session.started,
            started_at: session.started_at,
            stopped_at: session.stopped_at,
            start_count: session.start_count
        }
    };
}

/* Whatever the dispatcher admits, and nothing else. A caller reading this list
 * must be able to send every name on it. */
function muejejeIdentityOperations(context) {
    if (context === null || typeof context !== "object") {
        return [];
    }
    if (Object.prototype.toString.call(context.operations) !== "[object Array]") {
        return [];
    }
    return context.operations.slice(0);
}

/* Nothing binds a source SHA or a build recipe id into this artifact, so both
 * are reported as unbound rather than guessed. `state` is what a caller checks;
 * the two nulls are there so the field set does not change when a future build
 * does bind them. The artifact's own SHA-256 is measured outside the artifact
 * and is never embedded in it (MJ-017). */
function muejejeIdentityProvenance() {
    return {
        state: MUEJEJE_CORE.PROVENANCE_UNBOUND,
        source_sha: null,
        build_recipe_id: null
    };
}
