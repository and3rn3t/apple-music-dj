PYTHON ?= python3

.PHONY: help setup test test-fast coverage coverage-html lint ruff typecheck actionlint ci audit demo-svg social-preview

## List the make targets
help:
	@awk '/^## /{desc=substr($$0,4); next} /^[a-z][a-z-]*:/{if(desc){split($$1,t,":"); printf "  %-14s %s\n", t[1], desc} desc=""}' $(MAKEFILE_LIST)

## Create .venv, install the dev tools and git hooks, and check the system tools the scripts and CI need
setup:
	@$(PYTHON) -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else "ERROR: Python 3.11+ is required (this is $(PYTHON))")'
	@# A venv copied or moved from another folder keeps scripts whose #! line names the old one (and still
	@# works while the old folder exists): rebuild it unless pip's #! line points into this .venv
	@.venv/bin/python -c 'import pathlib, sys; first = pathlib.Path(".venv/bin/pip").read_text().splitlines()[0]; sys.exit(0 if first.startswith("#!" + str(pathlib.Path(".venv/bin").resolve()) + "/") else 1)' 2>/dev/null || $(PYTHON) -m venv --clear .venv
	@.venv/bin/python -m pip install --quiet --upgrade pip
	@.venv/bin/python -m pip install --quiet -e ".[dev]"
	@missing=0; \
	for tool in bash curl jq; do \
	  command -v $$tool >/dev/null || { echo "MISSING: $$tool (the scripts need it)"; missing=1; }; \
	done; \
	command -v actionlint >/dev/null || echo "NOTE: actionlint is not installed; 'make ci' needs it (brew install actionlint)"; \
	[ $$missing -eq 0 ] || exit 1
	@# Git hooks (ruff, ShellCheck, Conventional Commits): only inside a git checkout (a plain one, or a linked
	@# worktree or submodule, where .git is a file), never fatal
	@if [ -e .git ]; then .venv/bin/pre-commit install --hook-type pre-commit --hook-type commit-msg >/dev/null && echo "Git hooks installed (ruff, ShellCheck, commit-message check)." || echo "NOTE: could not install the git hooks; run: .venv/bin/pre-commit install --hook-type pre-commit --hook-type commit-msg"; fi
	@echo "Ready. Run:  . .venv/bin/activate && make ci   (make help lists everything else)"

## Run all tests
test:
	$(PYTHON) -m pytest tests/

## Run all tests in parallel on every core (pytest-xdist)
test-fast:
	$(PYTHON) -m pytest tests/ -n auto -q

## Run tests with coverage summary
coverage:
	$(PYTHON) -m pytest tests/ --cov=scripts --cov-report=term-missing --cov-fail-under=90

## Generate HTML coverage report
coverage-html:
	$(PYTHON) -m pytest tests/ --cov=scripts --cov-report=html:coverage_html --cov-report=term-missing
	@echo "Coverage report: coverage_html/index.html"

## Ruff (Python) and ShellCheck (bash)
ruff:
	$(PYTHON) -m ruff check scripts tests .github/scripts
	shellcheck scripts/*.sh

## Type-check scripts/ (non-strict; tests/ is out of scope for now)
typecheck:
	$(PYTHON) -m mypy

## Lint the GitHub Actions workflows (same check as CI's actionlint job)
actionlint:
	actionlint

## Everything CI checks, in one command: ruff + ShellCheck, mypy, tests with the coverage floor, workflows
ci: ruff typecheck coverage actionlint
	@echo "CI checks passed"

## Syntax-check all scripts
lint:
	@for f in scripts/*.py; do $(PYTHON) -c "import py_compile; py_compile.compile('$$f', doraise=True)"; done
	@for f in scripts/*.sh; do bash -n "$$f"; done
	@echo "All scripts OK"

## Pre-publish self-audit: trust checks, shipped changes since the last tag, and a review prompt
audit:
	$(PYTHON) .github/scripts/self_audit.py

## Regenerate the README's animated demo (assets/demo-tour.svg) from the real `demo.py tour`
demo-svg:
	$(PYTHON) .github/scripts/make_demo_svg.py

## Regenerate the GitHub social preview card (assets/social-preview.png); upload it in repo settings
social-preview:
	$(PYTHON) .github/scripts/make_social_preview.py
