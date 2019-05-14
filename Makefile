.PHONY: all checkdist clean sdist test uploadtest upload

all: ;

checkdist: sdist
	twine check dist/*

clean:
	rm -fr ./dist

sdist:
	python3 setup.py sdist bdist_wheel

test:
	py.test sshkernel tests/unit --disable-pytest-warnings

uploadtest: sdist checkdist
	python3 -m twine upload --repository-url https://test.pypi.org/legacy/ dist/*

upload: test sdist checkdist
	python3 -m twine upload dist/*