PYTHON ?= python3

.PHONY: test test-fast coverage coverage-html lint ruff actionlint ci audit demo-svg social-preview

## Run all tests
test:
	$(PYTHON) -m pytest tests/

## Run all tests in parallel on every core (pytest-xdist)
test-fast:
	$(PYTHON) -m pytest tests/ -n auto -q

## Run tests with coverage summary
coverage:
	$(PYTHON) -m pytest tests/ --cov=scripts --cov-report=term-missing --cov-fail-under=80

## Generate HTML coverage report
coverage-html:
	$(PYTHON) -m pytest tests/ --cov=scripts --cov-report=html:coverage_html --cov-report=term-missing
	@echo "Coverage report: coverage_html/index.html"

## Ruff (Python) and ShellCheck (bash)
ruff:
	$(PYTHON) -m ruff check scripts tests .github/scripts
	shellcheck scripts/*.sh

## Lint the GitHub Actions workflows (same check as CI's actionlint job)
actionlint:
	actionlint

## Everything CI checks, in one command: ruff + ShellCheck, tests with the coverage floor, workflows
ci: ruff coverage actionlint
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
