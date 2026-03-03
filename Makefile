PYTHON ?= python3

.PHONY: test coverage coverage-html lint

## Run all tests
test:
	$(PYTHON) -m pytest tests/ -v

## Run tests with coverage summary
coverage:
	$(PYTHON) -m pytest tests/ --cov=scripts --cov-report=term-missing --cov-fail-under=80

## Generate HTML coverage report
coverage-html:
	$(PYTHON) -m pytest tests/ --cov=scripts --cov-report=html:coverage_html --cov-report=term-missing
	@echo "Coverage report: coverage_html/index.html"

## Syntax-check all scripts
lint:
	@for f in scripts/*.py; do $(PYTHON) -c "import py_compile; py_compile.compile('$$f', doraise=True)"; done
	@for f in scripts/*.sh; do bash -n "$$f"; done
	@echo "All scripts OK"
