/*
 * Muejeje runtime — the module-type support reading. READ-ONLY.
 *
 * A declared adapter (MJ-006, MJ-019, MJ-031). It answers one question about
 * one device model: does its factory descriptor say it accepts a given module
 * type? `DeviceDescriptor.isModuleTypeSupported(ModuleType)` is the API that
 * knows, and it is a descriptor method — not a method on a runtime device, and
 * not a statement about installed hardware (MJ-014).
 *
 * It names no platform object. Every call goes through `muejejeAdapterCall` in
 * `platform_adapter.js`, which admits only the read-only getters on that list.
 *
 * THE TYPE VALUE COMES FROM THE CALLER, AND IS NEVER TRANSLATED. This artifact
 * carries no table of Cisco's module types, so it has no opinion about which
 * numbers exist: it passes the number it was given, reports what the platform
 * answered for it, and echoes the value back so the answer stays attributable.
 * Where a consumer gets a type value from is the platform too —
 * `platform.device_descriptors` reports the types a model lists, and
 * `platform.module_descriptors` reports the type of each module in its chassis
 * (MJ-014).
 *
 * A separate file from the chassis walk on purpose: one adapter, one subject.
 * "What does this model accept" and "what is this model described as carrying"
 * are two readings, and the walk is already the longer of the two (MJ-018).
 */

/* One result shape for every outcome, so a consumer parses one thing whether
 * the platform answered or not. A field is filled in only once something was
 * actually read. */
function muejejeAdapterSupportReading(resolution, reason, deviceIndex, type) {
    return {
        resolution: resolution,
        unavailable_reason: reason,
        device_index: deviceIndex,
        module_type: type,
        available_count: null,
        descriptor_present: false,
        model: null,
        device_type: null,
        module_type_supported: null
    };
}

function muejejeAdapterSupportUnavailable(reason, deviceIndex, type) {
    return muejejeAdapterSupportReading(
        MUEJEJE_PLATFORM_UNAVAILABLE, reason, deviceIndex, type
    );
}

/* The one entry point. An unreadable platform is an observation about the
 * platform, not an exception for the caller; an argument outside this
 * adapter's own bounds is a defect in this artifact, and fails as one. */
function muejejeAdapterModuleTypeSupport(deviceIndex, moduleType) {
    var index = muejejeReadingArgument(
        deviceIndex, 0, MUEJEJE_PLATFORM_LIMITS.MAX_FACTORY_INDEX
    );
    /* The consuming half of relay closure: the domain a type is admitted in is
     * the domain the readings publish, named from the same declaration. A
     * ceiling of its own here would refuse values this artifact hands out. */
    var type = muejejeReadingArgument(
        moduleType,
        MUEJEJE_PLATFORM_LIMITS.MODULE_TYPE_MIN,
        MUEJEJE_PLATFORM_LIMITS.MODULE_TYPE_MAX
    );
    var platform = muejejeAdapterPlatform();
    if (platform === null) {
        return muejejeAdapterSupportUnavailable(
            MUEJEJE_PLATFORM_ABSENT, index, type
        );
    }
    try {
        return muejejeAdapterSupportRead(platform, index, type);
    } catch (platformError) {
        return muejejeAdapterSupportUnavailable(
            muejejeReadingReason(platformError), index, type
        );
    }
}

/* An index past the end is an answer, not a failure: the factory said how many
 * models it offers, and it offers none there. */
function muejejeAdapterSupportRead(platform, index, type) {
    var factory = muejejeAdapterCall(
        muejejeAdapterCall(platform, "IPC.hardwareFactory"), "HardwareFactory.devices"
    );
    var reading = muejejeAdapterSupportReading(
        MUEJEJE_PLATFORM_OBSERVED, null, index, type
    );
    reading.available_count = muejejeReadingCount(
        muejejeAdapterCall(factory, "DeviceFactory.getAvailableDeviceCount")
    );
    if (index >= reading.available_count) {
        return reading;
    }
    return muejejeAdapterSupportAsk(
        reading, muejejeAdapterCallWith(factory, "DeviceFactory.getAvailableDeviceAt", index),
        type
    );
}

/* The identity is read back before the answer is reported, so a consumer can
 * see *which* model answered rather than trusting the index it sent. A support
 * flag with no model beside it is a fact nobody can attribute (MJ-010). */
function muejejeAdapterSupportAsk(reading, descriptor, type) {
    if (!descriptor) {
        throw MUEJEJE_PLATFORM_UNUSABLE;
    }
    reading.descriptor_present = true;
    reading.model = muejejeReadingText(
        muejejeAdapterCall(descriptor, "DeviceDescriptor.getModel"),
        MUEJEJE_PLATFORM_LIMITS.MAX_MODEL_CHARS
    );
    reading.device_type = muejejeReadingWholeNumber(
        muejejeAdapterCall(descriptor, "DeviceDescriptor.getType")
    );
    reading.module_type_supported = muejejeReadingFlag(
        muejejeAdapterCallWith(descriptor, "DeviceDescriptor.isModuleTypeSupported", type)
    );
    return reading;
}
