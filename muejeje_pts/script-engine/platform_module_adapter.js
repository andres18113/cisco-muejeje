/*
 * Muejeje runtime — the chassis-module descriptor reading. READ-ONLY.
 *
 * A declared adapter (MJ-006, MJ-019, MJ-031): it reads what hardware one
 * device *model* is described as carrying — the root module of its factory
 * descriptor, and the module tree under it — and reports what it read without
 * deciding what any of it establishes (MJ-011).
 *
 * It names no platform object. Every call goes through `muejejeAdapterCall` in
 * `platform_adapter.js`, which admits only the read-only getters on that list.
 *
 * A DESCRIPTOR IS NOT INSTALLED HARDWARE. `DeviceDescriptor.getRootModule()`
 * describes what a model can accept; it instantiates nothing, powers nothing,
 * and says nothing about a device on a workspace. The runtime `Module` surface
 * — reached from the network, not from the hardware factory — is a different
 * interface with different getters, and the two are never mixed (MJ-014).
 *
 * A MODEL IS ADDRESSED BY ITS INDEX IN THE FACTORY ENUMERATION, never by a
 * DeviceType and never by a name this artifact knows. Asking by type would
 * mean carrying a numeric Cisco enum table as the authority for which types
 * exist; asking by name would mean carrying a catalogue of somebody's models
 * (MJ-002, MJ-014). The identity actually read is reported back, so a consumer
 * can tell which model answered rather than trusting the index.
 *
 * THE WALK IS BOUNDED AND SAYS SO. A chassis tree has no bound this repository
 * has measured, so the ceilings are Muejeje's own (MJ-029) and every subtree
 * they omit is marked — a truncated branch stays visibly absent and can never
 * be read as an observed absence.
 */

/* One result shape for every outcome, so a consumer parses one thing whether
 * the platform answered or not. It starts as an unavailable reading with
 * nothing in it: a field is filled in only once something was actually read,
 * so an answer this adapter never obtained cannot be left looking like one. */
function muejejeAdapterModuleReading(resolution, reason, factoryIndex) {
    return {
        resolution: resolution,
        unavailable_reason: reason,
        factory_index: factoryIndex,
        available_count: null,
        descriptor_present: false,
        model: null,
        device_type: null,
        root_present: false,
        nodes: [],
        nodes_truncated: false,
        depth_truncated: false
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
    if (!descriptor) {
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
    if (!root) {
        return reading;
    }
    reading.root_present = true;
    return muejejeAdapterWalk(reading, root);
}

/* Breadth-first, over a queue this adapter owns, so the walk's cost is a
 * property of the runtime rather than of the tree it is handed. Nothing here
 * recurses: a descriptor that described itself would otherwise be a stack
 * overflow inside Packet Tracer's engine rather than a bounded reading. */
function muejejeAdapterWalk(reading, root) {
    var pending = [{descriptor: root, parent: null, depth: 0, position: null}];
    var head = 0;
    while (head < pending.length) {
        var item = pending[head];
        head = head + 1;
        var node = muejejeAdapterModuleNode(item, reading.nodes.length);
        reading.nodes.push(node);
        muejejeAdapterQueueChildren(reading, item, node, pending);
    }
    return reading;
}

/* One node, every field read through the boundary and checked before it is
 * reported. A partial node is deliberately not an option: reporting three
 * fields of a module and dropping the fourth would look like an answer about
 * the platform rather than about our inability to read it.
 *
 * `module_index` is the index this module was read at — the argument
 * `getModuleAt` was called with — and nothing more. It is deliberately not
 * called a slot: `getSlotCount()`/`getSlotTypeAt(i)` are a second enumeration
 * on the same descriptor, and nothing this repository has observed says the
 * two correspond. Publishing it as a slot position would be a claim about
 * Packet Tracer's model that no reading here supports (MJ-015). */
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
        children_truncated: false
    };
}

/* The slot types this module offers, as the platform's own numbers. Nothing
 * here translates them; naming a slot type is a consumer's job, against Cisco's
 * documentation (MJ-014).
 *
 * This is a different enumeration from the modules below it, and the reading
 * keeps them apart: `getSlotCount()` bounds this list, `getModuleCount()`
 * bounds that one, and nothing here claims the i-th of one is the i-th of the
 * other. */
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

/* Children are queued, never walked here, and a bound refuses the whole set of
 * a node's children rather than a prefix of it: half a module list read as a
 * complete one is the failure mode this marking exists to prevent. */
function muejejeAdapterQueueChildren(reading, item, node, pending) {
    if (node.module_count === 0) {
        return;
    }
    if (item.depth >= MUEJEJE_PLATFORM_LIMITS.MAX_MODULE_DEPTH) {
        node.children_truncated = true;
        reading.depth_truncated = true;
        return;
    }
    if (
        pending.length + node.module_count
        > MUEJEJE_PLATFORM_LIMITS.MAX_MODULE_NODES
    ) {
        node.children_truncated = true;
        reading.nodes_truncated = true;
        return;
    }
    for (var position = 0; position < node.module_count; position++) {
        muejejeAdapterQueueChild(item, node, pending, position);
    }
}

/* A missing module inside the count the platform itself reported is an answer
 * that cannot be attributed, exactly as a missing descriptor inside the device
 * count is. It is deliberately *not* read as "this position is empty": that
 * would be a semantic for `null` that no target reading supports, and inventing
 * one here would publish a fact about Packet Tracer's model that nobody
 * observed. If a target run shows a null is ordinary there, this becomes a
 * reported position with that evidence behind it — not before (MJ-015). */
function muejejeAdapterQueueChild(item, node, pending, position) {
    var child = muejejeAdapterCallWith(item.descriptor, "ModuleDescriptor.getModuleAt", position);
    if (!child) {
        throw MUEJEJE_PLATFORM_UNUSABLE;
    }
    pending.push({
        descriptor: child,
        parent: node.index,
        depth: item.depth + 1,
        position: position
    });
}
