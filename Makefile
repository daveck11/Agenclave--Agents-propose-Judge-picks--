# Agenclave — task runner.
# Windows (no `make`)? Each target maps to a one-line command shown in the README
# Quickstart; run that command directly in PowerShell.

PY ?= python
VENV ?= .venv

.PHONY: help setup data train eval stage1 serve demo test stage2 clean

help:
	@echo "Targets: setup | data | train | eval | stage1 | serve | demo | test | stage2"

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

test:                 ## run the pytest suite
	$(PY) -m pytest

stage2:               ## run the Chairman best-of-N harness on the SWE-bench slice
	$(PY) scripts/run_chairman.py

clean:
	rm -rf $(VENV) **/__pycache__ .pytest_cache
