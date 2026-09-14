/*
 * Muejeje runtime — the `network.link_endpoints` operation.
 *
 * Read-only. It answers one question — *which two ports does the link at this
 * position join* — by asking the platform through the declared adapter. It
 * names no platform symbol itself: operation -> adapter -> boundary ->
 * platform, and never back (MJ-019).
 *
 * ONE OBSERVATION. The link is selected once, and its object UUID and both of
 * its ends are read off that one hand-over, so a consumer never joins the ends
 * of one link with the identity of another (MJ-031). Each end carries the object
 * UUIDs Packet Tracer reports for its port and for the device that owns it,
 * which is how it is correlated with the device and port readings.
 *
 * THE ARGUMENT IS A LINK POSITION. `workspace_link_index` is where
 * `network.link_inventory` handed a link over, in its own enumeration: it is
 * neither a device position nor stable across readings, and a device's
 * `workspace_index` sent here is refused rather than read as a link (MJ-029).
 *
 * It reaches no verdict: `resolution` says whether a reading was obtained, and
 * Python decides what it establishes (MJ-011).
 */

/* `workspace_link_index` is REQUIRED: every position holds a different link, so
 * no default could be honest, and a request naming none reads nothing. It is
 * bounded by the exact-integer limit, the domain the inventory publishes it in,
 * and by no ceiling of its own (MJ-029). */
var MUEJEJE_NETWORK_LINK_ENDPOINTS_ARGS = {
    workspace_link_index: {
        kind: "integer",
        required: true,
        min: 0,
        max: MUEJEJE_PLATFORM_LIMITS.EXACT_INTEGER_MAX
    }
};

function muejejeNetworkLinkEndpoints(args, context) {
    return muejejeAdapterLinkEndpoints(
        muejejeV6RequiredArgument(args, "workspace_link_index")
    );
}
