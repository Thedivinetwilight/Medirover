"""Uvicorn entrypoint: `uvicorn backend.main:app`.

The environment is selected via MEDIROVER_ENVIRONMENT
(development | testing | simulation | hardware).
"""

from __future__ import annotations

from backend.api.app import create_app
from backend.config import load_default_config

app = create_app(load_default_config())
