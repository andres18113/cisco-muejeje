# domain/models/

This package defines the Pydantic contracts for the classic topology path. They
represent requests, topology plans, devices, links, modules, addressing,
routing, validation checks, and typed configuration such as VLANs, ACLs, NAT,
hardening, switch security, and interface tuning.

`TopologyPlan` is the plan exchanged by classic planning, validation,
generation, export, and comparison paths. Its fields express intended state and
validation results; they are not a read-back of a running Packet Tracer
workspace.

Validation is implemented in `domain/rules/`, not in these models. Callers use
the typed values and validation result to decide whether rendering or execution
may proceed.
