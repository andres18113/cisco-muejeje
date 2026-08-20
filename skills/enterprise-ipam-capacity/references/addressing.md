# Initial addressing

Read this reference only for new enterprise IPv4 allocation.

Supply the complete logical plan and declared address space to the current IPAM service. Let source code own subnet sizing, ordering, gateway conventions, site-block selection, and transit allocation; do not recreate those deterministic rules manually.

Review the result for:

- containment within the approved address space;
- non-overlapping site, segment, and transit allocations;
- sufficient usable capacity after the declared growth and reservations;
- stable output for equivalent input;
- a clear relationship between each allocation and its logical demand.

If a caller requests a fixed block, validate it through the current planner. Do not silently move or enlarge it to make the plan pass.
