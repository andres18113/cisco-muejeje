# domain/services/

Domain services implement deterministic transformations over domain values. The
classic path includes topology orchestration, IP planning, validation
coordination, repair suggestions, estimation, and explanation. Supporting
services summarize traces and ports, compare an intended plan with a supplied
observation, audit supplied security state, and decode or validate canvas data.

Services do not contact Packet Tracer, write files, or select a live transport.
They consume typed inputs and return typed plans, validation results, summaries,
or analysis suitable for application use cases.
