# SP-2 remote relay diagnostic, episode 3

Executed commit `9f93721f128f7e9ced2a151ba0a83870efe8872a`, tree `62582242a459ac18ea30d93b30aaf5c2a5f8057d`; build `9.0.1.0858`, file channel, stage `SP2-REMOTE-RELAY` profile v1.

Attempt `37f799295fbf7c1ecee0da9f53bb5055`; campaign `SERVER-PT-SP2-GENERALIZED-DHCP-RELAY-01`. Qualification outcome `stopped`; remote pool assessment `inconclusive`; terminal assessment `inconclusive`. Final process/mailbox cleanup `process_absent_exit_unattributed`: the first maintained retirement posted WM_CLOSE and was refused at the owned Exit save prompt (`window_set_changed`); the recovery retirement then found the owned PID absent, so no owned process-exit record exists and the exit is not attributed. The final census found no Packet Tracer process, mailbox file or campaign lock.

Primary failure `sp2_remote_helper_readback_unverified`: the BR1 helper action was applied, but its fresh `show ip interface` readback was not a complete attributed capture, so no client mode, pool or lease effect followed.

This is a private one-client remote relay diagnostic on an owned six-device fixture, not generalized DHCP, 36-client capacity, public relay or named-pool support, or routed service acceptance. Packet `giaddr` bytes, table end, exclusive serving, renewal and `dhcpRun` causality are not observed. The indexed campaign store and qualification record retain the full causes and reads.
