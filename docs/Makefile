# Minimal makefile for Sphinx documentation
#

# You can set these variables from the command line.
SPHINXOPTS      = -E
AUTOBUILDOPTS   = -j auto
SPHINXBUILD     = python -m sphinx
SOURCEDIR       = ./
BUILDDIR        = build
AUTOBUILDDIR    = build
SPHINXAUTOBUILD = sphinx-autobuild

export PYTHONPATH=${PWD}/../
# echo $PYTHONPATH

# Put it first so that "make" without argument is like "make help".
help:
	@$(SPHINXBUILD) -M help "$(SOURCEDIR)" "$(BUILDDIR)" $(SPHINXOPTS) $(O)


serve:
	sphinx-autobuild -b html "$(SOURCEDIR)" "$(AUTOBUILDDIR)" $(AUTOBUILDOPTS) --open-browser --delay 1 $(O)


buildapi:
	sphinx-apidoc -e -M -d 5 -o source/rst/ ../autopilot/
	# for f in source/rst/*.rst; do\
	# 	perl -pi -e 's/(module|package)$$// if $$. == 1' $$f ;\
	# done

# Catch-all target: route all unknown targets to Sphinx using the new
# "make mode" option.  $(O) is meant as a shortcut for $(SPHINXOPTS).
%: Makefile
	@$(SPHINXBUILD) -M $@ "$(SOURCEDIR)" "$(BUILDDIR)" $(SPHINXOPTS) $(O)
	cp _images/* $(BUILDDIR)/html/_images/
	#rsync -av $(BUILDDIR)/html/* ./ --remove-source-files

