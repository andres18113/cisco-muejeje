# application/dto/

DTOs define the stable inputs and outputs for the classic application use cases.
Request DTOs adapt external planning, repair, and export input into domain
values. Response DTOs carry a plan or generated artifact together with its
validation state, errors, warnings, explanations, estimates, or export result.

DTOs do not perform Packet Tracer I/O and do not establish live execution
status. Enterprise contracts use their own typed domain and application models
rather than forcing their richer lifecycle evidence through the classic DTOs.
