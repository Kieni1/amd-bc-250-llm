SHELL := /bin/bash
NAME := bc250-llm-server
VERSION := $(shell cat VERSION)
TOPDIR := $(CURDIR)/rpmbuild
DISTDIR := $(CURDIR)/dist
UPSTREAM_SOURCES := $(shell ./scripts/prepare-sources.py --print-files)

.PHONY: help sources source-tar srpm rpm validate clean

help:
	@printf '%s\n' \
	  'make sources    Download pinned governor and CU-tool sources' \
	  'make validate   Run basic RPM preflight checks' \
	  'make source-tar Create the project source archive' \
	  'make srpm       Build the source RPM' \
	  'make rpm        Build binary and source RPMs' \
	  'make clean      Remove generated build output and source archives'

sources:
	./scripts/prepare-sources.py

source-tar:
	./scripts/make-source-tarball.sh

validate:
	./scripts/validate.sh

srpm: sources source-tar validate
	mkdir -p $(TOPDIR)/{BUILD,BUILDROOT,RPMS,SOURCES,SPECS,SRPMS} $(DISTDIR)
	cp build/$(NAME)-$(VERSION).tar.gz $(TOPDIR)/SOURCES/
	cp $(UPSTREAM_SOURCES) $(TOPDIR)/SOURCES/
	cp packaging/$(NAME).spec $(TOPDIR)/SPECS/
	rpmbuild --define '_topdir $(TOPDIR)' -bs $(TOPDIR)/SPECS/$(NAME).spec
	cp -f $(TOPDIR)/SRPMS/*.src.rpm $(DISTDIR)/

rpm: sources source-tar validate
	mkdir -p $(TOPDIR)/{BUILD,BUILDROOT,RPMS,SOURCES,SPECS,SRPMS} $(DISTDIR)
	cp build/$(NAME)-$(VERSION).tar.gz $(TOPDIR)/SOURCES/
	cp $(UPSTREAM_SOURCES) $(TOPDIR)/SOURCES/
	cp packaging/$(NAME).spec $(TOPDIR)/SPECS/
	rpmbuild --define '_topdir $(TOPDIR)' -ba $(TOPDIR)/SPECS/$(NAME).spec
	find $(TOPDIR)/RPMS $(TOPDIR)/SRPMS -type f -name '*.rpm' -exec cp -f {} $(DISTDIR)/ \;
	cd $(DISTDIR) && sha256sum *.rpm > SHA256SUMS

clean:
	rm -rf build dist rpmbuild
	rm -f sources/*.tar.gz sources/*.tar.xz sources/*.sha256
