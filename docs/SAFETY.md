# Medirover — Safety (current state + hardware requirements)

Status: the **software** safety architecture is IMPLEMENTED and UNIT-TESTED;
**no physical safety verification has been performed** — this build has no
hardware. Everything physical below is a requirement for M10, not a fact.

## 1. What the software does today (SIMULATION-VERIFIED)

- **Safety FSM** (`shared/safety/machine.py`): SAFE → READY only after
  `INIT_OK` (startup self-check). Motion commands are accepted only from
  READY. An anomaly during motion goes straight to FAULT.
- **E_STOP dominance**: E_STOP is a legal transition from **every** state to
  EMERGENCY_STOP; the only exit is E_STOP_RELEASED → RECOVERY →
  RECOVERY_OK → READY. The FSM makes it impossible to skip the recovery
  checks.
- **Node-side enforcement**: when the safety state is not READY the motion
  node refuses drive commands (`COMMAND_ACCEPT` is refused by the FSM), and
  on E_STOP the simulated motors are commanded to stop.
- **Backend visibility**: safety_state is part of every state update and the
  frontend chip; FAULT/EMERGENCY_STOP take visual precedence.
- Exhaustive transition tests: every legal transition is exercised and
  representative illegal transitions assert `FSMError`
  (`tests/test_safety_fsm.py`).

## 2. What this is NOT (be honest)

- The E-stop path is **software-only** against a simulated safety input.
  There is no evidence of behavior on a physical motor drive, encoder, or
  hardwired E-stop button. **Do not treat this system as safe to operate
  near people or property in any physical form.**
- `hardware.yaml` refuses to start without `MEDIROVER_HARDWARE_ACK=yes`
  precisely so this state cannot be silently assumed.

## 3. Hardware requirements (M10 checklist — NOT-STARTED)

Before any physical operation:

1. **Hardwired E-stop** that cuts motor power directly (bypassing the MCU,
   battery, and this software entirely); software E_STOP is secondary.
2. **Drive current limiting + hardware over-current/over-temperature cutoff**
   in the motor driver, independent of firmware.
3. **Physical containment**: the mechanism cannot reach people at any
   fault speed; verify with documented bench test.
4. **Battery disconnect switch**, accessible, rated.
5. **Sensor failure ⇒ safe state**: a missing/stale safety or motor
   feedback input must force WARNING/FAULT (fail-safe direction), verified
   by fault injection on the bench.
6. **Bench E-stop drill**: engage E-stop during motion; measure stop time;
   repeat 10×; record in `results/` (canonical, bounded report).
7. **Sign-off**: a named person records HARDWARE-VERIFIED per checklist item
   in `recovery/PROJECT_STATE.json`; until then the system's status label
   stays SIMULATION-VERIFIED.

## 4. Operational rules (applies from the moment hardware exists)

- Never disable the safety FSM or its events to make a test pass.
- Never run the hardware profile without the env acknowledgement.
- Fault history is retained (HISTORICAL class) and reviewed before re-enable
  after any FAULT/EMERGENCY_STOP.
