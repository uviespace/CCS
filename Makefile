.PHONY: install-confignator ccs-storage codeblockreusefeature install-testlib

all: install build-pc

install: install-confignator ccs-storage codeblockreusefeature install-testlib

databases: ccs-storage codeblockreusefeature

# build-pc: build-fw-profile build-crplm build-cria build-crfee

install-confignator:
	@echo "+---------------------------------------+"
	@echo "| installing confignator Python package |"
	@echo "+---------------------------------------+"
	    $(MAKE) build -C $(CURDIR)/Tst/confignator
	    pip install -U $(CURDIR)/Tst/confignator/dist/*.whl
	@echo "+--------------------------------------+"
	@echo "| installed confignator Python package |"
	@echo "+--------------------------------------+"
	@echo
	
install-confignator-userspace:
	@echo "+---------------------------------------+"
	@echo "| installing confignator Python package |"
	@echo "+---------------------------------------+"
	    $(MAKE) build -C $(CURDIR)/Tst/confignator
	    pip install --user -U $(CURDIR)/Tst/confignator/dist/*.whl
	@echo "+--------------------------------------+"
	@echo "| installed confignator Python package |"
	@echo "+--------------------------------------+"
	@echo

install-testlib:
	@echo "+-----------------------------------+"
	@echo "| installing testlib Python package |"
	@echo "+-----------------------------------+"
	    $(MAKE) all -C $(CURDIR)/Tst/testing_library
	@echo "+----------------------------------+"
	@echo "| installed testlib Python package |"
	@echo "+----------------------------------+"
	@echo

install-database-dev-env:
	@echo "+---------------------------------------------------+"
	@echo "| installing Python dev packages for the database   |"
	@echo "+---------------------------------------------------+"
	    $(MAKE) install-devenv -C $(CURDIR)/Ccs/database
	@echo "+---------------------------------------------------+"
	@echo "| installed Python dev packages for the database    |"
	@echo "+---------------------------------------------------+"
	@echo
	
install-python-env:
	@echo "+-----------------------------+"
	@echo "| installing Python modules   |"
	@echo "+-----------------------------+"
	    python -m pip install --user --upgrade numpy scipy matplotlib cairocffi mysqlclient sqlalchemy wheel sphinx sphinx_rtd_theme astropy crcmod psutil
	@echo "+-----------------------------+"
	@echo "| installed Python modules    |"
	@echo "+-----------------------------+"
	@echo

install-python-requirements:
	@echo "+-----------------------------+"
	@echo "| installing Python modules   |"
	@echo "+-----------------------------+"
	    pip install -U -r $(CURDIR)/requirements.txt
	@echo "+-----------------------------+"
	@echo "| installed Python modules    |"
	@echo "+-----------------------------+"
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
