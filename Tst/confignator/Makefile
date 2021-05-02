CONFIGNATOR_CFG = $(CURDIR)/confignator/confignator.cfg
BASIC_CONFI_CFG = $(PWD)/egse.cfg
BASIC_PATH = $(PWD)
DOCU_INDEX_HTML = $(CURDIR)/doc/build/html/index.html
DOC_SRC = "confignator/"
DOC_DST = "doc/source/_apidocfiles/"
DOC_OPEN = $(CURDIR)/confignator/open_doc.py
DIST_DIR = $(CURDIR)/dist

.PHONY: build clean-build install uninstall reinstall build-doc clean-doc-build all open-doc

all: clean build install set-log-file-path build-doc open-doc

doc: clean-doc-build build-doc

clean: clean-build clean-doc-build

reinstall: clean uninstall build install

build:
	@echo "\e[1m=====================================\e[0m"
	@echo "\e[1m building confignator Python package \e[0m"
	@echo "\e[1m=====================================\e[0m"
		# remove the last file containing the path to the configuration file
		rm -f $(CONFIGNATOR_CFG)
		# create the new file containing the path to the configuration file
		@echo "# This is the configuration file for the confignator and is a generated file, created during the installation of the confignator package." >> $(CONFIGNATOR_CFG)
		@echo "# Modifications have to be done in the Makefile of the confignator package and a reinstall of it is needed!\n" >> $(CONFIGNATOR_CFG)
		@echo "[confignator-paths]" >> $(CONFIGNATOR_CFG)
		@echo "basic-path = $(BASIC_PATH)" >> $(CONFIGNATOR_CFG)
		@echo "basic-cfg = $(BASIC_CONFI_CFG)" >> $(CONFIGNATOR_CFG)
		@echo "docu = $(DOCU_INDEX_HTML)" >> $(CONFIGNATOR_CFG)
		@echo "log-file = ''\n" >> $(CONFIGNATOR_CFG)
		# build the Python package
		# python3 setup.py sdist;
		python3 setup.py bdist_wheel
		rm -f $(CONFIGNATOR_CFG)
	@echo "\e[1m\e[32m==================================\e[0m"
	@echo "\e[1m\e[32m built confignator Python package \e[0m"
	@echo "\e[1m\e[32m==================================\e[0m"
	@echo

clean-build:
	@echo "\e[1m=============================================================\e[0m"
	@echo "\e[1m deleting Python package folders and generated documentation \e[0m"
	@echo "\e[1m=============================================================\e[0m"
		rm -f $(CONFIGNATOR_CFG)
		rm -rf ./build
		rm -rf ./confignator.egg-info
	@echo "\e[1m\e[32m============================================================\e[0m"
	@echo "\e[1m\e[32m deleted Python package folders and generated documentation \e[0m"
	@echo "\e[1m\e[32m============================================================\e[0m"
	@echo

install:
	@echo "\e[1m=================================\e[0m"
	@echo "\e[1m installing confignator with pip \e[0m"
	@echo "\e[1m=================================\e[0m"
		pip3 install --user $(DIST_DIR)/*.whl
	@echo "\e[1m\e[32m================================\e[0m"
	@echo "\e[1m\e[32m installed confignator with pip \e[0m"
	@echo "\e[1m\e[32m================================\e[0m"
	@echo

set-log-file-path:
	@echo "\e[1m=========================================================================\e[0m"
	@echo "\e[1m setting the path of the confignator into the its own configuration file \e[0m"
	@echo "\e[1m=========================================================================\e[0m"
		cd ..; \
		python3 -c "import confignator; confignator.set_own_log_file_path()"
	@echo "\e[1m\e[32m====================================================================================\e[0m"
	@echo "\e[1m\e[32m setting the path of the confignator into its own configuration file was successful \e[0m"
	@echo "\e[1m\e[32m====================================================================================\e[0m"
	@echo

uninstall:
	@echo "\e[1m===================================\e[0m"
	@echo "\e[1m uninstalling confignator with pip \e[0m"
	@echo "\e[1m===================================\e[0m"
	pip3 uninstall confignator
	@echo "\e[1m\e[32m==================================\e[0m"
	@echo "\e[1m\e[32m uninstalled confignator with pip \e[0m"
	@echo "\e[1m\e[32m==================================\e[0m"
	@echo

clean-doc-build:
	@echo "\e[1m==============================\e[0m"
	@echo "\e[1m deleting documentation build \e[0m"
	@echo "\e[1m==============================\e[0m"
	rm -rf ./doc/build
	rm -rf ./doc/source/_apidocfiles
	mkdir -p ./doc/source/_static
	mkdir -p ./doc/source/_apidocfiles
	@echo "\e[1m\e[32m=============================\e[0m"
	@echo "\e[1m\e[32m deleted documentation build \e[0m"
	@echo "\e[1m\e[32m=============================\e[0m"

build-doc:
	@echo "\e[1m=======================\e[0m"; \
	echo "\e[1m Running sphinx apidoc \e[0m"; \
	echo "\e[1m=======================\e[0m"; \
	sphinx-apidoc --separate -f -e -d 10 --implicit-namespaces -o $(DOC_DST) $(DOC_SRC); \
	if [ $$? -eq 0 ]; then \
		echo "\e[32mSuccessful ran command sphinx-apidoc on folder:"; \
		echo "'$(DOC_SRC)' \e[0m"; \
		echo "\e[1m\e[32m================================\e[0m"; \
		echo "\e[1m\e[32m Successfully ran sphinx-apidoc \e[0m"; \
		echo "\e[1m\e[32m================================\e[0m"; \
	else \
		echo "\e[1m\e[31mFAILED\e[0m to run command sphinx-apidoc on folder '$(DOC_SRC)' \e[0m"; \
		echo "\e[1m\e[31m==============================\e[0m"; \
		echo "\e[1m\e[31m Failed running sphinx apidoc \e[0m"; \
		echo "\e[1m\e[31m==============================\e[0m"; \
	fi;

	@echo ""

	@echo "\e[1m==========================\e[0m"; \
	echo "\e[1m Running sphinx make HTML \e[0m"; \
	echo "\e[1m==========================\e[0m"; \
	cd doc; \
	make html; \
	if [ $$? -eq 0 ]; then \
		echo "\e[1m\e[32m===================================\e[0m"; \
		echo "\e[1m\e[32m Successfully ran sphinx make HTML \e[0m"; \
		echo "\e[1m\e[32m===================================\e[0m"; \
	else \
		echo "\e[1m\e[31m=================================\e[0m"; \
		echo "\e[1m\e[31m Failed running sphinx make HTML \e[0m"; \
		echo "\e[1m\e[31m=================================\e[0m"; \
	fi

open-doc:
	@echo "\e[1m=====================================\e[0m"; \
	echo "\e[1m Opening the documentation in firefox \e[0m"; \
	echo "\e[1m======================================\e[0m"; \
		cd ..; \
		python3 -c "import confignator; confignator.documentation()" &
