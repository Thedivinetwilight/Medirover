PYTHON ?= python3
VENV := .venv
PIP := $(VENV)/bin/pip
PY := $(VENV)/bin/python

.PHONY: venv install test lint typecheck check demo migrate clean-checkout storage-audit manifest

venv:
	$(PYTHON) -m venv $(VENV)
	$(PIP) install --upgrade pip

install: venv
	$(PIP) install -e ".[dev]"

test:
	$(PY) -m pytest

test-frontend:
	node --test 'frontend/tests/**/*.test.mjs'

lint:
	$(PY) -m ruff check .

typecheck:
	$(PY) -m mypy

check: lint typecheck test

migrate:
	MEDIROVER_DB_URL=$$($(PY) -c 'from backend.config import load_default_config; print(load_default_config().db_url)') \
		$(PY) -m alembic upgrade head

demo:
	$(PY) scripts/demo.py

clean-checkout:
	$(PY) scripts/clean_checkout.py

storage-audit:
	$(PY) tools/storage.py audit

manifest:
	$(PY) tools/artifact_manifest.py build
