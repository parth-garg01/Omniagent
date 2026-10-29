VENV ?= .venv
PY := $(VENV)/bin/python

.PHONY: setup test lint seed run eval web-install web-test web-build up down

setup:
	python3 -m venv $(VENV)
	$(VENV)/bin/pip install -e "apps/api[dev]"

test:
	cd apps/api && ../../$(PY) -m pytest -q

lint:
	cd apps/api && ../../$(VENV)/bin/ruff check .

seed:
	cd apps/api && ../../$(PY) -m nova_api.seed

run:
	cd apps/api && ../../$(VENV)/bin/uvicorn nova_api.main:app --reload --port 8000

eval:
	cd apps/api && ../../$(PY) -m nova_api.evaluation.runner

web-install:
	cd apps/web && npm install

web-test:
	cd apps/web && npm test

web-build:
	cd apps/web && npm run build

up:
	docker compose up --build

down:
	docker compose down
