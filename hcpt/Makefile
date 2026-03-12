.PHONY: requirements install

VENV := .venv

ifeq ($(OS),Windows_NT)
    VENV_BIN := $(VENV)/Scripts
    PYTHON   := python
else
    VENV_BIN := $(VENV)/bin
    PYTHON   := python3
endif

PIP         := $(VENV_BIN)/pip
PIP_COMPILE := $(VENV_BIN)/pip-compile

$(VENV):
	$(PYTHON) -m venv $(VENV)

$(PIP_COMPILE): $(VENV)
	$(PIP) install pip-tools --quiet

requirements: $(PIP_COMPILE)
	$(PIP_COMPILE) requirements.in --output-file requirements.txt --strip-extras

install: $(VENV)
	$(PIP) install -r requirements.txt
