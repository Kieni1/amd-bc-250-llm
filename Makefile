SHELL := /bin/bash
export LANG := C
export LC_ALL := C
NAME := bc250-llm-server
VERSION := $(shell cat VERSION)
BUILD_DIR ?= $(CURDIR)/build
TOPDIR ?= $(CURDIR)/rpmbuild
DISTDIR ?= $(CURDIR)/dist
SOURCE_CACHE_DIR ?= $(CURDIR)/sources
GFX_CACHE_DIR ?= $(SOURCE_CACHE_DIR)/gfx1013
BC250_SOURCE_DIR ?= $(SOURCE_CACHE_DIR)
BC250_GFX1013_CACHE_ROOT ?= $(GFX_CACHE_DIR)
BC250_BUILD_DIR ?= $(BUILD_DIR)
PYTHONDONTWRITEBYTECODE ?= 1
export BC250_SOURCE_DIR BC250_GFX1013_CACHE_ROOT BC250_BUILD_DIR PYTHONDONTWRITEBYTECODE
RPM_TREE_TARGET ?= rpm-tree
FROZEN_SPEC := $(BUILD_DIR)/$(NAME).spec
FROZEN_INPUTS := $(BUILD_DIR)/RPM-INPUTS.sha256
FROZEN_SOURCE_PARENT := $(BUILD_DIR)/frozen-source
FROZEN_SOURCE_DIR := $(FROZEN_SOURCE_PARENT)/$(NAME)-$(VERSION)
UPSTREAM_SOURCES := $(shell ./scripts/prepare-sources.py --print-files)

.PHONY: help sources sources-check gfx1013-kernel-builddeps gfx1013-kernel-build-check gfx1013-mesa-build-check lint source-tar freeze-rpm-inputs check-frozen-source preflight validate prepare-rpm-output rpm-tree rpm-tree-prevalidated rpm-tree-frozen srpm rpm artifact-manifests check-rpm-payload check-srpm-rebuild release-gate-preflight release-gate-postprovision release-gate release-diagnostics clean clean-sources distclean

help:
	@printf '%s\n' \
	  'make sources    Download pinned governor and live-manager sources' \
	  'make sources-check  Verify the local source cache and SHA-256 sidecars' \
	  'make gfx1013-kernel-builddeps  Provision exact Fedora kernel SRPM BuildRequires as root' \
	  'make gfx1013-kernel-build-check  Build and ABI-check patched amdgpu against Fedora kernel-devel' \
	  'make gfx1013-mesa-build-check  Build the pinned private headless RADV in staging' \
	  'make lint       Run Ruff and ShellCheck' \
	  'make preflight  Run cheap source checks plus host release-pipeline contracts' \
	  'make validate   Run preflight plus deterministic tests' \
	  'make source-tar Create the project source archive' \
	  'make freeze-rpm-inputs  Freeze validated source tar/spec before heavy release work' \
	  'make check-frozen-source  Run package contracts from the exact frozen source tarball' \
	  'make srpm       Build the source RPM' \
	  'make rpm        Build binary and source RPMs' \
	  'make artifact-manifests  Create closed binary/source checksum manifests' \
	  'make check-rpm-payload  Verify the built greenfield RPM file surface' \
	  'make check-srpm-rebuild  Rebuild the generated SRPM from a clean temporary topdir' \
	  'make release-gate-preflight  Run cheap fail-fast release checks before privileged/heavy work' \
	  'make release-gate-postprovision  Run exact GFX builds, RPM checks and SRPM self-contained rebuild' \
	  'make release-gate  Run both release phases when dependencies are already provisioned' \
	  'make release-diagnostics  Run independent release checks and retain all failure logs' \
	  'make clean      Remove disposable build output; keep downloaded sources' \
	  'make clean-sources  Remove the reusable third-party source cache'

sources:
	./scripts/prepare-sources.py
	./scripts/check-gfx1013-mesa.py --fetch
	./scripts/check-upstream-patches.py

sources-check:
	./scripts/prepare-sources.py --check
	./scripts/check-gfx1013-mesa.py
	./scripts/check-upstream-patches.py

gfx1013-kernel-builddeps:
	./scripts/provision-gfx1013-kernel-builddeps.sh

gfx1013-kernel-build-check:
	./scripts/check-gfx1013-kernel-build.sh

gfx1013-mesa-build-check:
	@set -Eeuo pipefail; \
	tmp="$$(mktemp -d)"; trap 'rm -rf "$$tmp"' EXIT; \
	mkdir -p "$$tmp/work"; \
	BC250_GFX1013_LIBRARY_ONLY=1 \
	BC250_GFX1013_SOURCE='$(CURDIR)/gfx1013/upstream' \
	BC250_GFX1013_CACHE_ROOT='$(GFX_CACHE_DIR)' \
	BC250_GFX1013_PREFIX_ROOT=/opt/bc250-gfx1013-ci \
	bash -Eeuo pipefail -c 'source "$$1/cmd/system/gfx1013.sh"; build_mesa "$$2/work" "$$2/stage" "$$2/mesa-info"; prefix="$$2/stage$$(private_prefix)"; test -f "$$prefix/lib64/libvulkan_radeon.so"; test -f "$$prefix/share/vulkan/icd.d/radeon_icd.x86_64.json"; test "$$(find "$$prefix" \( -type f -o -type l \) | wc -l)" -eq 2' \
	  bash '$(CURDIR)' "$$tmp"; \
	echo 'Headless private RADV build check passed.'

lint:
	ruff check .
	@set -Eeuo pipefail; \
	while IFS= read -r file; do \
	  if head -n1 "$$file" | grep -qE '^#!.*[ /](ba)?sh([[:space:]]|$$)'; then \
	    shellcheck --severity=error "$$file"; \
	  fi; \
	done < <(find . -type f \
	  -not -path './sources/*' -not -path './build/*' -not -path './.build/*' \
	  -not -path './governor-src/*' -not -path './live-manager-src/*')

source-tar:
	./scripts/make-source-tarball.sh

freeze-rpm-inputs: source-tar
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
	  echo 'ERROR: spec embedded in the frozen source archive differs from the frozen RPM spec.' >&2; exit 1; \
	}; \
	cd "$$src"; \
	env -u BC250_BUILD_DIR -u BC250_SOURCE_DIR -u BC250_GFX1013_CACHE_ROOT \
	  PYTHONDONTWRITEBYTECODE=1 bash scripts/validate.sh --package </dev/null; \
	echo 'Frozen source package validation passed.'

preflight:
	./scripts/validate.sh --preflight

validate:
	./scripts/validate.sh

prepare-rpm-output:
	rm -rf $(TOPDIR)
	mkdir -p $(DISTDIR)
	rm -f $(DISTDIR)/*.rpm $(DISTDIR)/*.src.rpm $(DISTDIR)/SHA256SUMS $(DISTDIR)/SHA256SUMS.binary $(DISTDIR)/SHA256SUMS.source

define populate-rpm-tree
	mkdir -p $(TOPDIR)/{BUILD,BUILDROOT,RPMS,SOURCES,SPECS,SRPMS} $(DISTDIR)
	cp $(BUILD_DIR)/$(NAME)-$(VERSION).tar.gz $(TOPDIR)/SOURCES/
	cp $(UPSTREAM_SOURCES) $(TOPDIR)/SOURCES/
	cp packaging/$(NAME).spec $(TOPDIR)/SPECS/
endef

rpm-tree: prepare-rpm-output sources source-tar preflight
	$(populate-rpm-tree)

# Orchestrators that have already run sources + preflight can select the
# prevalidated tree. Full release builds use rpm-tree-frozen so the RPM consumes
# the exact source tar/spec snapshot that passed preflight before heavy GFX work.
rpm-tree-prevalidated: prepare-rpm-output source-tar
	$(populate-rpm-tree)

rpm-tree-frozen: prepare-rpm-output
	@cd '$(BUILD_DIR)' && sha256sum -c 'RPM-INPUTS.sha256'
	mkdir -p $(TOPDIR)/{BUILD,BUILDROOT,RPMS,SOURCES,SPECS,SRPMS} $(DISTDIR)
	cp $(BUILD_DIR)/$(NAME)-$(VERSION).tar.gz $(TOPDIR)/SOURCES/
	cp $(UPSTREAM_SOURCES) $(TOPDIR)/SOURCES/
	cp $(FROZEN_SPEC) $(TOPDIR)/SPECS/$(NAME).spec

srpm: rpm-tree
	rpmbuild --define '_topdir $(TOPDIR)' -bs $(TOPDIR)/SPECS/$(NAME).spec
	cp -f $(TOPDIR)/SRPMS/*.src.rpm $(DISTDIR)/
	cd $(DISTDIR) && sha256sum *.src.rpm > SHA256SUMS.source && cp SHA256SUMS.source SHA256SUMS

rpm: $(RPM_TREE_TARGET)
	rpmbuild --define '_topdir $(TOPDIR)' -ba $(TOPDIR)/SPECS/$(NAME).spec
	find $(TOPDIR)/RPMS -type f -name '*.rpm' -exec cp -f {} $(DISTDIR)/ \;
	find $(TOPDIR)/SRPMS -type f -name '*.src.rpm' -exec cp -f {} $(DISTDIR)/ \;
	$(MAKE) check-rpm-payload
	cd $(DISTDIR) && sha256sum *.rpm > SHA256SUMS
	$(MAKE) artifact-manifests

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
	sha256sum -c SHA256SUMS.binary; \
	sha256sum -c SHA256SUMS.source

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
	  /usr/share/bc250-llm-server/gfx1013/upstream/check-kernel-provenance.py \
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
	main_rpm_abs="$$(readlink -f "$$main_rpm")"; \
	(cd "$$extracted" && rpm2cpio "$$main_rpm_abs" | cpio -idm --quiet); \
	gfx_source="$$extracted/usr/share/bc250-llm-server/gfx1013/upstream"; \
	[[ -d "$$gfx_source" ]] || { echo 'ERROR: extracted RPM lacks GFX1013 source payload.' >&2; exit 1; }; \
	(cd "$$gfx_source" && sha256sum -c PATCH-SHA256SUMS && sha256sum -c SOURCE-SHA256SUMS); \
	helper_mode="$$(stat -c '%a' "$$gfx_source/check-kernel-provenance.py")"; \
	[[ "$$helper_mode" == 644 ]] || { echo "ERROR: provenance helper must be installed as non-executable data (0644), got $$helper_mode." >&2; exit 1; }; \
	expected_ollama="$$(sed -n 's/^BC250_OLLAMA_VERSION=//p' config/runtime.env | head -1)"; \
	installed_ollama="$$(sed -n 's/^BC250_OLLAMA_VERSION=//p' "$$extracted/usr/share/bc250-llm-server/runtime.env" | head -1)"; \
	[[ -n "$$expected_ollama" && "$$installed_ollama" == "$$expected_ollama" ]] || { \
	  echo "ERROR: RPM runtime Ollama pin '$$installed_ollama' differs from source '$$expected_ollama'." >&2; exit 1; \
	}; \
	echo "Transformed RPM payload integrity passed: GFX1013 manifests + Ollama $$installed_ollama"; \
	echo "RPM payload contract passed: $$(basename "$$main_rpm")"

check-srpm-rebuild:
	@set -Eeuo pipefail; \
	mapfile -t srpms < <(find '$(DISTDIR)' -maxdepth 1 -type f -name '$(NAME)-$(VERSION)-*.src.rpm' -print | sort); \
	[[ "$${#srpms[@]}" -eq 1 ]] || { echo "ERROR: expected exactly one current SRPM, found $${#srpms[@]}." >&2; exit 1; }; \
	top="$$(mktemp -d)"; trap 'rm -rf "$$top"' EXIT; \
	mkdir -p "$$top"/{BUILD,BUILDROOT,RPMS,SOURCES,SPECS,SRPMS}; \
	CARGO_NET_OFFLINE=true rpmbuild --define "_topdir $$top" --rebuild "$${srpms[0]}"; \
	echo "SRPM self-contained rebuild passed: $$(basename "$${srpms[0]}")"

release-gate-preflight:
	$(MAKE) clean
	$(MAKE) sources
	$(MAKE) lint
	$(MAKE) preflight
	$(MAKE) freeze-rpm-inputs
	$(MAKE) check-frozen-source

release-gate-postprovision:
	@echo 'GFX1013 release validation covers prepare stages 1-6; stage 7 commits device lifecycle state and is device-only.'
	$(MAKE) gfx1013-kernel-build-check
	$(MAKE) gfx1013-mesa-build-check
	$(MAKE) RPM_TREE_TARGET=rpm-tree-frozen rpm </dev/null
	rpmlint -c packaging/rpmlint.toml $(DISTDIR)/*.rpm
	$(MAKE) check-srpm-rebuild

release-gate:
	$(MAKE) release-gate-preflight
	$(MAKE) -C '$(FROZEN_SOURCE_DIR)' BUILD_DIR='$(BUILD_DIR)' TOPDIR='$(TOPDIR)' DISTDIR='$(DISTDIR)' SOURCE_CACHE_DIR='$(SOURCE_CACHE_DIR)' GFX_CACHE_DIR='$(GFX_CACHE_DIR)' release-gate-postprovision


release-diagnostics:
	BC250_RELEASE_BUILD_DIR='$(BUILD_DIR)' \
	BC250_RELEASE_RPM_TOPDIR='$(TOPDIR)' \
	BC250_RELEASE_DISTDIR='$(DISTDIR)' \
	BC250_RELEASE_SOURCE_CACHE='$(SOURCE_CACHE_DIR)' \
	BC250_RELEASE_GFX_CACHE='$(GFX_CACHE_DIR)' \
	./scripts/release-diagnostics.sh

clean:
	rm -rf $(BUILD_DIR) $(DISTDIR) $(TOPDIR)

clean-sources:
	rm -f $(SOURCE_CACHE_DIR)/*.tar.gz $(SOURCE_CACHE_DIR)/*.tar.xz $(SOURCE_CACHE_DIR)/*.sha256
	rm -rf $(GFX_CACHE_DIR)

distclean: clean clean-sources
