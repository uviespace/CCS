.PHONY: install-confignator install-testlib set-start-scripts-permissions build-pc build-fw-profile build-crplm build-cria

all: install build-pc

install: install-confignator install-testlib set-start-scripts-permissions

databases: ccs-storage codeblockreusefeature

build-pc: build-fw-profile build-crplm build-cria build-crfee

install-confignator:
	@echo "+-----------------------------------------------+"
	@echo "| installing confignator Python package |"
	@echo "+-----------------------------------------------+"
	    $(MAKE) all -C $(CURDIR)/Tst/confignator
	@echo "+-----------------------------------------------+"
	@echo "| installed confignator Python package |"
	@echo "+-----------------------------------------------+"
	@echo

install-testlib:
	@echo "+-----------------------------------------------+"
	@echo "| installing testlib Python package |"
	@echo "+-----------------------------------------------+"
	    $(MAKE) all -C $(CURDIR)/Tst/testing_library
	@echo "+-----------------------------------------------+"
	@echo "| installed testlib Python package |"
	@echo "+-----------------------------------------------+"
	@echo

install-database-dev-env:
	@echo "+-----------------------------------------------+"
	@echo "| installing Python packages for the database   |"
	@echo "+-----------------------------------------------+"
	    $(MAKE) install-devenv -C $(CURDIR)/Ccs/database
	@echo "+-----------------------------------------------+"
	@echo "| installed Python packages for the database    |"
	@echo "+-----------------------------------------------+"
	@echo

ccs-storage:
	@echo "+----------------------------------------+"
	@echo "| setting up the storage database schema |"
	@echo "+----------------------------------------+"
	    $(MAKE) storage -C $(CURDIR)/Ccs/database
	@echo "+--------------------------------------------+"
	@echo "| set up of the storage database schemas done|"
	@echo "+--------------------------------------------+"
	@echo

codeblockreusefeature:
	@echo "+-----------------------------------------------+"
	@echo "| setting up the codeblockreuse database schema |"
	@echo "+-----------------------------------------------+"
	    $(MAKE) schema -C $(CURDIR)/Tst/codeblockreusefeature
	@echo "+---------------------------------------------------+"
	@echo "| set up of the codeblockreuse database schemas done|"
	@echo "+---------------------------------------------------+"
	@echo

set-start-scripts-permissions:
	@echo "+-----------------------------------------------------+"
	@echo "| setting permissions for the start scripts (execute) |"
	@echo "+-----------------------------------------------------+"
	    $(MAKE) all -C $(CURDIR)/Tst/
