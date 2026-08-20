# Address reconciliation

Read this reference only when existing or deployed IPv4 bindings must coexist with new infrastructure demand.

Provide `AddressReconciler` with explicit owner identities, demand identities, address scope, and existing bindings. Do not match records by display-name similarity or rewrite an owner to resolve a conflict.

Interpret the result conservatively:

- preserved bindings remain evidence of continuity;
- conflicts and invalid demand are blocking;
- insufficient space is not solved by dropping a demand;
- a proposed renumber must identify the affected owner, previous assignment, replacement, and reason;
- a usable proposed plan that requires renumbering still needs separate approval before mutation.

Reconciliation produces desired state only. Read current source and tests for exact matching and status semantics.
