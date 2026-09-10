/*
 * Muejeje runtime — module lifecycle.
 *
 * Packet Tracer evaluates every script-engine file in the order the Scripting
 * Interface lists them, calls main() when the Script Module starts, and calls
 * cleanUp() when it stops. This file owns that lifecycle and nothing else.
 *
 * Deliberately absent, and not an oversight:
 *   - no dispatcher and no operations (Runtime Protocol V6 is not implemented);
 *   - no transport, no polling, no file mailbox;
 *   - no IPC call at all, so the module needs no privilege to start;
 *   - no device, topology, addressing or scenario concept of any kind.
 *
 * Each Script Module runs in its own sandbox, so these names are ours alone and
 * do not collide with any other module's main()/cleanUp().
 */

var MUEJEJE_LIFECYCLE = {
    started: false,
    startedAt: null,
    stoppedAt: null,
    startCount: 0
};

/* Read-only view of the lifecycle, for a future identity operation to build on.
 * It reports what this module observed about itself and asserts nothing about
 * Packet Tracer. */
function muejejeLifecycleState() {
    return {
        started: MUEJEJE_LIFECYCLE.started,
        started_at: MUEJEJE_LIFECYCLE.startedAt,
        stopped_at: MUEJEJE_LIFECYCLE.stoppedAt,
        start_count: MUEJEJE_LIFECYCLE.startCount
    };
}

function main() {
    MUEJEJE_LIFECYCLE.started = true;
    MUEJEJE_LIFECYCLE.startedAt = Date.now();
    MUEJEJE_LIFECYCLE.stoppedAt = null;
    MUEJEJE_LIFECYCLE.startCount = MUEJEJE_LIFECYCLE.startCount + 1;
}

function cleanUp() {
    MUEJEJE_LIFECYCLE.started = false;
    MUEJEJE_LIFECYCLE.stoppedAt = Date.now();
}
