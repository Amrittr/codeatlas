PYTHON ?= python3
VENV := backend/.venv
PY := $(VENV)/bin/python
PORT ?= 8000

.PHONY: setup css watch-css dev test test-backend test-frontend test-e2e check sample clean

## setup: create the Python venv, install pinned dependencies, install Tailwind and build CSS
setup: $(VENV)/.installed frontend/node_modules/.installed css

$(VENV)/.installed: backend/requirements.txt backend/requirements-dev.txt
	$(PYTHON) -m venv $(VENV)
	$(PY) -m pip install --upgrade pip
	$(PY) -m pip install -r backend/requirements-dev.txt
	touch $@

frontend/node_modules/.installed: frontend/package.json frontend/package-lock.json
	cd frontend && npm ci
	touch $@

## css: compile Tailwind into frontend/public/assets/app.css
css:
	cd frontend && npm run build:css

watch-css:
	cd frontend && npm run watch:css

## dev: build CSS, then serve the API and UI on http://localhost:$(PORT)
dev: css
	cd backend && .venv/bin/uvicorn app.main:app --reload --port $(PORT)

## test: backend unit/API tests + frontend unit tests
test: test-backend test-frontend

test-backend:
	cd backend && .venv/bin/python -m pytest

test-frontend:
	cd frontend && npm test

## test-e2e: browser tests with Playwright (needs `make setup` and `.venv/bin/playwright install chromium`)
test-e2e: css
	cd backend && .venv/bin/python -m pytest -m e2e tests/e2e

## check: syntax-check every Python and JS source file
check:
	$(PY) -m compileall -q backend/app
	find frontend/public/js -name '*.js' -exec node --check {} \;

## sample: write demo archives to samples/ for manual testing
sample:
	$(PY) scripts/make_sample_zip.py

clean:
	rm -rf frontend/public/assets/app.css samples test-results
