SHELL := /bin/bash
export LANG := C
export LC_ALL := C
NAME := bc250-llm-server
VERSION := $(shell cat VERSION)
TOPDIR := $(CURDIR)/rpmbuild
DISTDIR := $(CURDIR)/dist
UPSTREAM_SOURCES := $(shell ./scripts/prepare-sources.py --print-files)

.PHONY: help sources sources-check lint source-tar preflight validate prepare-rpm-output rpm-tree srpm rpm check-rpm-payload check-srpm-rebuild release-gate clean clean-sources distclean

help:
	@printf '%s\n' \
	  'make sources    Download pinned governor and live-manager sources' \
	  'make sources-check  Verify the local source cache and SHA-256 sidecars' \
	  'make lint       Run Ruff and ShellCheck' \
	  'make preflight  Run cheap source/structure checks' \
	  'make validate   Run preflight plus deterministic tests' \
	  'make source-tar Create the project source archive' \
	  'make srpm       Build the source RPM' \
	  'make rpm        Build binary and source RPMs' \
	  'make check-rpm-payload  Verify the built greenfield RPM file surface' \
	  'make check-srpm-rebuild  Rebuild the generated SRPM from a clean temporary topdir' \
	  'make release-gate  Run the authoritative Fedora workstation/CI RPM gate' \
	  'make clean      Remove disposable build output; keep downloaded sources' \
	  'make clean-sources  Remove the reusable third-party source cache'

sources:
	./scripts/prepare-sources.py
	./scripts/check-upstream-patches.py

sources-check:
	./scripts/prepare-sources.py --check
	./scripts/check-upstream-patches.py

lint:
	ruff check .
	@set -Eeuo pipefail; \
	while IFS= read -r file; do \
	  if head -n1 "$$file" | grep -qE '^#!.*[ /](ba)?sh([[:space:]]|$$)'; then \
	    shellcheck --severity=error "$$file"; \
	  fi; \
	done < <(find . -type f \
	  -not -path './sources/*' -not -path './build/*' \
	  -not -path './governor-src/*' -not -path './live-manager-src/*')

source-tar:
	./scripts/make-source-tarball.sh

preflight:
	./scripts/validate.sh --preflight

validate:
	./scripts/validate.sh

prepare-rpm-output:
	rm -rf $(TOPDIR)
	mkdir -p $(DISTDIR)
	rm -f $(DISTDIR)/*.rpm $(DISTDIR)/*.src.rpm $(DISTDIR)/SHA256SUMS

rpm-tree: prepare-rpm-output sources source-tar preflight
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
	mapfile -t main_rpms < <(find '$(DISTDIR)' -maxdepth 1 -type f -name '$(NAME)-$(VERSION)-*.x86_64.rpm' \
	  ! -name '*-debuginfo-*' ! -name '*-debugsource-*' -print | sort); \
	[[ "$${#main_rpms[@]}" -eq 1 ]] || { \
	  echo "ERROR: expected exactly one current main binary RPM in $(DISTDIR), found $${#main_rpms[@]}." >&2; \
	  printf '  %s\n' "$${main_rpms[@]:-}" >&2; exit 1; \
	}; \
	main_rpm="$${main_rpms[0]}"; \
	payload="$$(mktemp)"; trap 'rm -f "$$payload"' EXIT; \
	rpm -qpl "$$main_rpm" > "$$payload"; \
	for path in \
	  /usr/bin/bc250 \
	  /usr/bin/bc250-40cu \
	  /usr/bin/bc250-cu-live-manager \
	  /usr/bin/llm-run-diagnose \
	  /usr/libexec/bc250-llm-server/install-ollama.sh \
	  /usr/libexec/bc250-llm-server/status-json.py \
	  /usr/libexec/bc250-llm-server/doctor.py \
	  /usr/libexec/bc250-llm-server/gfx1013.sh \
	  /usr/libexec/bc250-llm-server/gfx1013-ab.py \
	  /usr/libexec/bc250-llm-server/qualification/package_gate_capture.py \
	  /usr/libexec/bc250-llm-server/qualification/resilience_manager.py \
	  /usr/libexec/bc250-llm-server/qualification/qualification_inventory.py \
	  /usr/libexec/bc250-llm-server/version.py \
	  /usr/share/bash-completion/completions/bc250 \
	  /usr/share/bc250-llm-server/gfx1013/upstream/PATCH-SHA256SUMS \
	  /usr/share/bc250-llm-server/gfx1013/upstream/SOURCE-SHA256SUMS \
	  /usr/share/doc/bc250-llm-server/docs/GFX1013.md \
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

check-srpm-rebuild:
	@set -Eeuo pipefail; \
	mapfile -t srpms < <(find '$(DISTDIR)' -maxdepth 1 -type f -name '$(NAME)-$(VERSION)-*.src.rpm' -print | sort); \
	[[ "$${#srpms[@]}" -eq 1 ]] || { echo "ERROR: expected exactly one current SRPM, found $${#srpms[@]}." >&2; exit 1; }; \
	top="$$(mktemp -d)"; trap 'rm -rf "$$top"' EXIT; \
	mkdir -p "$$top"/{BUILD,BUILDROOT,RPMS,SOURCES,SPECS,SRPMS}; \
	CARGO_NET_OFFLINE=true rpmbuild --define "_topdir $$top" --rebuild "$${srpms[0]}"; \
	echo "SRPM self-contained rebuild passed: $$(basename "$${srpms[0]}")"

release-gate:
	$(MAKE) clean
	$(MAKE) sources
	$(MAKE) sources-check
	$(MAKE) lint
	$(MAKE) preflight
	$(MAKE) rpm </dev/null
	rpmlint -c packaging/rpmlint.toml $(DISTDIR)/*.rpm
	$(MAKE) check-rpm-payload
	$(MAKE) check-srpm-rebuild


clean:
	rm -rf build dist rpmbuild

clean-sources:
	rm -f sources/*.tar.gz sources/*.tar.xz sources/*.sha256

distclean: clean clean-sources
