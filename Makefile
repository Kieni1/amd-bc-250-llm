SHELL := /bin/bash
NAME := bc250-llm-server
VERSION := $(shell cat VERSION)
TOPDIR := $(CURDIR)/rpmbuild
DISTDIR := $(CURDIR)/dist
UPSTREAM_SOURCES := $(shell ./scripts/prepare-sources.py --print-files)

.PHONY: help sources sources-check source-tar rpm-tree srpm rpm check-rpm-payload validate clean clean-sources distclean

help:
	@printf '%s\n' \
	  'make sources    Download pinned governor and live-manager sources' \
	  'make sources-check  Verify the local source cache and SHA-256 sidecars' \
	  'make validate   Run deterministic RPM preflight checks' \
	  'make source-tar Create the project source archive' \
	  'make srpm       Build the source RPM' \
	  'make rpm        Build binary and source RPMs' \
	  'make check-rpm-payload  Verify the built greenfield RPM file surface' \
	  'make clean      Remove disposable build output; keep downloaded sources' \
	  'make clean-sources  Remove the reusable third-party source cache'

sources:
	./scripts/prepare-sources.py
	./scripts/check-upstream-patches.py

sources-check:
	./scripts/prepare-sources.py --check
	./scripts/check-upstream-patches.py

source-tar:
	./scripts/make-source-tarball.sh

validate:
	./scripts/validate.sh

rpm-tree: sources source-tar validate
	mkdir -p $(TOPDIR)/{BUILD,BUILDROOT,RPMS,SOURCES,SPECS,SRPMS} $(DISTDIR)
	cp build/$(NAME)-$(VERSION).tar.gz $(TOPDIR)/SOURCES/
	cp $(UPSTREAM_SOURCES) $(TOPDIR)/SOURCES/
	cp packaging/$(NAME).spec $(TOPDIR)/SPECS/

srpm: rpm-tree
	rpmbuild --define '_topdir $(TOPDIR)' -bs $(TOPDIR)/SPECS/$(NAME).spec
	cp -f $(TOPDIR)/SRPMS/*.src.rpm $(DISTDIR)/
	cd $(DISTDIR) && sha256sum *.src.rpm > SHA256SUMS

rpm: rpm-tree
	rpmbuild --define '_topdir $(TOPDIR)' -ba $(TOPDIR)/SPECS/$(NAME).spec
	find $(TOPDIR)/RPMS -type f -name '*.rpm' -exec cp -f {} $(DISTDIR)/ \;
	find $(TOPDIR)/SRPMS -type f -name '*.src.rpm' -exec cp -f {} $(DISTDIR)/ \;
	$(MAKE) check-rpm-payload
	cd $(DISTDIR) && sha256sum *.rpm > SHA256SUMS

check-rpm-payload:
	@set -Eeuo pipefail; \
	main_rpm="$$(find '$(DISTDIR)' -maxdepth 1 -type f -name '$(NAME)-$(VERSION)-*.x86_64.rpm' \
	  ! -name '*-debuginfo-*' ! -name '*-debugsource-*' -print -quit)"; \
	[[ -n "$$main_rpm" ]] || { echo 'ERROR: main binary RPM not found in $(DISTDIR).' >&2; exit 1; }; \
	payload="$$(mktemp)"; trap 'rm -f "$$payload"' EXIT; \
	rpm -qpl "$$main_rpm" > "$$payload"; \
	for path in \
	  /usr/bin/bc250 \
	  /usr/bin/bc250-40cu \
	  /usr/bin/bc250-cu-live-manager \
	  /usr/bin/llm-run-diagnose \
	  /usr/libexec/bc250-llm-server/install-ollama.sh \
	  /usr/share/doc/bc250-llm-server/docs/RAG.md \
	  /usr/share/licenses/bc250-llm-server/LICENSE \
	  /usr/share/licenses/bc250-llm-server/LICENSE.cyan-skillfish-governor \
	  /srv/bc250-documents; do \
	  grep -Fxq "$$path" "$$payload" || { echo "ERROR: required RPM path missing: $$path" >&2; exit 1; }; \
	done; \
	unexpected="$$(grep '^/usr/bin/bc250-' "$$payload" | \
	  grep -vE '^/usr/bin/bc250-(40cu|cu-live-manager)$$' || true)"; \
	[[ -z "$$unexpected" ]] || { echo 'ERROR: obsolete public bc250-* command(s) remain:' >&2; printf '%s\n' "$$unexpected" >&2; exit 1; }; \
	ollama_group_provides="$$(rpm -qp --provides "$$main_rpm" | grep -Ec '^group\(ollama\)([ =]|$$)' || true)"; \
	[[ "$$ollama_group_provides" -eq 1 ]] || { echo "ERROR: expected exactly one generated group(ollama) provide, got $$ollama_group_provides" >&2; exit 1; }; \
	if grep -Eq 'bc250-40cu-unlock|40cu-module|/quality-checks/|/usr/share/doc/bc250-llm-server/(cmd|config|packaging)/|eurollm9b' "$$payload"; then \
	  echo 'ERROR: obsolete or source-only asset remains in the binary RPM:' >&2; \
	  grep -E 'bc250-40cu-unlock|40cu-module|/quality-checks/|/usr/share/doc/bc250-llm-server/(cmd|config|packaging)/|eurollm9b' "$$payload" >&2; \
	  exit 1; \
	fi; \
	echo "RPM payload contract passed: $$(basename "$$main_rpm")"

clean:
	rm -rf build dist rpmbuild

clean-sources:
	rm -f sources/*.tar.gz sources/*.tar.xz sources/*.sha256

distclean: clean clean-sources
