# GNU Make aliases; Windows can invoke the same Python runner directly.
PYTHON ?= python
.PHONY: setup up down migrate seed-demo reset-demo test lint build contracts smoke auth-smoke telemetry-smoke notification-smoke evidence-smoke report-smoke security-check restore-drill reference-load container-audit adapter-smoke commercial-smoke audit secret-scan e2e
setup up down migrate seed-demo test lint build contracts smoke auth-smoke telemetry-smoke notification-smoke evidence-smoke report-smoke security-check restore-drill reference-load container-audit adapter-smoke commercial-smoke audit secret-scan e2e:
	$(PYTHON) scripts/dev.py $@
reset-demo:
	$(PYTHON) scripts/dev.py reset-demo $(if $(filter 1,$(CONFIRM_LOCAL)),--confirm-local,)
