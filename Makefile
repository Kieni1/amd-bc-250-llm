SHELL := /bin/bash
export LANG := C
export LC_ALL := C
NAME := bc250-llm-server
VERSION := $(shell cat VERSION)
BUILD_DIR ?= $(CURDIR)/build
TOPDIR ?= $(CURDIR)/rpmbuild
DISTDIR ?= $(CURDIR)/dist
SOURCE_CACHE_DIR ?= $(CURDIR)/sources
_BC250_BUILD_DIR_ORIGIN := $(origin BC250_BUILD_DIR)
_BC250_BUILD_DIR_INPUT := $(BC250_BUILD_DIR)
ifneq ($(filter environment command line,$(_BC250_BUILD_DIR_ORIGIN)),)
ifneq ($(abspath $(_BC250_BUILD_DIR_INPUT)),$(abspath $(BUILD_DIR)))
$(error BC250_BUILD_DIR is internal to helper scripts; use BUILD_DIR=/path for Make-level build-root overrides)
endif
endif
override BC250_BUILD_DIR := $(BUILD_DIR)
BC250_SOURCE_DIR ?= $(SOURCE_CACHE_DIR)
PYTHONDONTWRITEBYTECODE ?= 1
export BC250_BUILD_DIR BC250_SOURCE_DIR PYTHONDONTWRITEBYTECODE
RPM_TREE_TARGET ?= rpm-tree
FROZEN_SPEC := $(BUILD_DIR)/$(NAME).spec
FROZEN_INPUTS := $(BUILD_DIR)/RPM-INPUTS.sha256
SOURCE_IDENTITY := $(BUILD_DIR)/SOURCE-IDENTITY.json
FROZEN_SOURCE_PARENT := $(BUILD_DIR)/frozen-source
FROZEN_SOURCE_DIR := $(FROZEN_SOURCE_PARENT)/$(NAME)-$(VERSION)
UPSTREAM_SOURCES := $(shell ./scripts/prepare-sources.py --print-files)
TIME_STAGE := ./scripts/time-stage.sh

.PHONY: help sources sources-check lint quality-report source-tar freeze-rpm-inputs check-frozen-source preflight validate prepare-rpm-output rpm-tree rpm-tree-frozen srpm artifact-manifests release-evidence release-selection check-rpm-payload rebuild-srpm check-rpmlint release-gate-preflight release-gate-package release-gate clean clean-sources distclean

help:
	@printf '%s\n' \
	  'make sources    Download pinned governor and live-manager sources' \
	  'make sources-check  Verify the local source cache and SHA-256 sidecars' \
	  'make lint       Run blocking Ruff and ShellCheck release preflight' \
	  'make quality-report  Run lint + full validation and report all issues without blocking artifacts' \
	  'make preflight  Run release-critical source/release-pipeline checks' \
	  'make validate   Run current guidance/scope plus the full advisory repository test suite' \
	  'make source-tar Create the project source archive' \
	  'make freeze-rpm-inputs  Freeze Source0/spec plus source identity before package build' \
	  'make check-frozen-source  Verify the exact frozen source/spec snapshot' \
	  'make srpm       Build the source RPM' \
	  'make artifact-manifests  Create closed binary/source checksum manifests' \
	  'make release-evidence  Emit CI/build evidence and, when explicitly selected, release-selection.json' \
	  'make BUILD_DIR=/path release-gate  Supported custom Make-level build root (BC250_BUILD_DIR is internal)' \
	  'make check-rpm-payload  Verify transformed binary RPM content and metadata' \
	  'make rebuild-srpm  Rebuild the generated SRPM in an isolated topdir and publish those exact binary RPMs' \
	  'make release-gate  Fedora RPM release gate; GitHub artifact is release authority, local execution reproduces the gate' \
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
	  -not -path './.git/*' -not -path './sources/*' -not -path './build/*' -not -path './.build/*' -not -path './dist/*' -not -path './rpmbuild/*' \
	  -not -path './vendor/*' -not -path './governor-src/*' -not -path './live-manager-src/*' \
	  -not -path './development/handovers/archive/*' -not -path './development/model-runs/*' -not -path './development/patchnotes/*' \
	  -not -path './quality-checks/history/*')


quality-report:
	@set +e; \
	mkdir -p '$(BUILD_DIR)'; \
	report='$(BUILD_DIR)/quality-report.txt'; \
	: > "$$report"; \
	echo '== Advisory quality report ==' | tee -a "$$report"; \
	$(MAKE) lint >>"$$report" 2>&1; lint_rc=$$?; \
	./scripts/validate.sh >>"$$report" 2>&1; validate_rc=$$?; \
	printf 'lint_rc=%s\nvalidate_rc=%s\n' "$$lint_rc" "$$validate_rc" | tee -a "$$report"; \
	if ((lint_rc == 0 && validate_rc == 0)); then \
	  echo 'Advisory quality report: PASS' | tee -a "$$report"; \
	else \
	  echo 'Advisory quality report: WARN (non-blocking; inspect report)' | tee -a "$$report"; \
	fi; \
	exit 0

source-tar:
	./scripts/make-source-tarball.sh

freeze-rpm-inputs:
	./scripts/check-release-source.sh '$(SOURCE_IDENTITY)'
	$(MAKE) source-tar
	cp -f packaging/$(NAME).spec $(FROZEN_SPEC)
	@cd '$(BUILD_DIR)' && sha256sum '$(NAME)-$(VERSION).tar.gz' '$(NAME).spec' > 'RPM-INPUTS.sha256'
	rm -rf '$(FROZEN_SOURCE_PARENT)'
	mkdir -p '$(FROZEN_SOURCE_PARENT)'
	tar -xzf '$(BUILD_DIR)/$(NAME)-$(VERSION).tar.gz' -C '$(FROZEN_SOURCE_PARENT)'
	@echo 'Frozen RPM source/spec inputs:'
	@cat '$(FROZEN_INPUTS)'

check-frozen-source:
	@set -Eeuo pipefail; \
	archive='$(BUILD_DIR)/$(NAME)-$(VERSION).tar.gz'; \
	spec='$(FROZEN_SPEC)'; inputs='$(FROZEN_INPUTS)'; src='$(FROZEN_SOURCE_DIR)'; \
	[[ -f "$$archive" && -f "$$spec" && -f "$$inputs" && -d "$$src" ]] || { \
	  echo 'ERROR: frozen RPM inputs/source tree are missing; run make freeze-rpm-inputs first.' >&2; exit 1; \
	}; \
	(cd '$(BUILD_DIR)' && sha256sum -c 'RPM-INPUTS.sha256'); \
	cmp -s "$$src/packaging/$(NAME).spec" "$$spec" || { \
	  echo 'ERROR: spec embedded in frozen Source0 differs from frozen RPM spec.' >&2; exit 1; \
	}; \
	cd "$$src"; \
	env -u BC250_BUILD_DIR -u BC250_SOURCE_DIR PYTHONDONTWRITEBYTECODE=1 \
	  bash scripts/validate.sh --preflight </dev/null; \
	echo 'Frozen Source0/spec preflight passed.'

preflight:
	./scripts/validate.sh --preflight

validate:
	./scripts/validate.sh

prepare-rpm-output:
	rm -rf $(TOPDIR)
	mkdir -p $(DISTDIR)
	rm -f $(DISTDIR)/*.rpm $(DISTDIR)/*.src.rpm $(DISTDIR)/SHA256SUMS $(DISTDIR)/SHA256SUMS.binary $(DISTDIR)/SHA256SUMS.source $(DISTDIR)/SHA256SUMS.inputs $(DISTDIR)/release-evidence.json $(DISTDIR)/release-selection.json

define populate-rpm-tree
	mkdir -p $(TOPDIR)/{BUILD,BUILDROOT,RPMS,SOURCES,SPECS,SRPMS} $(DISTDIR)
	cp $(BUILD_DIR)/$(NAME)-$(VERSION).tar.gz $(TOPDIR)/SOURCES/
	cp $(UPSTREAM_SOURCES) $(TOPDIR)/SOURCES/
	cp packaging/$(NAME).spec $(TOPDIR)/SPECS/
endef

rpm-tree: prepare-rpm-output sources source-tar preflight
	$(populate-rpm-tree)

rpm-tree-frozen: prepare-rpm-output
	@cd '$(BUILD_DIR)' && sha256sum -c 'RPM-INPUTS.sha256'
	mkdir -p $(TOPDIR)/{BUILD,BUILDROOT,RPMS,SOURCES,SPECS,SRPMS} $(DISTDIR)
	cp $(BUILD_DIR)/$(NAME)-$(VERSION).tar.gz $(TOPDIR)/SOURCES/
	cp $(UPSTREAM_SOURCES) $(TOPDIR)/SOURCES/
	cp $(FROZEN_SPEC) $(TOPDIR)/SPECS/$(NAME).spec

srpm: $(RPM_TREE_TARGET)
	rpmbuild --define '_topdir $(TOPDIR)' -bs $(TOPDIR)/SPECS/$(NAME).spec
	cp -f $(TOPDIR)/SRPMS/*.src.rpm $(DISTDIR)/
	cd $(DISTDIR) && sha256sum *.src.rpm > SHA256SUMS.source && cp SHA256SUMS.source SHA256SUMS

artifact-manifests:
	@set -Eeuo pipefail; \
	cd '$(DISTDIR)'; \
	shopt -s nullglob; \
	binary_rpms=( *.x86_64.rpm ); \
	source_rpms=( *.src.rpm ); \
	[[ "$${#binary_rpms[@]}" -gt 0 ]] || { echo 'ERROR: no binary RPMs found for closed manifest.' >&2; exit 1; }; \
	[[ "$${#source_rpms[@]}" -gt 0 ]] || { echo 'ERROR: no source RPMs found for closed manifest.' >&2; exit 1; }; \
	sha256sum "$${binary_rpms[@]}" > SHA256SUMS.binary; \
	sha256sum "$${source_rpms[@]}" > SHA256SUMS.source; \
	cat SHA256SUMS.binary SHA256SUMS.source > SHA256SUMS; \
	sha256sum -c SHA256SUMS.binary; \
	sha256sum -c SHA256SUMS.source

release-evidence: artifact-manifests
	./scripts/release-evidence.py \
	  --source0 '$(BUILD_DIR)/$(NAME)-$(VERSION).tar.gz' \
	  --spec '$(FROZEN_SPEC)' \
	  --dist '$(DISTDIR)' \
	  --source-identity '$(SOURCE_IDENTITY)' \
	  --contract release-contract.json \
	  --output '$(DISTDIR)/release-evidence.json'
	@if [[ "$${BC250_RELEASE_AUTHORITY:-false}" == true ]]; then \
	  $(MAKE) release-selection; \
	else \
	  rm -f '$(DISTDIR)/release-selection.json'; \
	fi

release-selection:
	./scripts/release-selection.py \
	  --evidence '$(DISTDIR)/release-evidence.json' \
	  --output '$(DISTDIR)/release-selection.json'

check-rpm-payload:
	@set -Eeuo pipefail; \
	mapfile -t main_rpms < <(find '$(DISTDIR)' -maxdepth 1 -type f -name '$(NAME)-$(VERSION)-*.x86_64.rpm' \
	  ! -name '*-debuginfo-*' ! -name '*-debugsource-*' -print | sort); \
	[[ "$${#main_rpms[@]}" -eq 1 ]] || { \
	  echo "ERROR: expected exactly one current main binary RPM in $(DISTDIR), found $${#main_rpms[@]}." >&2; \
	  printf '  %s\n' "$${main_rpms[@]:-}" >&2; exit 1; \
	}; \
	main_rpm="$${main_rpms[0]}"; \
	payload="$$(mktemp)"; extracted="$$(mktemp -d)"; trap 'rm -f "$$payload"; rm -rf "$$extracted"' EXIT; \
	rpm -qpl "$$main_rpm" > "$$payload"; \
	for path in \
	  /usr/bin/bc250 \
	  /usr/libexec/bc250-llm-server/advanced \
	  /usr/bin/bc250-40cu \
	  /usr/bin/bc250-cu-live-manager \
	  /usr/libexec/bc250-llm-server/parity-diagnose.sh \
	  /usr/libexec/bc250-llm-server/install-ollama.sh \
	  /usr/libexec/bc250-llm-server/status-json.py \
	  /usr/libexec/bc250-llm-server/health.py \
	  /usr/libexec/bc250-llm-server/qualification/package_gate_capture.py \
	  /usr/libexec/bc250-llm-server/qualification/resilience_manager.py \
	  /usr/libexec/bc250-llm-server/qualification/qualification_inventory.py \
	  /usr/libexec/bc250-llm-server/version.py \
	  /usr/share/bash-completion/completions/bc250 \
	  /usr/share/bc250-llm-server/VERSION \
	  /usr/share/bc250-llm-server/runtime.env \
	  /usr/share/doc/bc250-llm-server/docs/RAG.md \
	  /usr/share/licenses/bc250-llm-server/LICENSE \
	  /usr/share/licenses/bc250-llm-server/LICENSE.cyan-skillfish-governor \
	  /srv/bc250-documents; do \
	  grep -Fxq "$$path" "$$payload" || { echo "ERROR: required RPM path missing: $$path" >&2; exit 1; }; \
	done; \
	unexpected="$$(grep '^/usr/bin/bc250-' "$$payload" | grep -vE '^/usr/bin/bc250-(40cu|cu-live-manager)$$' || true)"; \
	[[ -z "$$unexpected" ]] || { echo 'ERROR: obsolete public bc250-* command(s) remain:' >&2; printf '%s\n' "$$unexpected" >&2; exit 1; }; \
	ollama_group_provides="$$(rpm -qp --provides "$$main_rpm" | grep -Ec '^group\(ollama\)([ =]|$$)' || true)"; \
	[[ "$$ollama_group_provides" -eq 1 ]] || { echo "ERROR: expected exactly one generated group(ollama) provide, got $$ollama_group_provides" >&2; exit 1; }; \
	if grep -Eqi 'bc250-40cu-unlock|40cu-module|gfx''1013|/quality-checks/|/usr/share/doc/bc250-llm-server/(cmd|config|packaging)/|eurollm9b' "$$payload"; then \
	  echo 'ERROR: obsolete, GFX, or source-only asset remains in binary RPM.' >&2; exit 1; \
	fi; \
	main_rpm_abs="$$(readlink -f "$$main_rpm")"; \
	(cd "$$extracted" && rpm2cpio "$$main_rpm_abs" | cpio -idm --quiet); \
	cmp -s config/runtime.env "$$extracted/usr/share/bc250-llm-server/runtime.env" || { echo 'ERROR: packaged runtime.env differs from source authority.' >&2; exit 1; }; \
	cmp -s VERSION "$$extracted/usr/share/bc250-llm-server/VERSION" || { echo 'ERROR: packaged VERSION differs from source authority.' >&2; exit 1; }; \
	[[ "$$(stat -c '%a' "$$extracted/usr/bin/bc250")" == 755 ]] || { echo 'ERROR: packaged bc250 dispatcher is not mode 0755.' >&2; exit 1; }; \
	[[ "$$(stat -c '%a' "$$extracted/usr/share/bc250-llm-server/runtime.env")" == 644 ]] || { echo 'ERROR: packaged runtime.env is not mode 0644.' >&2; exit 1; }; \
	echo "Transformed RPM payload integrity passed: runtime/version/mode contract"; \
	echo "RPM payload contract passed: $$(basename "$$main_rpm")"

rebuild-srpm:
	@set -Eeuo pipefail; \
	mapfile -t srpms < <(find '$(DISTDIR)' -maxdepth 1 -type f -name '$(NAME)-$(VERSION)-*.src.rpm' -print | sort); \
	[[ "$${#srpms[@]}" -eq 1 ]] || { echo "ERROR: expected exactly one current SRPM, found $${#srpms[@]}." >&2; exit 1; }; \
	top="$$(mktemp -d)"; trap 'rm -rf "$$top"' EXIT; \
	mkdir -p "$$top"/{BUILD,BUILDROOT,RPMS,SOURCES,SPECS,SRPMS}; \
	CARGO_NET_OFFLINE=true rpmbuild --define "_topdir $$top" --rebuild "$${srpms[0]}"; \
	mapfile -t rebuilt_rpms < <(find "$$top/RPMS" -type f -name '*.rpm' -print | sort); \
	[[ "$${#rebuilt_rpms[@]}" -gt 0 ]] || { echo 'ERROR: isolated SRPM rebuild produced no binary RPMs.' >&2; exit 1; }; \
	rm -f '$(DISTDIR)'/*.x86_64.rpm '$(DISTDIR)'/*.noarch.rpm; \
	cp -f "$${rebuilt_rpms[@]}" '$(DISTDIR)/'; \
	echo "Authoritative SRPM rebuild published $${#rebuilt_rpms[@]} binary RPM(s) from SRPM: $$(basename "$${srpms[0]}")"; \
	printf '  %s\n' "$${rebuilt_rpms[@]##*/}"

check-rpmlint:
	@set +e; \
	report='$(BUILD_DIR)/rpmlint-report.txt'; \
	rpmlint -c '$(FROZEN_SOURCE_DIR)/packaging/rpmlint.toml' $(DISTDIR)/*.rpm >"$$report" 2>&1; rc=$$?; \
	cat "$$report"; \
	if ((rc != 0)); then echo "rpmlint: FAIL (blocking, rc=$$rc)" >&2; exit "$$rc"; fi; \
	echo 'rpmlint: PASS'

release-gate-preflight:
	$(MAKE) clean
	$(TIME_STAGE) preflight-static $(MAKE) lint
	$(TIME_STAGE) preflight $(MAKE) preflight
	$(TIME_STAGE) prepare-sources $(MAKE) sources
	$(TIME_STAGE) source-check $(MAKE) sources-check
	$(TIME_STAGE) freeze-source0 $(MAKE) freeze-rpm-inputs
	$(TIME_STAGE) check-frozen-inputs $(MAKE) check-frozen-source

release-gate-package:
	$(TIME_STAGE) rpmbuild-bs $(MAKE) -C '$(FROZEN_SOURCE_DIR)' \
	  BUILD_DIR='$(BUILD_DIR)' TOPDIR='$(TOPDIR)' DISTDIR='$(DISTDIR)' SOURCE_CACHE_DIR='$(SOURCE_CACHE_DIR)' \
	  RPM_TREE_TARGET=rpm-tree-frozen srpm </dev/null
	$(TIME_STAGE) authoritative-srpm-rebuild $(MAKE) -C '$(FROZEN_SOURCE_DIR)' \
	  BUILD_DIR='$(BUILD_DIR)' TOPDIR='$(TOPDIR)' DISTDIR='$(DISTDIR)' SOURCE_CACHE_DIR='$(SOURCE_CACHE_DIR)' \
	  rebuild-srpm
	$(TIME_STAGE) payload-check $(MAKE) -C '$(FROZEN_SOURCE_DIR)' \
	  BUILD_DIR='$(BUILD_DIR)' TOPDIR='$(TOPDIR)' DISTDIR='$(DISTDIR)' SOURCE_CACHE_DIR='$(SOURCE_CACHE_DIR)' \
	  check-rpm-payload
	$(TIME_STAGE) rpmlint $(MAKE) \
	  BUILD_DIR='$(BUILD_DIR)' TOPDIR='$(TOPDIR)' DISTDIR='$(DISTDIR)' SOURCE_CACHE_DIR='$(SOURCE_CACHE_DIR)' \
	  check-rpmlint
	$(TIME_STAGE) release-evidence $(MAKE) -C '$(FROZEN_SOURCE_DIR)' \
	  BUILD_DIR='$(BUILD_DIR)' TOPDIR='$(TOPDIR)' DISTDIR='$(DISTDIR)' SOURCE_CACHE_DIR='$(SOURCE_CACHE_DIR)' \
	  release-evidence

release-gate:
	$(MAKE) release-gate-preflight
	$(MAKE) release-gate-package

clean:
	rm -rf $(BUILD_DIR) $(DISTDIR) $(TOPDIR)

clean-sources:
	rm -f $(SOURCE_CACHE_DIR)/*.tar.gz $(SOURCE_CACHE_DIR)/*.tar.xz $(SOURCE_CACHE_DIR)/*.sha256

distclean: clean clean-sources
