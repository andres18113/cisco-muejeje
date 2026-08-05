# Runtime quirks

Keep version/model/scenario anomalies in RuntimeQuirkRegistry rather than universal Skill rules. A quirk can mark a capability PARTIAL, UNKNOWN or UNOBSERVABLE without asserting that all Packet Tracer versions behave identically.

Always match the active runtime fingerprint before applying a quirk.
