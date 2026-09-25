# SERVER-PT-DHCP-AUTONOMOUS-02: episode 3

This is the immutable primary archive of the native DHCP policy experiment on
Packet Tracer 9.0.1.0858. `MANIFEST.sha256` hashes every file in `lead/`,
`store/`, `record/`, and this README. The three one-use lead scripts retain
their exact source bytes with `.txt` appended to their original `.py` names;
remove only that final `.txt` to recover each original filename. `store/` is
the byte-for-byte cumulative campaign snapshot after episode 3 closed and
includes earlier episode records named by the campaign index.

The executing commit was `76a60a8d259e1f2cee571a446664ef3cb1a2d6bc`
(tree `190f53c41ee0a930be08a3253633fc706eb72f23`). Episode 3 used
attempt `3abd3d33dfeb48e0bbd689c314418ed4`, instance token
`6f66d1d16a3d49fbbbfff96829dfcde4`, and the file channel. The
qualification record is
`q3-native-policy-2026-09-25T22-00-05Z-5ce98dfc.json` (SHA-256
`3222546e0497fae88139ad0cd6fbc20dff6223118cb1e494f0bba00e42020f01`).

The first launch record was refused as Packet Tracer's window title changed
between OS reads. A new read of the same PID and creation time under the
shared lifecycle claim allowed `04b`/`05b` to record the owned blank lab.
This refusal did not dispatch a native DHCP operation.

The repeated `setStartIp("192.0.2.100")` reproduced the prior coupled native
transition. `setMaxUsers(1)` then read back one physical `serverPool` with
`start=end=192.0.2.100`, network `192.0.2.0`, mask `255.255.255.0`, and
`max=1`. Separate `setDefaultRouter("192.0.2.1")` and
`setDnsServerIp("192.0.2.10")` calls changed only their intended fields.
Two `addExcludedAddress` calls then read back singleton exclusions for
`192.0.2.1` and `192.0.2.10`. Every before/after policy read reported one
physical pool, the disabled DHCP process, and complete exclusion count/list.
All six `M-NATIVE-*` measurements were **SUPPORTED_IN_SAMPLE** for this build
and disposable fixture. This establishes stored policy, not client serving,
reapplication, renewal, or dependent HTTP.

The run used 45 operations and proved fixture restoration. The retirement
record reports an actual exit of the owned PID. The save-prompt helper sent
no button because its fresh check found the document changed; the process
exited nonetheless. The final census found zero Packet Tracer processes,
pending mailbox files, or campaign claim. The ledger closed episode 3 at
45 operations and 258.04685 seconds. Cumulative use is 115 operations and
910.882859 seconds, leaving 8,885 ordinary operations and 12,889.117141
ordinary seconds outside the protected reserve.
