# SERVER-PT-DHCP-AUTONOMOUS-02: episode 5

This is the immutable primary archive of the guarded native DHCP serving
experiment on Packet Tracer 9.0.1.0858. `MANIFEST.sha256` hashes every file
in `lead/`, `store/`, `record/`, and this README. The three one-use lead
scripts retain their exact bytes with `.txt` appended to their original
`.py` names. `store/` is the cumulative campaign snapshot after episode 5
closed, including earlier records named by its index.

The executing commit was `04f5337eef67f0c850e057537ce80757e3aa73b1`
(tree `b0a0d2e0e34b4efd7892ee52aff6d033bfc16ecc`). Episode 5 used
attempt `66645cff81524e8f93d05295ddcd075f`, instance token
`6d045ac7212f481c91ccd97a6dc621b5`, and the file channel. The original
record is `q3-native-serve-2026-09-26T00-30-30Z-f961bd3d.json`
(SHA-256 `83e01280787c46b422c1339c2d6b7e8bce58a44aee6ac67804b3bf1edb775149`).

The owned blank instance was recorded on the first launch attempt. The
stage reestablished the exact one-user physical `serverPool` policy and the
E5 reapplication stability result, then performed a guarded native DHCP
enable and a guarded `configurePcIp` DHCP-mode activation on PC1. No
explicit `dhcpRun`, reset, ping, DNS query or HTTP request was dispatched.

Two consecutive samples, with client reads beginning at operation offsets
60.266 and 71.406 seconds, each observed PC1 in DHCP mode with address
`192.0.2.100`, mask `255.255.255.0`, stable MAC `0004.9AB0.A2B2`, and an
exact IP/MAC/`FastEthernet0` row in physical `serverPool` (capacity 1).
The separately named logical `MCP_E6Q_DHCP` pool was observed absent in
both samples. Each complete policy read still showed the requested range,
gateway `192.0.2.1`, DNS `192.0.2.10` and both exclusions. PC2 remained
DHCP-off and `0.0.0.0/0.0.0.0`. The enabled terminal inventory was complete.
`M-NATIVE-SERVE` is **SUPPORTED_IN_SAMPLE** for usable PC1 state and
effective physical-pool attribution on this build. This is passive
autonomous state evidence; it does not establish explicit `dhcpRun`
causality, table-end semantics, restart persistence, a second lease, or
dependent HTTP.

The run used 63 operations and proved fixture restoration. The maintained
retirement answered the exact owned save prompt `No`, observed the PID
exit, and the final census found zero Packet Tracer processes, pending
mailbox files or campaign claim. Episode 5 closed at 63 operations and
217.331687 seconds. Cumulative use is 226 operations and 1349.41694
seconds, leaving 8,774 ordinary operations and 12,450.58306 ordinary
seconds outside the protected reserve.
