# STP Resilience

Read this reference only when the task requires STP-family root selection, role/state interpretation, edge protection, or recovery evidence.

Derive root and edge intent from the approved topology and policy. Treat current root identity, bridge identity, port role/state, forwarding, convergence, and restoration as separate evidence questions. An edge designation is valid only where the topology semantics support it.

Before a failure exercise, require a fresh working baseline and an intended alternate path. Observe the changed forwarding state, restore the condition, and verify restoration separately. Determine the concrete STP mode, current public exposure, and observable fields from current source/tests and runtime capability evidence.
