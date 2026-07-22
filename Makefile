SHELL := /bin/bash
NAME := bc250-llm-server
VERSION := $(shell cat VERSION)
TOPDIR := $(CURDIR)/rpmbuild
DISTDIR := $(CURDIR)/dist
RPMDIR := $(DISTDIR)/RPMS
SRPMDIR := $(DISTDIR)/SRPMS
UPSTREAM_SOURCES := $(shell ./scripts/prepare-sources.py --print-files)

.PHONY: help sources sources-check source-tar rpm-tree srpm rpm validate clean clean-sources distclean

help:
	@printf '%s\n' \
	  'make sources    Download pinned governor and CU-tool sources' \
	  'make sources-check  Check the local source cache without downloading' \
	  'make validate   Run deterministic RPM preflight checks' \
	  'make source-tar Create the project source archive' \
	  'make srpm       Build the source RPM' \
	  'make rpm        Build binary and source RPMs' \
	  'make clean      Remove disposable build output; keep downloaded sources' \
	  'make clean-sources  Remove the reusable third-party source cache'

sources:
	./scripts/prepare-sources.py

sources-check:
	./scripts/prepare-sources.py --check

source-tar:
	./scripts/make-source-tarball.sh

validate:
	./scripts/validate.sh

rpm-tree: sources source-tar validate
	mkdir -p $(TOPDIR)/{BUILD,BUILDROOT,RPMS,SOURCES,SPECS,SRPMS} $(RPMDIR) $(SRPMDIR)
	cp build/$(NAME)-$(VERSION).tar.gz $(TOPDIR)/SOURCES/
	cp $(UPSTREAM_SOURCES) $(TOPDIR)/SOURCES/
	cp packaging/$(NAME).spec $(TOPDIR)/SPECS/

srpm: rpm-tree
	rpmbuild --define '_topdir $(TOPDIR)' -bs $(TOPDIR)/SPECS/$(NAME).spec
	cp -f $(TOPDIR)/SRPMS/*.src.rpm $(SRPMDIR)/
	cd $(DISTDIR) && sha256sum SRPMS/*.src.rpm > SHA256SUMS

rpm: rpm-tree
	rpmbuild --define '_topdir $(TOPDIR)' -ba $(TOPDIR)/SPECS/$(NAME).spec
	find $(TOPDIR)/RPMS -type f -name '*.rpm' -exec cp -f {} $(RPMDIR)/ \;
	find $(TOPDIR)/SRPMS -type f -name '*.src.rpm' -exec cp -f {} $(SRPMDIR)/ \;
	rpm -qpl $(RPMDIR)/$(NAME)-$(VERSION)-*.x86_64.rpm | grep -qx /usr/bin/bc250-install-ollama
	cd $(DISTDIR) && sha256sum RPMS/*.rpm SRPMS/*.src.rpm > SHA256SUMS

clean:
	rm -rf build dist rpmbuild

clean-sources:
	rm -f sources/*.tar.gz sources/*.tar.xz

distclean: clean clean-sources
