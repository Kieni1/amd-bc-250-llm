SHELL := /bin/bash
NAME := bc250-llm-server
VERSION := $(shell cat VERSION)
TOPDIR := $(CURDIR)/rpmbuild
DISTDIR := $(CURDIR)/dist

GOV_COMMIT := 60ab6e5b354f01f287c73d920990dcd618a674cc
GOV_SOURCE := sources/cyan-skillfish-governor-$(GOV_COMMIT).tar.gz
GOV_VENDOR := sources/cyan-skillfish-governor-vendor-$(GOV_COMMIT).tar.xz

UNLOCK_COMMIT := 6c3969ddee40e894297869e6ca30537f274619cb
UNLOCK_SOURCE := sources/bc250-40cu-unlock-$(UNLOCK_COMMIT).tar.gz

.PHONY: help sources source-tar srpm rpm validate clean

help:
	@printf '%s\n' \
	  'make sources    Download pinned governor and 40-CU sources' \
	  'make validate   Run repository checks' \
	  'make source-tar Create the project source archive' \
	  'make srpm       Build the source RPM' \
	  'make rpm        Build binary and source RPMs' \
	  'make clean      Remove generated build output and source archives'

sources:
	./scripts/prepare-governor-sources.sh
	./scripts/prepare-40cu-source.sh

source-tar:
	./scripts/make-source-tarball.sh

validate:
	./scripts/validate.sh

srpm: sources source-tar validate
	mkdir -p $(TOPDIR)/{BUILD,BUILDROOT,RPMS,SOURCES,SPECS,SRPMS} $(DISTDIR)
	cp build/$(NAME)-$(VERSION).tar.gz $(TOPDIR)/SOURCES/
	cp $(GOV_SOURCE) $(GOV_VENDOR) $(UNLOCK_SOURCE) $(TOPDIR)/SOURCES/
	cp packaging/$(NAME).spec $(TOPDIR)/SPECS/
	rpmbuild --define '_topdir $(TOPDIR)' -bs $(TOPDIR)/SPECS/$(NAME).spec
	cp -f $(TOPDIR)/SRPMS/*.src.rpm $(DISTDIR)/

rpm: sources source-tar validate
	mkdir -p $(TOPDIR)/{BUILD,BUILDROOT,RPMS,SOURCES,SPECS,SRPMS} $(DISTDIR)
	cp build/$(NAME)-$(VERSION).tar.gz $(TOPDIR)/SOURCES/
	cp $(GOV_SOURCE) $(GOV_VENDOR) $(UNLOCK_SOURCE) $(TOPDIR)/SOURCES/
	cp packaging/$(NAME).spec $(TOPDIR)/SPECS/
	rpmbuild --define '_topdir $(TOPDIR)' -ba $(TOPDIR)/SPECS/$(NAME).spec
	find $(TOPDIR)/RPMS $(TOPDIR)/SRPMS -type f -name '*.rpm' -exec cp -f {} $(DISTDIR)/ \;
	cd $(DISTDIR) && sha256sum *.rpm > SHA256SUMS

clean:
	rm -rf build dist rpmbuild
	rm -f sources/*.tar.gz sources/*.tar.xz sources/*.sha256
