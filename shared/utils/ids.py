"""ID helpers."""

from __future__ import annotations

import uuid


def new_message_id() -> str:
    return str(uuid.uuid4())


def new_connection_id() -> str:
    return "conn-" + uuid.uuid4().hex[:12]
