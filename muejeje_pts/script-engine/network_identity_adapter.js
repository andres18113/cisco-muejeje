/*
 * Muejeje runtime — one workspace device's identity, in one reading. READ-ONLY.
 *
 * A declared adapter (MJ-006, MJ-019, MJ-031). It reads what the platform says
 * one device on the workspace *is* — its name, its model, its DeviceType — and
 * reports what it read without deciding what any of it establishes (MJ-011).
 *
 * It names no platform object. Every call goes through `muejejeAdapterCall` in
 * `platform_adapter.js`, which admits only the read-only getters on that list.
 *
 * ONE OBSERVATION, NOT A JOIN. Everything reported comes from a single reading
 * of a single device: the count, the device at the requested position, and each
 * fact read off that device. Nothing is carried over from an earlier reading and
 * nothing is combined with a second one. A workspace changes under a reading in
 * a way a factory catalogue does not, so two facts gathered at two moments
 * would describe a device that may never have existed in that state.
 *
 * THE INDEX IS A POSITION IN THIS READING, AND NOT AN IDENTITY. It is where the
 * platform handed this device over, in this observation, and nothing more. It
 * is not stable across readings, it is not a handle, and a consumer that stored
 * one and sent it back later is addressing whatever is in that position then.
 * Which is why the identity facts are reported beside it: they are how a
 * consumer tells *what* answered, rather than trusting the position it asked
 * about.
 *
 * IT CORRELATES NOTHING TO THE FACTORY, and that is a decision rather than an
 * omission. A workspace index is not a factory index; a device's model string
 * is not a factory descriptor; and neither equal names nor similar ones make two
 * readings the same subject. Cisco does document `Device.getDescriptor()`, which
 * would answer this properly — from the device itself, with no matching of ours
 * involved — and that is a *different subject* with its own bounds and its own
 * evidence, not a field this reading may grow. Correlating by index, by name or
 * by assumption would publish a relationship nobody observed (MJ-002, MJ-015).
 *
 * WHAT IS NOT READ HERE. `Device` also documents `getSerialNumber()`,
 * `getPower()` and `getUpTime()`. A serial number is the closest thing to an
 * identity key on this interface, and it is deliberately not in this slice: a
 * reading is all-or-nothing by design — a partial one would look like an answer
 * about the platform rather than about our inability to read it — so including
 * the getter with the least standing here would make name and model unreadable
 * on any device that does not answer it. It becomes a field when a target run
 * says what it does, and not before. `getPower` and `getUpTime` are state, not
 * identity, and belong to neither this reading nor this milestone.
 *
 * NOTHING HERE MUTATES ANYTHING. `Device` offers members that move, power and
 * rename a device; none of them is on the boundary's read-only allowlist, so
 * this file could not reach one if it tried (MJ-031).
 */

/* One result shape for every outcome, so a consumer parses one thing whether
 * the platform answered or not. It starts with every identity field empty: a
 * field is filled in only once it was actually read, in this reading, so a fact
 * this adapter never obtained cannot be left looking like one. */
function muejejeAdapterIdentityReading(resolution, reason, workspaceIndex) {
    return {
        resolution: resolution,
        unavailable_reason: reason,
        workspace_index: workspaceIndex,
        available_count: null,
        device_present: false,
        name: null,
        model: null,
        device_type: null
    };
}

function muejejeAdapterIdentityUnavailable(reason, workspaceIndex) {
    return muejejeAdapterIdentityReading(
        MUEJEJE_PLATFORM_UNAVAILABLE, reason, workspaceIndex
    );
}

/* The one entry point. An unreadable platform is an observation about the
 * platform, not an exception for the caller; an index outside this adapter's
 * own bounds is a defect in this artifact, and fails as one.
 *
 * The bound is the exact-integer limit every published index is held to — the
 * same declaration `network.device_inventory` names for its window — so every
 * index that operation publishes is one this one admits (MJ-029). */
function muejejeAdapterDeviceIdentity(workspaceIndex) {
    var index = muejejeReadingArgument(
        workspaceIndex, 0, MUEJEJE_PLATFORM_LIMITS.EXACT_INTEGER_MAX
    );
    var platform = muejejeAdapterPlatform();
    if (platform === null) {
        return muejejeAdapterIdentityUnavailable(
            MUEJEJE_PLATFORM_ABSENT, index
        );
    }
    try {
        return muejejeAdapterIdentityRead(platform, index);
    } catch (platformError) {
        /* Only the sentinels are a reading; anything else is a defect in this
         * artifact and is rethrown for the dispatcher (MJ-031). */
        return muejejeAdapterIdentityUnavailable(
            muejejeReadingReason(platformError), index
        );
    }
}

/* An index past the end is an answer, not a failure: the workspace said how
 * many devices it holds, and it holds none there. The count is read in this
 * same observation rather than assumed from an earlier one, which is what makes
 * "past the end" a statement about this reading. */
function muejejeAdapterIdentityRead(platform, index) {
    var network = muejejeAdapterCall(platform, "IPC.network");
    var reading = muejejeAdapterIdentityReading(
        MUEJEJE_PLATFORM_OBSERVED, null, index
    );
    reading.available_count = muejejeReadingCount(
        muejejeAdapterCall(network, "Network.getDeviceCount")
    );
    if (index >= reading.available_count) {
        return reading;
    }
    return muejejeAdapterIdentityFacts(
        reading, muejejeAdapterCallWith(network, "Network.getDeviceAt", index)
    );
}

/* Every fact off the one device the platform handed over, checked before it is
 * reported. A device inside the count that the platform will not hand over is
 * an answer that cannot be attributed, exactly as a missing descriptor inside
 * the model count is.
 *
 * `device_type` is reported as the platform's own number and is never matched
 * against a table of ours: naming a DeviceType is a consumer's job, against
 * Cisco's documentation, and a mirrored constant is correct only until Packet
 * Tracer changes (MJ-014). */
function muejejeAdapterIdentityFacts(reading, device) {
    if (!device) {
        throw MUEJEJE_PLATFORM_UNUSABLE;
    }
    reading.device_present = true;
    reading.name = muejejeReadingText(
        muejejeAdapterCall(device, "Device.getName"),
        MUEJEJE_PLATFORM_LIMITS.MAX_NAME_CHARS
    );
    reading.model = muejejeReadingText(
        muejejeAdapterCall(device, "Device.getModel"),
        MUEJEJE_PLATFORM_LIMITS.MAX_MODEL_CHARS
    );
    reading.device_type = muejejeReadingExactInteger(
        muejejeAdapterCall(device, "Device.getType")
    );
    return reading;
}
