# Hierarchy decisions

Read this reference only when hierarchy or aggregation changes the logical plan.

- Preserve identities supplied by the intent; do not rename or merge scopes for visual convenience.
- Treat site, building, floor, and zone as distinct placement and ownership boundaries when the requirements distinguish them.
- A zone is not automatically a VLAN or security boundary. Create segmentation only from explicit network intent.
- Keep endpoint populations grouped while designing. Downstream planners can consume counts without inventing individual devices.
- Add a default or inferred grouping only when the current source contract supports it, and surface the assumption in the result.

Confirm exact hierarchy normalization and validation in the current enterprise planning source and tests rather than copying model fields here.
