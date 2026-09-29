# Medirover — Safety Audit (2026-09-29, commit b0dd83f)

Audit of the 13 standing safety constraints against the **actual code** at
the snapshot commit. Verdicts: SATISFIED (code enforces it), SATISFIED-BY-
ABSENCE (the regulated capability does not exist), GAP (documented, tracked).

| # | Constraint | Verdict | Evidence |
|---|---|---|---|
| 1 | No human-connected pacing | SATISFIED-BY-ABSENCE | No pacing/defibrillation/cardiac code exists anywhere (grep: zero matches) |
| 2 | No clinical diagnosis or treatment claims | SATISFIED-BY-ABSENCE | No clinical/diagnosis/treatment language in code or docs; project is a robotics/monitoring system |
| 3 | No real biomedical waste | SATISFIED-BY-ABSENCE | No biomedical functions exist |
| 4 | No automatic physical motion startup | SATISFIED (with note) | Nodes boot to `SAFE`, reach `READY` only after self-check; motion commands require `COMMAND_ACCEPT` from READY. The scripted demo drive auto-starts **only in simulation profiles** (`drive_every_s>0`); `config/hardware.yaml` sets `drive_every_s: 0.0`, and the hardware profile additionally requires `MEDIROVER_HARDWARE_ACK=yes` to even boot the backend. Note: once real drivers exist (M8/M10), the drive cycle must remain disabled by default on hardware — tracked in `docs/SAFETY.md` M10 checklist. |
| 5 | E-stop must override all software commands | SATISFIED (software path) | `_estop_watchdog` polls `ISafetyInput.e_stop_engaged()` every `ESTOP_SCAN_S`; on engage it sends `E_STOP` (legal from every FSM state) and commands `motors.stop()` unconditionally, mid-drive included. Physical override path does not exist yet (see #7). |
| 6 | Zero-velocity stopping cannot be blocked by software | SATISFIED (software path) | `IMotorController.stop()` is a direct controller call with no FSM/interlock gate in front of it; the node `finally` block and E-stop watchdog both call it unconditionally. Enforced as an interface requirement for the M8 real drivers. |
| 7 | Physical E-stop power cut remains a hardware requirement until verified | GAP (known, tracked) | No physical E-stop exists; `docs/SAFETY.md` §3 makes hardwired power cut (bypassing MCU/software) item 1 of the M10 checklist. Nothing in the repo claims otherwise. |
| 8 | Simulated physiology clearly labelled as simulated | SATISFIED | `source_kind=SIMULATED` on every node state, health endpoint, and dashboard chip; simulation profile name; `hardware.yaml` timing values placeholder-labeled. (No physiology simulation exists — see #9.) |
| 9 | Glucose simulation remains simulation-only unless a real verified interface exists | SATISFIED-BY-ABSENCE | No glucose code exists at all |
| 10 | Arm/motor commands pass explicit safety gates | SATISFIED | `_drive_loop` refuses to command unless `safety.state == READY` and `safety.can(COMMAND_ACCEPT)`; the FSM makes illegal motion transitions raise. No arm/servo commands exist (nothing to gate). |
| 11 | Unknown hardware must never be guessed | SATISFIED | No real-hardware assumptions in code; all hardware access is behind `firmware/hardware/interfaces.py`; physical constants that are assumed are explicitly commented "placeholder assumption (UNKNOWN real hardware)"; hardware profile refuses to start without explicit env acknowledgement. |
| 12 | Hardware-dependent capabilities clearly marked unverified until physically tested | SATISFIED | `docs/STATUS_MATRIX.md`: every hardware row is NOT-STARTED/UNVERIFIED; `docs/SAFETY.md` states plainly no physical verification exists; UI shows SIMULATED; `hardware_status: NO_HARDWARE_ATTACHED` in the canonical checkpoint. |
| 13 | Simulation never silently mistaken for real hardware operation | SATISFIED | `source_kind` is a protocol field (reported by node state, displayed by UI), not a log comment; REST health returns it; the clean-checkout report and test history carry the mode. |

## Audit observations (actionable)

1. **M8 real-driver skeletons must hard-wire rules #5/#6 into the driver
   interface**: `stop()` must bypass all interlocks, and an E-stop input
   latch must not be clearable by software alone (latching release requires
   the physical input to de-assert). These become fault-injection unit tests.
2. **Drive cycle default**: when real drivers land, the hardware profile's
   `drive_every_s: 0.0` (no auto-motion) must be preserved and asserted by a
   config test (added in M8).
3. **Sensor node in e2e**: the sensor node is unit-tested but not part of
   the vertical-slice e2e; not a safety violation, tracked as test-coverage
   work.
4. No violations found. No rule required a code change at this snapshot
   beyond the M8 interface hardening above.
