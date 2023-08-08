.PHONY: confignator ccs-storage codeblockreusefeature install-testlib python-requirements db-user database-dev-env databases startmenu-entries

install: python-requirements confignator ccs-storage codeblockreusefeature startmenu-entries

databases: ccs-storage codeblockreusefeature

db-user:
	sudo ./mk_mysql_user.sh $(USER) $(PW)

python-requirements:
	@echo "+-----------------------------+"
	@echo "| installing Python modules   |"
	@echo "+-----------------------------+"
		if [ -z $(VIRTUAL_ENV) ]; then pip install --user --break-system-packages -U -r $(CURDIR)/requirements.txt; else pip install -U -r $(CURDIR)/requirements.txt; fi
	@echo "+-----------------------------+"
	@echo "| installed Python modules    |"
	@echo "+-----------------------------+"
	@echo

confignator:
	@echo "+---------------------------------------+"
	@echo "| installing confignator Python package |"
	@echo "+---------------------------------------+"
		$(MAKE) build -C $(CURDIR)/Tst/confignator
	    if [ -z $(VIRTUAL_ENV) ]; then pip install --user --break-system-packages -U --force-reinstall $(CURDIR)/Tst/confignator/dist/*.whl; else pip install -U --force-reinstall $(CURDIR)/Tst/confignator/dist/*.whl; fi
		$(MAKE) build-doc -C $(CURDIR)/Tst/confignator
	@echo "+--------------------------------------+"
	@echo "| installed confignator Python package |"
	@echo "+--------------------------------------+"
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

database-dev-env:
	@echo "+---------------------------------------------------+"
	@echo "| installing Python dev packages for the database   |"
	@echo "+---------------------------------------------------+"
	    $(MAKE) install-devenv -C $(CURDIR)/Ccs/database
	@echo "+---------------------------------------------------+"
	@echo "| installed Python dev packages for the database    |"
	@echo "+---------------------------------------------------+"
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

startmenu-entries:
	@echo "+-----------------------------------+"
	@echo "| creating application menu entries |"
	@echo "+-----------------------------------+"
	    ./gen_desktop_files.sh $(CURDIR)
	    mv ccs.desktop $(HOME)/.local/share/applications/
	    mv tst.desktop $(HOME)/.local/share/applications/
	@echo "+----------------------------------+"
	@echo "| created application menu entries |"
	@echo "+----------------------------------+"
	@echo

set-start-scripts-permissions:
	@echo "+-----------------------------------------------------+"
	@echo "| setting permissions for the start scripts (execute) |"
	@echo "+-----------------------------------------------------+"
	    $(MAKE) all -C $(CURDIR)/Tst/

