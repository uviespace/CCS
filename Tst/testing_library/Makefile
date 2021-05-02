.PHONY: build clean install uninstall reinstall

all: clean build install

build:
	@echo "+-----------------------------------------------+"
	@echo "| building SMILE testing library Python package |"
	@echo "+-----------------------------------------------+"
		python3 setup.py sdist bdist_wheel
	@echo "+-----------------------------------------------+"
	@echo "| built SMILE testing library Python package |"
	@echo "+-----------------------------------------------+"
	@echo

clean:
	@echo "+-------------------------------------------------------+"
	@echo "| deleting SMILE testing library Python package folders |"
	@echo "+-------------------------------------------------------+"
		rm -rf ./build
		rm -rf ./dist
		rm -rf ./testlib.egg-info
	@echo "+------------------------------------------------------+"
	@echo "| deleted SMILE testing library Python package folders |"
	@echo "+------------------------------------------------------+"
	@echo

install:
	@echo "+-------------------------------------------+"
	@echo "| installing SMILE testing library with pip |"
	@echo "+-------------------------------------------+"
		pip3 install --user ./dist/testlib-1.0.0.tar.gz
	@echo "+------------------------------------------+"
	@echo "| installed SMILE testing library with pip |"
	@echo "+------------------------------------------+"
	@echo

uninstall:
	@echo "+---------------------------------------------+"
	@echo "| uninstalling SMILE testing library with pip |"
	@echo "+---------------------------------------------+"
		pip uninstall testlib
	@echo "+--------------------------------------------+"
	@echo "| uninstalled SMILE testing library with pip |"
	@echo "+--------------------------------------------+"
	@echo

