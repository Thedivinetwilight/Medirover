# Medirover — Legacy Knowledge Map

The old Medirover codebase (legacy ZIP / old repositories) is **not available
in this build's workspace** and was never inspected. This rebuild is a clean
foundation; nothing was carried forward. Per the directive, legacy knowledge
is classified, and unclassified claims are marked UNKNOWN.

| Item | Classification | Notes |
|---|---|---|
| Legacy ZIP / prior repo contents | UNKNOWN (UNAVAILABLE) | File was never delivered to the workspace; no claim is made about its code. |
| "Medirover genuinely works" as a goal, not file count | VERIFIED (operator directive) | Standing instruction from the rebuild directive. |
| Past storage incident: ~1.1 GB / 13,000+ files of unbounded artifacts | VERIFIED (operator report) | The bounded-artifact + retention design (ARTIFACTS_AND_RETENTION.md) exists to prevent recurrence. |
| Legacy bug list / known issues | UNKNOWN | Never inspected; no bug was assumed or fixed by reference. |
| Legacy hardware model (which boards/sensors/motors were used) | UNKNOWN | Hardware interfaces in `firmware/hardware/` are designed from the requirement (motion + sensor nodes), not from legacy code. |
| Legacy protocol format | UNKNOWN | The new protocol is defined fresh in PROTOCOL.md; compatibility with any legacy wire format is NOT claimed. |
| Legacy dashboard features | UNKNOWN | The new frontend implements the vertical-slice requirements only. |
| Milestone definitions M0–M12 | INFERRED (from directive) | As interpreted in MILESTONES.md; the directive named milestones, the scope per milestone is our operationalization. |

Rule applied: anything about the legacy system that cannot be evidenced in
this workspace is marked UNKNOWN or INFERRED and is never presented as fact.
