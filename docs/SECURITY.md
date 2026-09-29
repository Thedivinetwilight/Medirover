# Medirover — Security Review (current state)

Status: PRELIMINARY security review as of the M5–M7 rebuild (2026-09-29).
This is an honest gap list, not a claim of completeness. Closure is
milestone M12.

## What is in place

| Area | Control | Where |
|---|---|---|
| Input validation | Strict JSON envelopes; pydantic models with `extra="forbid"`; unknown fields → INVALID, never silently dropped | `shared/schemas/*`, `shared/protocols/validator.py` |
| Frame size | Max frame bytes (default 16 384) enforced before parsing; overflow counts as malformed | `backend/services/node_manager.py` |
| Abuse circuit breaker | 3 consecutive malformed frames → close 1008; 5 invalid client frames on the UI socket → close 1008 | `node_manager.py`, `api/ws_state.py` |
| Identity discipline | A node must identify before any state-changing frame is processed; invalid identify → reject, no state written | `node_manager.py` |
| Replay protection | Unique `(node_id, message_id, sensor_id)` constraint makes re-insertion idempotent; sequence check flags DUPLICATE/OUT_OF_ORDER | `telemetry_ingest.py`, `sequence.py` |
| Secrets | No credentials in the repo; `.env*` and `secrets/` gitignored; hardware profile requires an explicit `MEDIROVER_HARDWARE_ACK=yes` env to prevent accidental hardware mode | `.gitignore`, `config/hardware.yaml` |
| Error disclosure | Error envelope returns stable codes + categories, never stack traces or DB internals | `backend/api/errors.py` |
| Log hygiene | Structured logging with bounded context; no secrets logged; JSON logs optional | `backend/core/logging.py` |
| State-machine safety | Illegal safety transitions are impossible (FSM raises); E_STOP reachable from every state, single defined exit | `shared/fsm`, `shared/safety/machine.py` |
| Storage integrity | Atomic checkpoint writes (tmp+fsync+replace); orphan cleanup; SQLite transactions | `tools/project_state.py`, `data/` |

## Known gaps (must be closed before any non-local deployment)

1. **No authentication or authorization** on `/ws/node`, `/ws/state`, or REST.
   Assumption: trusted single-operator local network. Any exposure to an
   untrusted network must be preceded by M12 auth work (token-based WS
   handshake + operator credentials).
2. **No TLS.** `ws://`/`http://` only. Field use requires a reverse proxy or
   in-app TLS (M12).
3. **Single-device security model.** One SQLite file, one operator. No
   multi-tenant separation.
4. **Demo/dev binds `0.0.0.0`** so the app is reachable on the local network
   (required for preview tooling); combined with gap 1 this is acceptable
   only on trusted networks.
5. **E-stop is simulated.** The Python reference firmware reacts to a
   software safety input; a physical hardwired E-stop path (bypassing the
   MCU entirely) is an M10 hardware requirement and is NOT currently
   present.

## Review checklist (M12 entry)

- [ ] Threat model for field deployment (network, physical, firmware update)
- [ ] Auth design + implementation + tests
- [ ] TLS in front of the stack + tests
- [ ] Secrets handling for credentials store (currently: none exist)
- [ ] Firmware update channel integrity (out of scope until M9)
