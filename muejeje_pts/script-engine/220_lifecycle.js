/*
 * Muejeje runtime — module lifecycle.
 *
 * Packet Tracer evaluates every script-engine file in the order the Scripting
 * Interface lists them, calls main() when the Script Module starts, and calls
 * cleanUp() when it stops. This file owns that lifecycle and nothing else: the
 * session state it records lives in core, so an operation can read it without
 * depending on the lifecycle (MJ-019).
 *
 * Deliberately absent, and not an oversight:
 *   - no dispatch and no operation — both live in their own files;
 *   - no transport, no polling, no file mailbox;
 *   - no IPC call at all, so the module needs no privilege to start;
 *   - no device, topology, addressing or scenario concept of any kind.
 *
 * Each Script Module runs in its own sandbox, so these names are ours alone and
 * do not collide with any other module's main()/cleanUp().
 */

function main() {
    muejejeCoreMarkStarted();
}

function cleanUp() {
    muejejeCoreMarkStopped();
}

/* Read-only view of the lifecycle for the Custom Interface. It reports what
 * this module observed about itself and asserts nothing about Packet Tracer. */
function muejejeLifecycleState() {
    return muejejeCoreSession();
}
