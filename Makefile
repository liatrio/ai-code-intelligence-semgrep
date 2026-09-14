.PHONY: check install scan status clean

PY ?= python3
REPO ?=
RULES ?= ./rules

help:
	@echo "make check                     # prerequisites report, installs nothing"
	@echo "make install                   # install pinned semgrep via uv/pipx"
	@echo "make scan REPO=/abs/path       # semgrep scan --config \$$(RULES) REPO"
	@echo "make status REPO=/abs/path     # informational: Semgrep has no persistent index"
	@echo "make clean                     # uninstall semgrep + drop lab state"

check:
	$(PY) setup.py --check

install:
	$(PY) setup.py

scan:
	@if [ -z "$(REPO)" ]; then echo "REPO=/abs/path required"; exit 2; fi
	$(PY) setup.py --scan $(REPO) --rules $(RULES)

status:
	@if [ -z "$(REPO)" ]; then echo "REPO=/abs/path required"; exit 2; fi
	$(PY) setup.py --status $(REPO)

clean:
	$(PY) setup.py --clean
