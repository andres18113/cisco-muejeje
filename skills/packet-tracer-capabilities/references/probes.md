# Probe protocol

Resolve the requirement, choose a registered typed probe, allocate a fresh ProbeSession, mutate only session-owned resources, observe through an independent path, bound the wait, clean up and verify inventory.

Probe definitions must be versioned and safe. Do not expose arbitrary command, JavaScript or target selection as a discovery interface.
