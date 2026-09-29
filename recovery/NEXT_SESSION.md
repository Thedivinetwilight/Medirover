# Medirover — Next Session Brief (written 2026-09-29, after M8)

**Start here.** Read this file, then `recovery/PROJECT_STATE.json`, then the
commit this brief points at. Do not redo M8; do not re-audit what the safety
audit already covered.

## Where the project stands

- **M8 COMPLETE** (this session). Real driver skeletons with safety
  interlocks live in `firmware/hardware/real/`:
  - `ports.py` — `Board` (channel-based physical I/O port) + `MemoryBoard`
    (deterministic test double). **This is the M9/M10 boundary.**
  - `estop.py` — `EstopLatch`: engage latches; `hardware_reset()` only
    clears when the physical input is observed de-asserted. Software can
    never clear it.
  - `motor_driver.py` — `DualMotorDriver`: interlock order
    E-stop latch → fault latch → enable gate. `stop()` bypasses all
    interlocks and never raises. `clear_fault()` cannot lift an E-stop.
  - `encoders.py` — velocity / zero-velocity verification / stall.
  - `battery.py` — OK/LOW/CRITICAL/**UNKNOWN** (ADC None → UNKNOWN, never
    a guessed value).
  - `hardware.py` — `RealHardware(IHardware)` facade + `acknowledge_estop_reset()`.
- **source_kind is end-to-end**: node reports it on identify
  (`IHardware.source_kind` → `NodeConfig.source_kind` →
  `IdentifyPayload.source_kind`), backend stores it in the runtime dict +
  `NodeRuntimeState.source_kind` (DB), default SIMULATED for legacy nodes.
  Config: hardware profile locks `drive_every_s: 0.0`
  (`test_hardware_profile_locks_automatic_drive_off`).
- Totals at M8 close: **206 Python tests + 4 frontend tests green;
  ruff + mypy (95 files) clean; live boot check green** (sim backend +
  demo node → ONLINE/READY, `source_kind=SIMULATED` in `/api/v1/nodes`).

## Next task: M9 — real MCU firmware port

Acceptance (docs/MILESTONES.md): boot → identify (**source_kind=HARDWARE**)
→ heartbeat on a real node, integration bench.

Work order suggested by the existing structure:
1. Implement a concrete `Board` for the target MCU (keep it thin: only the
   8 port operations). Until real wiring exists, every M9 test must still
   run against `MemoryBoard` — the skeleton interlock tests already pin the
   safety behavior.
2. Port the Python reference nodes (`firmware/motion_node`,
   `firmware/sensor_node`) to the MCU runtime. They already depend only on
   `IHardware` + `ICommunication`, so the port is: MCU transport +
   MCU `Board` + scheduler.
3. **Keep the M10 boundary clean**: the MCU port is not hardware-verified
   until the M10 checklist (docs/SAFETY.md) is physically executed and
   signed off. Do not claim HARDWARE-VERIFIED from a bench photo.

## Standing rules (unchanged)

- GitHub is the canonical source of truth: commit + push before calling
  work done. Branch: `arena/01a0eafd-medirover`. No force-push.
- 13 safety constraints (recovery/SAFETY_AUDIT.md, docs/SAFETY.md) —
  especially: E-stop overrides all software; zero-velocity stop cannot be
  blocked; unknown hardware is never guessed; simulation never silently
  mistaken for real hardware (source_kind is the mechanism).
- Test discipline: implement → targeted → full → diff → commit. Never
  weaken or delete tests. Current total to beat: 206 py + 4 js.
- Honesty labels: STUB/PARTIAL/…/FIELD-VERIFIED; UNKNOWN stays UNKNOWN.

## Quick commands

```bash
make check            # ruff + mypy + pytest
make test-frontend    # node --test frontend/tests/**/*.test.mjs
make demo             # sim backend + demo node
python tools/project_state.py show   # canonical checkpoint
```

## Things that bit this session (so you don't repeat them)

- Multi-file python heredoc patches with asserts abort mid-batch: verify
  every target file with grep after patching.
- `pytest -q | tail -2` can swallow the summary line; use `tail -3` or
  grep `passed`.
- Frontend tests live at `frontend/tests/**/*.test.mjs` (not `frontend/*.test.js`).
- Backend env var is `MEDIROVER_ENVIRONMENT`; API routes are `/api/v1/...`.
- Leftover demo_node/uvicorn processes from boot checks must be killed
  before the next run (they hold node identity + ports).
