.PHONY: install-confignator ccs-storage codeblockreusefeature install-testlib

# all: install install-database-dev-env

install: install-python-requirements install-confignator ccs-storage codeblockreusefeature

databases: ccs-storage codeblockreusefeature

install-confignator:
	@echo "+---------------------------------------+"
	@echo "| installing confignator Python package |"
	@echo "+---------------------------------------+"
		$(MAKE) build -C $(CURDIR)/Tst/confignator
	    if [ -z $VIRTUAL_ENV ]; then pip install --user -U --force-reinstall $(CURDIR)/Tst/confignator/dist/*.whl; else pip install -U --force-reinstall $(CURDIR)/Tst/confignator/dist/*.whl; fi
		$(MAKE) build-doc -C $(CURDIR)/Tst/confignator
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

install-python-requirements:
	@echo "+-----------------------------+"
	@echo "| installing Python modules   |"
	@echo "+-----------------------------+"
		if [ -z $VIRTUAL_ENV ]; then pip install --user -U -r $(CURDIR)/requirements.txt; else pip install -U -r $(CURDIR)/requirements.txt; fi
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
