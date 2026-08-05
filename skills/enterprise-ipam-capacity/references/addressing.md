# Addressing reference

Allocate site-summary blocks first, then segment prefixes with deterministic VLSM. Reserve infrastructure addresses for management, SVI, physical FHRP members, VIPs, transit links and loopbacks before endpoint hosts.

Check overlap, host count, growth reserve, summarization and deterministic ordering. The allocation result is an input to E4/E5, not a runtime observation.
