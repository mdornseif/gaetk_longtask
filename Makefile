GAE_VERSION=1.6.2

# pyLint
#   W0142 = *args and **kwargs support
# Pointless whinging
#   W0603 = Using the global statement
#   R0201 = Method could be a function
#   W0212 = Accessing protected attribute of client class
#   W0232 = Class has no __init__ method
#   W0212 = Access to a protected member _rev of a client class
# Mistakes in Parsing the AppEngine Source
#   E1103: %s %r has no %r member (but some types could not be inferred)
# Usually makes sense for webapp.Handlers & Friends.
#   W0221 Arguments number differs from %s method
# In Python versions < 2.6 all Exceptions inherited from Exception. py2.6 introduced BaseException
# On AppEngine we do not care much about the "serious" Exception like KeyboardInterrupt etc.
#   W0703 Catch "Exception"
#   R0903 Too few public methods - pointless for db.Models
# Unused Reports
#   RP0401 External dependencies
#   RP0402 Modules dependencies graph
#   RP0101 Statistics by type
#   RP0701 Raw metrics

GOOD_NAMES=gaetk_LongTask

PYLINT_ARGS= --output-format=parseable -rn -iy --ignore=config.py \
             --deprecated-modules=regsub,string,TERMIOS,Bastion,rexec,husoftm \
             --max-public-methods=25 \
             --max-line-length=110 \
             --min-similarity-lines=6 \
             --disable=I0011,W0201,W0142,W0603,W0403,R0201,W0212,W0232,W0212,E1103,W0221,W0703,W0404 \
             --disable=RP0401,RP0402,RP0101,RP0701,RP0801 \
             --ignored-classes=Struct,Model,google.appengine.api.memcache \
             --dummy-variables-rgx="_|dummy|abs_url" \
             --good-names=_,setUp,fd,application,$(GOOD_NAMES) \
             --generated-members=request,response

PYLINT_FILES= longtask/

check: lib/google_appengine/google/__init__.py checknodeps

checknodeps:
	@# pyflakes & pep8
	pep8 -r --ignore=E501 $(PYLINT_FILES)
	pyflakes $(PYLINT_FILES)
	@# der erste Durchlauf zeigt alle Probleme inkl. TODOs an
	-sh -c 'PYTHONPATH=lib/google_appengine/:lib/google_appengine/lib/webob/:lib/google_appengine/lib/webapp2/ pylint $(PYLINT_ARGS) $(PYLINT_FILES)'
	@# im zweiten Durchlauf werden alle Nicht-TODOs als Fehler ausgegeben und verhindern ein Deployment
	@echo "----------------------------------------------------------------"
	@sh -c 'PYTHONPATH=lib/google_appengine/:lib/google_appengine/lib/webob/:lib/google_appengine/lib/webapp2/ pylint $(PYLINT_ARGS) $(PYLINT_FILES)'
	# clonedigger *.py modules/ lib/CentralServices/ lib/gaetk/ lib/huTools lib/huSoftM

# Install AppEngine SDK locally so pyLint und pyFlakes find it
lib/google_appengine/google/__init__.py:
	curl -s -O http://googleappengine.googlecode.com/files/google_appengine_$(GAE_VERSION).zip
	unzip -q google_appengine_$(GAE_VERSION).zip
	mkdir -p lib/
	rm -Rf lib/google_appengine
	mv google_appengine lib/
	rm google_appengine_$(GAE_VERSION).zip

dependencies: clean
	git submodule update --init

.PHONY: clean check 
