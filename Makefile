.PHONY: requirements install

VENV := .venv
PIP  := $(VENV)/bin/pip
PIP_COMPILE := $(VENV)/bin/pip-compile

$(VENV):
	python3 -m venv $(VENV)

$(PIP_COMPILE): $(VENV)
	$(PIP) install pip-tools --quiet

requirements: $(PIP_COMPILE)
	$(PIP_COMPILE) requirements.in --output-file requirements.txt --strip-extras

install: $(VENV)
	$(PIP) install -r requirements.txt
