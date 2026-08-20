# Redundancy decisions

Read this reference only when the request includes availability, failover, path diversity, or tolerated-failure requirements.

Describe redundancy as an outcome:

- the failure to tolerate;
- the service or path that must remain available;
- the expected recovery behavior;
- the independent failure boundary;
- whether the outcome can be tested with the available evidence.

Separate link multiplicity, path diversity, device redundancy, and failure-domain independence. Duplicated links or devices do not by themselves prove a surviving independent path.

Leave protocol-specific mechanisms to the Layer 2, first-hop redundancy, or IGP Skill selected for that reasoning step.
