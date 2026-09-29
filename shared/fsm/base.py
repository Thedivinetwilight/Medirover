"""Data-driven finite state machine with explicit failure on bad transitions.

Generic over state/event types so `.state` keeps its enum type at call sites.
"""

from __future__ import annotations

from collections.abc import Callable, Hashable, Mapping, Sequence
from typing import Generic, TypeVar

from shared.errors import SAFETY_INVALID_TRANSITION, MediroverError

S = TypeVar("S", bound=Hashable)
E = TypeVar("E", bound=Hashable)


class FSMError(MediroverError):
    """Raised when a disallowed state transition is attempted."""

    def __init__(self, machine: str, state: object, event: object, allowed: Sequence[object]) -> None:
        self.machine = machine
        self.state = state
        self.event = event
        self.allowed = allowed
        super().__init__(
            f"[{machine}] invalid transition: {state!r} -[{event!r}]-> ? "
            f"(allowed: {[str(e) for e in allowed] or 'none'})",
            code=SAFETY_INVALID_TRANSITION,
            source=machine,
            details={"state": str(state), "event": str(event), "allowed": [str(e) for e in allowed]},
        )


class StateMachine(Generic[S, E]):
    """A minimal, fully explicit FSM.

    Transitions are a mapping of (state, event) -> next_state.
    Anything not in the table is illegal and raises FSMError.
    Optional entry actions run after a successful transition.
    """

    def __init__(
        self,
        name: str,
        states: set[S],
        initial: S,
        transitions: Mapping[tuple[S, E], S],
        entry_actions: Mapping[S, Callable[[], None]] | None = None,
    ) -> None:
        self.name = name
        self.states = set(states)
        self._transitions: dict[tuple[S, E], S] = dict(transitions)
        self._entry_actions: Mapping[S, Callable[[], None]] = entry_actions or {}
        if initial not in states:
            raise ValueError(f"[{name}] initial state {initial!r} not in states")
        # sanity: every transition endpoint must be a declared state
        for (src, _ev), dst in self._transitions.items():
            if src not in states or dst not in states:
                raise ValueError(f"[{name}] transition {src!r} -> {dst!r} uses undeclared state")
        self._state = initial

    @property
    def state(self) -> S:
        return self._state

    def allowed_events(self) -> list[E]:
        return sorted({ev for (s, ev) in self._transitions if s == self._state}, key=str)

    def can(self, event: E) -> bool:
        return (self._state, event) in self._transitions

    def send(self, event: E) -> S:
        """Apply an event. Returns the new state or raises FSMError."""
        key = (self._state, event)
        if key not in self._transitions:
            raise FSMError(self.name, self._state, event, self.allowed_events())
        self._state = self._transitions[key]
        action = self._entry_actions.get(self._state)
        if action is not None:
            action()
        return self._state

    def all_transitions(self) -> list[tuple[S, E, S]]:
        return [
            (s, e, d)
            for (s, e), d in sorted(self._transitions.items(), key=lambda kv: (str(kv[0][0]), str(kv[0][1])))
        ]

    def describe(self) -> str:
        lines = [f"FSM {self.name} (initial={self._state!r})"]
        for s, e, d in self.all_transitions():
            lines.append(f"  {s!r} -[{e!r}]-> {d!r}")
        return "\n".join(lines)
