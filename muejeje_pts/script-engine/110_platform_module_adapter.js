/*
 * Muejeje runtime — the chassis-module descriptor reading. READ-ONLY.
 *
 * A declared adapter (MJ-006, MJ-019, MJ-031): it reads what hardware one
 * device *model* is described as carrying — the root module of its factory
 * descriptor, and the module tree under it — and reports what it read without
 * deciding what any of it establishes (MJ-011).
 *
 * It names no platform object. Every call goes through `muejejeAdapterCall` in
 * `060_platform_adapter.js`, which admits only the read-only getters on that list.
 *
 * A DESCRIPTOR IS NOT INSTALLED HARDWARE. `DeviceDescriptor.getRootModule()`
 * describes what a model can accept; it instantiates nothing, powers nothing,
 * and says nothing about a device on a workspace. The runtime `Module` surface
 * — reached from the network, not from the hardware factory — is a different
 * interface with different getters, and the two are never mixed (MJ-014).
 *
 * A MODEL IS ADDRESSED BY ITS INDEX IN THE FACTORY ENUMERATION, never by a
 * DeviceType and never by a name this artifact knows (MJ-002, MJ-014). Neither
 * would address one entry anyway: on 9.0.1.0858, entries sharing a model and a
 * DeviceType were read with different trees. The index names an entry as this
 * reading enumerated it, not an identity that outlives the observation, and the
 * identity actually read is reported back beside it.
 *
 * THE WALK IS BOUNDED AND SAYS SO. The ceilings are Muejeje's own (MJ-029), and
 * every subtree they omit is marked: a truncated branch stays visibly absent
 * and can never be read as an observed absence.
 */

/* One result shape for every outcome, so a consumer parses one thing whether
 * the platform answered or not. It starts as an unavailable reading with
 * nothing in it: a field is filled in only once something was actually read,
 * so an answer this adapter never obtained cannot be left looking like one. */
function muejejeAdapterModuleReading(resolution, reason, factoryIndex) {
    return {
        resolution: resolution,
        unavailable_reason: reason,
        unavailable_member: muejejeReadingStageMember(reason),
        unavailable_argument: muejejeReadingStageArgument(reason),
        factory_index: factoryIndex,
        available_count: null,
        descriptor_present: false,
        model: null,
        device_type: null,
        root_present: false,
        nodes: [],
        nodes_truncated: false,
        depth_truncated: false,
        module_positions_truncated: false
    };
}

function muejejeAdapterModuleUnavailable(reason, factoryIndex) {
    return muejejeAdapterModuleReading(
        MUEJEJE_PLATFORM_UNAVAILABLE, reason, factoryIndex
    );
}

/* The index, checked rather than defaulted. An index outside these bounds
 * reached this adapter from our own code, and reading device 0 instead would
 * report an observation about a model nobody asked about. */
function muejejeAdapterFactoryIndex(factoryIndex) {
    return muejejeReadingArgument(
        factoryIndex, 0, MUEJEJE_PLATFORM_LIMITS.EXACT_INTEGER_MAX
    );
}

/* The one entry point. An unreadable platform is an observation about the
 * platform, not an exception for the caller. */
function muejejeAdapterModuleDescriptors(factoryIndex) {
    var index = muejejeAdapterFactoryIndex(factoryIndex);
    var platform = muejejeAdapterPlatform();
    if (platform === null) {
        return muejejeAdapterModuleUnavailable(MUEJEJE_PLATFORM_ABSENT, index);
    }
    try {
        return muejejeAdapterModuleRead(platform, index);
    } catch (platformError) {
        /* The thrown value is engine-internal and never reaches the result.
         * Only the two sentinels are a reading; anything else is a defect in
         * this artifact and is rethrown for the dispatcher (MJ-031). */
        return muejejeAdapterModuleUnavailable(
            muejejeReadingReason(platformError), index
        );
    }
}

/* An index past the end is an answer, not a failure: the factory said how many
 * models it offers, and it offers none there. Reporting that as an unreadable
 * platform would send a consumer looking for a fault that nothing had. */
function muejejeAdapterModuleRead(platform, index) {
    var factory = muejejeAdapterCall(
        muejejeAdapterCall(platform, "IPC.hardwareFactory"), "HardwareFactory.devices"
    );
    var count = muejejeReadingCount(
        muejejeAdapterCall(factory, "DeviceFactory.getAvailableDeviceCount")
    );
    var reading = muejejeAdapterModuleReading(
        MUEJEJE_PLATFORM_OBSERVED, null, index
    );
    reading.available_count = count;
    if (index >= count) {
        return reading;
    }
    return muejejeAdapterModuleTree(
        reading, muejejeAdapterCallWith(factory, "DeviceFactory.getAvailableDeviceAt", index)
    );
}

function muejejeAdapterModuleTree(reading, descriptor) {
    if (descriptor === null) {
        throw MUEJEJE_PLATFORM_UNUSABLE;
    }
    reading.descriptor_present = true;
    reading.model = muejejeReadingText(
        muejejeAdapterCall(descriptor, "DeviceDescriptor.getModel"),
        MUEJEJE_PLATFORM_LIMITS.MAX_MODEL_CHARS
    );
    reading.device_type = muejejeReadingExactInteger(
        muejejeAdapterCall(descriptor, "DeviceDescriptor.getType")
    );
    var root = muejejeAdapterCall(descriptor, "DeviceDescriptor.getRootModule");
    if (root === null) {
        return reading;
    }
    reading.root_present = true;
    return muejejeAdapterWalk(reading, root);
}

/* Breadth-first, over a queue this adapter owns, so nothing here recurses: a
 * descriptor that described itself is a bounded reading rather than a stack
 * overflow inside Packet Tracer's engine. */
function muejejeAdapterWalk(reading, root) {
    var walk = {
        pending: [{descriptor: root, parent: null, depth: 0, position: null}],
        positions: 0
    };
    var head = 0;
    while (head < walk.pending.length) {
        var item = walk.pending[head];
        head = head + 1;
        var node = muejejeAdapterModuleNode(item, reading.nodes.length);
        reading.nodes.push(node);
        muejejeAdapterQueueChildren(reading, walk, item, node);
    }
    return reading;
}

/* One node, every field read through the boundary and checked first: a partial
 * node would look like an answer about the platform. `module_index` is the
 * argument `getModuleAt` was called with and is not called a slot, nor is any
 * entry of `null_module_positions`: `getSlotCount()`/`getSlotTypeAt(i)` are a
 * second enumeration, and nothing observed says the two correspond (MJ-015). */
function muejejeAdapterModuleNode(item, index) {
    var slots = muejejeAdapterSlotTypes(item.descriptor);
    return {
        index: index,
        parent_index: item.parent,
        depth: item.depth,
        module_index: item.position,
        model: muejejeReadingText(
            muejejeAdapterCall(item.descriptor, "ModuleDescriptor.getModel"),
            MUEJEJE_PLATFORM_LIMITS.MAX_MODEL_CHARS
        ),
        module_type: muejejeReadingExactInteger(
            muejejeAdapterCall(item.descriptor, "ModuleDescriptor.getType")
        ),
        hot_swappable: muejejeReadingFlag(
            muejejeAdapterCall(item.descriptor, "ModuleDescriptor.isHotSwappable")
        ),
        slot_types: slots.types,
        slot_types_truncated: slots.truncated,
        module_count: muejejeReadingCount(
            muejejeAdapterCall(item.descriptor, "ModuleDescriptor.getModuleCount")
        ),
        null_module_positions: [],
        children_truncated: false
    };
}

/* The slot types this module offers, as the platform's own numbers and never
 * translated (MJ-014). A different enumeration from the modules below it:
 * `getSlotCount()` bounds this list, `getModuleCount()` that one, and nothing
 * here claims the i-th of one is the i-th of the other. */
function muejejeAdapterSlotTypes(descriptor) {
    var count = muejejeReadingCount(
        muejejeAdapterCall(descriptor, "ModuleDescriptor.getSlotCount")
    );
    var readable = Math.min(count, MUEJEJE_PLATFORM_LIMITS.MAX_SLOTS);
    var types = [];
    for (var index = 0; index < readable; index++) {
        types.push(muejejeReadingExactInteger(
            muejejeAdapterCallWith(descriptor, "ModuleDescriptor.getSlotTypeAt", index)
        ));
    }
    return {types: types, truncated: count > readable};
}

/* Children are queued, never walked here, and a bound refuses a node's whole
 * child set, never a prefix: half a module list read as a complete one is what
 * the marking exists to prevent. TWO BUDGETS, because a position is not a node:
 * positions are reserved from `MAX_MODULE_POSITIONS` before any is asked, so a
 * refused node reports no null it never saw; `MAX_MODULE_NODES` counts what the
 * walk keeps, judged once the positions answered — a null costs none, and a
 * module handed over into a set that does not fit is dropped with it. */
function muejejeAdapterQueueChildren(reading, walk, item, node) {
    if (node.module_count === 0) {
        return;
    }
    if (item.depth >= MUEJEJE_PLATFORM_LIMITS.MAX_MODULE_DEPTH) {
        node.children_truncated = true;
        reading.depth_truncated = true;
        return;
    }
    if (walk.positions + node.module_count > MUEJEJE_PLATFORM_LIMITS.MAX_MODULE_POSITIONS) {
        node.children_truncated = true;
        reading.module_positions_truncated = true;
        return;
    }
    walk.positions = walk.positions + node.module_count;
    var children = [];
    for (var position = 0; position < node.module_count; position++) {
        muejejeAdapterQueueChild(item, node, children, position);
    }
    if (walk.pending.length + children.length > MUEJEJE_PLATFORM_LIMITS.MAX_MODULE_NODES) {
        node.children_truncated = true;
        reading.nodes_truncated = true;
        return;
    }
    for (var queued = 0; queued < children.length; queued++) {
        walk.pending.push(children[queued]);
    }
}

/* One position, asked once, and the walk goes on past a null. On 9.0.1.0858 a
 * null inside the count is ordinary — 1054 of the factory's 1551 positions,
 * some before a later module in the same node — so it is recorded as that
 * position and nothing more: what it means physically nobody observed (MJ-015).
 * A throw, `undefined` or a primitive never reach here; the boundary refuses them. */
function muejejeAdapterQueueChild(item, node, children, position) {
    var child = muejejeAdapterCallWith(item.descriptor, "ModuleDescriptor.getModuleAt", position);
    if (child === null) {
        node.null_module_positions.push(position);
        return;
    }
    children.push({
        descriptor: child, parent: node.index, depth: item.depth + 1, position: position
    });
}
