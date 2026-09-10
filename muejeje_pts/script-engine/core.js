/*
 * Muejeje runtime — core.
 *
 * Constants and session state. Nothing else lives here: no envelope, no
 * dispatch, no operation, no platform call. Every other kernel file may read
 * this one, and this one reads none of them, which is what makes the
 * dependency direction checkable rather than arguable.
 *
 * Packet Tracer evaluates the Script Engine files in the order the Scripting
 * Interface lists them, and this file is first. The session identity below is
 * therefore established exactly once per Script Module session.
 */

var MUEJEJE_CORE = {
    EXTENSION_NAME: "muejeje",
    EXTENSION_VERSION: "0.1.0",

    /* The only protocol this runtime speaks. There is no fallback to an
     * earlier one: a request that is not V6 is refused, never reinterpreted. */
    PROTOCOL_VERSION: 6,
    PROTOCOL_VERSIONS: [6],

    /* Capabilities of the kernel itself, each one true of the code in this
     * artifact and verifiable from it. A feature is named here only once
     * something behind it exists; the list is not a roadmap. */
    SUPPORTED_FEATURES: [
        "protocol.v6",
        "runtime.operation_catalog",
        "runtime.session_id"
    ],

    /* Provenance is not bound into the artifact. The source SHA and the build
     * recipe id are decided by the build audit, outside the runtime, and the
     * artifact SHA-256 is measured externally and never embedded in the bytes
     * it describes. Saying UNBOUND is the truthful answer; inventing either
     * value would make the runtime claim an identity nobody verified. */
    PROVENANCE_UNBOUND: "UNBOUND",

    session: {
        id: null,
        started: false,
        started_at: null,
        stopped_at: null,
        start_count: 0
    }
};

/* A per-evaluation correlation token.
 *
 * Non-secret by construction, and deliberately so: it exists to let two
 * observations be attributed to the same Script Module evaluation, and it is
 * never authentication. It carries no privilege, grants nothing, and proves
 * nothing about who is calling. A caller that treats it as a credential has
 * misread the contract.
 *
 * It is generated exactly once — Packet Tracer evaluates this file once — and
 * is therefore stable for the life of that evaluation, including across a
 * cleanUp()/main() cycle, because restarting the module is not re-evaluating
 * it.
 *
 * What it is not is globally unique. It is a clock reading and a random draw,
 * and the engine guarantees neither: two evaluations may in principle produce
 * the same token, and nothing here would detect it. Correlation is therefore
 * scoped to one observation window; a consumer that needs identity wider than
 * that carries its own and correlates on both. */
function muejejeCoreNewSessionId() {
    var moment = Date.now().toString(36);
    var entropy = Math.floor(Math.random() * 4294967296).toString(36);
    return "mjs-" + moment + "-" + entropy;
}

MUEJEJE_CORE.session.id = muejejeCoreNewSessionId();

/* A copy, so that reading the session can never modify it. */
function muejejeCoreSession() {
    return {
        id: MUEJEJE_CORE.session.id,
        started: MUEJEJE_CORE.session.started,
        started_at: MUEJEJE_CORE.session.started_at,
        stopped_at: MUEJEJE_CORE.session.stopped_at,
        start_count: MUEJEJE_CORE.session.start_count
    };
}

function muejejeCoreMarkStarted() {
    MUEJEJE_CORE.session.started = true;
    MUEJEJE_CORE.session.started_at = Date.now();
    MUEJEJE_CORE.session.stopped_at = null;
    MUEJEJE_CORE.session.start_count = MUEJEJE_CORE.session.start_count + 1;
}

function muejejeCoreMarkStopped() {
    MUEJEJE_CORE.session.started = false;
    MUEJEJE_CORE.session.stopped_at = Date.now();
}
