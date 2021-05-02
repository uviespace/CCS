all:	check coverage

check:
	cd .. ; flake8 database/tm_db.py
	cd .. ; pylint -E database/tm_db.py
	cd .. ; pylint -E database/test_db.py
#	cd .. ; MYPYPATH=~/.local/lib/python3.7/site-packages/ mypy -s database/tm_db.py database/test_db.py

run:
	cd .. ; python3 -m database.tm_db

verbose:
	cd .. ; python3 -m database.tm_db -v

debug:
	cd .. ; python3 -m database.tm_db -v -pdb

coverage:
	bash -c '[ ! -z "$$DISPLAY" ] && \
	    { py.test --verbose -s --cov=. --cov-report html && firefox htmlcov/index.html ; } || \
	    py.test --verbose -s --cov=.'

install-devenv:
	pip3 install --user --upgrade pylint
	pip3 install --user --upgrade mypy
	pip3 install --user --upgrade pyflakes
	pip3 install --user --upgrade flake8
	pip3 install --user --upgrade ipdb
	pip3 install --user --upgrade pytest
	pip3 install --user --upgrade pytest-cov

clean:
	rm -rf __pycache__/ .cache/ .coverage htmlcov/

.PHONY:	clean install-devenv coverage debug verbose run check
