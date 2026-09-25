# SERVER-PT-DHCP-AUTONOMOUS-02: episode 1

This is the immutable primary archive of the first delegated native-pool
experiment on Packet Tracer 9.0.1.0858. `MANIFEST.sha256` names and hashes
every archived file. `lead/` retains the episode plan, one refused opening,
the exclusive launch script and its observations, exact qualification argv,
stdout/stderr/exit code, and the observed retirement summary. `store/` is a
byte-for-byte snapshot of the commissioning campaign store after closing the
episode. `record/` contains the original qualification record.

The executed source was `c76ab02bc177ba0e0c60f481d009432fdb886485`
(tree `79d7025419191bf0ecbe7f1c376f81aa2af605d2`). Episode 1 used
attempt `e61273ccccbf4492a33d5e02798facfb`, instance token
`6ff7bc8aed7a4187b8e98187b74473e8`, and the file channel. The
qualification record is `q3-native-probe-2026-09-25T20-36-44Z-84514155.json`
(SHA-256 `1dcf4d95f2c8d20dc22f67950b86c0bb4c0b4dac3e828d88ae4a2d31494fa9c1`).

`setStartIp("192.0.2.100")` returned with no call error. The same physical
`serverPool` then read back `start=192.0.2.100`, `end=192.0.2.255`, and
`max=156`, from `start=192.0.2.0`, `end=192.0.3.255`, and `max=512`.
The DHCP process remained disabled and the inventory held exactly one pool.
The stage stopped as **CONTRADICTED** because two unrequested pool fields
changed. This is a measured, build-scoped coupled setter result, not proof
that the requested one-user policy is configured or that a client is served.

The stage used 34 operations; fixture restoration was proven. The owned
process exited after the revalidated save prompt's `No` button was invoked.
The subsequent process census found no Packet Tracer process, pending mailbox
file, or campaign lock. The ledger closed the episode at 34 operations and
347.474369 seconds. The CLI retirement stdout was seen by the lead but was
not separately captured as a source file; the indexed `process-exit.json` is
the primary retirement record. No DHCP client or HTTP service was qualified.
