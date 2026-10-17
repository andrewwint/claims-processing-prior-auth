# Regular commands. AWS credentials come from whatever AWS_PROFILE is set in your shell;
# nothing here names a profile or an account. Teardown is deliberately not a target: it runs
# once, through its own script (python -m scripts.teardown --yes).

PY := .venv/bin/python
BEAT ?= 1

.PHONY: help test demo workbench deploy smoke verify-chain report scan

help: ## List the targets
	@grep -E "^[a-z-]+:.*## " $(MAKEFILE_LIST) | awk -F ":.*## " '{printf "  %-13s %s\n", $$1, $$2}'

test: ## Run the test suite
	$(PY) -m pytest -q

demo: ## Run one demo beat, identifiers masked (BEAT=1..6; REDACT=0 to show them)
	$(PY) -m scripts.demo $(if $(filter 0,$(REDACT)),,--redact) $(BEAT)

workbench: ## Start the clinician workbench on 127.0.0.1:8765
	$(PY) -m scripts.workbench

deploy: ## Deploy one stack through the guard (STACK=PriorAuthRuntime; clean tree only)
	@test -n "$(STACK)" || (echo "usage: make deploy STACK=<stack>"; exit 2)
	$(PY) -m scripts.deploy $(STACK)

smoke: ## Rerun the boundary checks against the recorded evidence
	$(PY) -m scripts.boundary_smoke

verify-chain: ## Verify a decision chain (CASE=SYN-CASE-CF-1 RUN=<run id>)
	@test -n "$(CASE)" -a -n "$(RUN)" || (echo "usage: make verify-chain CASE=<case> RUN=<run id>"; exit 2)
	$(PY) -m scripts.verify_chain $(CASE) $(RUN)

report: ## Regenerate evaluation/report.md and SAMPLE_OUTPUTS.md from committed data
	$(PY) -m evaluation.report
	$(PY) -m scripts.sample_outputs

scan: ## The public-flip gate: identifiers in the tree and the full history
	$(PY) -m scripts.public_scan
