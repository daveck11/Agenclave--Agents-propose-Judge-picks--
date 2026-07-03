# Agenclave - task runner.
# Windows (no `make`)? Each target maps to a one-line command shown in the README
# Quickstart; run that command directly in PowerShell.

PY ?= python
VENV ?= .venv

.PHONY: help setup data train eval stage1 serve demo web-build app dev test trust clean

help:
	@echo "Targets: setup | stage1 (data train eval) | app | dev | serve | demo | test | trust"
	@echo "  app  = build UI + serve the whole product on :8000 (single command)"
	@echo "  dev  = how to run API + Vite hot-reload for development"

setup:                ## create venv + install pinned deps
	$(PY) -m venv $(VENV)
	$(VENV)/Scripts/pip install -U pip
	$(VENV)/Scripts/pip install -r requirements.txt
	$(VENV)/Scripts/pip install -e .

data:                 ## download + prepare datasets (writes data/ + data/README.md)
	$(PY) scripts/prepare_data.py

train:                ## train TF-IDF + embedding classifiers, save models/
	$(PY) scripts/train_classifier.py

eval:                 ## evaluate on held-out test set, write results/classifier_metrics.json
	$(PY) scripts/evaluate_classifier.py

stage1: data train eval ## full Stage 1 pipeline (data -> train -> eval)

serve:                ## run the FastAPI triage service on :8000
	$(PY) -m uvicorn agenclave.api.main:app --reload --port 8000

demo:                 ## run the Vite React demo (expects `serve` running)
	cd frontend && npm install && npm run dev

web-build:            ## build the React app into frontend/dist
	cd frontend && npm install && npm run build

app: web-build        ## build the UI + serve the WHOLE product (UI+API) on :8000
	$(PY) -m uvicorn agenclave.api.main:app --port 8000

dev:                  ## how to run API + Vite hot-reload (two terminals)
	@echo "Development (hot reload), run in two terminals:"
	@echo "  1) make serve   # FastAPI on :8000"
	@echo "  2) make demo    # Vite dev server on :5173 (proxies to :8000)"

test:                 ## run the pytest suite
	$(PY) -m pytest

trust:                ## verified best-of-N -> per-model reliability (dry run by default)
	$(PY) scripts/verified_run.py

clean:
	rm -rf $(VENV) **/__pycache__ .pytest_cache
