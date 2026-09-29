"""Per-connection ordering and duplicate detection (master directive §11).

Sequence numbers are strictly increasing per connection session (start 0).
message_id is the dedup key within a sliding window of seen ids.
"""

from __future__ import annotations

from collections import OrderedDict

from shared.constants import MAX_SEEN_MESSAGE_IDS
from shared.types import ValidationOutcome


class SequenceTracker:
    def __init__(self, max_seen: int = MAX_SEEN_MESSAGE_IDS) -> None:
        self._seen: OrderedDict[str, None] = OrderedDict()
        self._last_sequence = -1
        self._max_seen = max_seen

    @property
    def last_sequence(self) -> int:
        return self._last_sequence

    def check(self, message_id: str, sequence: int) -> ValidationOutcome:
        """Return DUPLICATE / OUT_OF_ORDER / VALID. Caller must record() on VALID."""
        if message_id in self._seen:
            return ValidationOutcome.DUPLICATE
        if sequence <= self._last_sequence:
            return ValidationOutcome.OUT_OF_ORDER
        return ValidationOutcome.VALID

    def record(self, message_id: str, sequence: int) -> None:
        self._seen[message_id] = None
        if len(self._seen) > self._max_seen:
            self._seen.popitem(last=False)
        self._last_sequence = sequence

    def reset(self) -> None:
        self._seen.clear()
        self._last_sequence = -1
