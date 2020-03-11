# Minimal makefile for Sphinx documentation
#

# You can set these variables from the command line.
SPHINXOPTS      = -E
SPHINXBUILD     = python -m sphinx
SOURCEDIR       = source
BUILDDIR        = build
AUTOBUILDDIR    = ./
SPHINXAUTOBUILD = sphinx-autobuild

export PYTHONPATH=${PWD}/../
# echo $PYTHONPATH

# Put it first so that "make" without argument is like "make help".
help:
	@$(SPHINXBUILD) -M help "$(SOURCEDIR)" "$(BUILDDIR)" $(SPHINXOPTS) $(O)

.PHONY: help Makefile

serve:
	@$(SPHINXBUILD) -M html "$(SOURCEDIR)" "$(BUILDDIR)" $(SPHINXOPTS) $(O)
# 	@$(SPHINXAUTOBUILD) -b html "$(SOURCEDIR)" "$(AUTOBUILDDIR)" $(SPHINXOPTS) --watch source/changelog --open-browser --delay 1 $(O)
	rsync -av $(BUILDDIR)/html/* ./ --remove-source-files
	# open up the simple node http-server
	http-server
	# open firefox
	#UNAME_S := $(shell uname -s)
	#ifeq ($(UNAME_S),Linux)
    #		/usr/bin/firefox http://127.0.0.1:8080#
	#endif
	#ifeq ($(UNAME_S),Darwin)
	#	open -a firefox -g http://127.0.0.1:8080
	#endif

buildapi:
	sphinx-apidoc -e -M -d 5 -o source/rst/ ../autopilot/
	# for f in source/rst/*.rst; do\
	# 	perl -pi -e 's/(module|package)$$// if $$. == 1' $$f ;\
	# done

# Catch-all target: route all unknown targets to Sphinx using the new
# "make mode" option.  $(O) is meant as a shortcut for $(SPHINXOPTS).
%: Makefile
	@$(SPHINXBUILD) -M $@ "$(SOURCEDIR)" "$(BUILDDIR)" $(SPHINXOPTS) $(O)
	rsync -av $(BUILDDIR)/html/* ./ --remove-source-files

