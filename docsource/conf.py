# Configuration file for the Sphinx documentation builder.
#
# This file only contains a selection of the most common options. For a full
# list see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# -- Path setup --------------------------------------------------------------

# If extensions (or modules to document with autodoc) are in another directory,
# add these directories to sys.path here. If the directory is relative to the
# documentation root, use os.path.abspath to make it absolute, like shown here.
#
# import os
# import re
# import sys


# Verify Import
try:
    import comtrade
except:
    print("Couldn't import `comtrade` module!")
    sys.exit(9)


# -- Project information -----------------------------------------------------

project = 'python-comtrade'
copyright = '2018, David Rodrigues Parrini'
author = 'David Rodrigues Parrini'


# -- General configuration ---------------------------------------------------

# Add any Sphinx extension module names here, as strings. They can be
# extensions coming with Sphinx (named 'sphinx.ext.*') or your custom
# ones.
extensions = [  'sphinx.ext.autodoc',
                'sphinx.ext.napoleon',
                'sphinx.ext.autosummary',
                'numpydoc',
                'sphinx_sitemap',
                'm2r2',
]
autosummary_generate = True
numpydoc_show_class_members = True

# Add any paths that contain templates here, relative to this directory.
templates_path = ['_templates']

# List of patterns, relative to source directory, that match files and
# directories to ignore when looking for source files.
# This pattern also affects html_static_path and html_extra_path.
exclude_patterns = []


# -- Options for HTML output -------------------------------------------------

# The theme to use for HTML and HTML Help pages.  See the documentation for
# a list of builtin themes.
#
html_theme = 'classic'
html_title = 'python-comtrade`'
# html_theme_options = {
    # 'rightsidebar':     'false',
    # 'stickysidebar':    'false',
    # 'collapsiblesidebar': 'false',
    # 'externalrefs':     'false',
    # 'footerbgcolor':    '#08385D',
    # 'footertextcolor':  '#ffffff',
    # 'sidebarbgcolor':   '#08385D',
    # # 'sidebartextcolor': ,
    # 'relbarbgcolor':    '#08385D',
    # 'relbartextcolor':  '#ffffff',
    # # 'relbarlinkcolor':  '#3432D8',
    # 'bgcolor':          '#ffffff',
    # # 'textcolor':        ,
    # 'linkcolor':        '#3432D8',
    # # 'visitedlinkcolor': ,
    # 'headbgcolor':      '#C1C1C1',
    # 'headtextcolor':    '#08385D',
    # 'headlinkcolor':    '#3432D8',
    # # 'codebgcolor':      ,
    # # 'codetextcolor':    ,
    # # 'bodyfont':         ,
    # # 'headfont':         ,
# }

# Add any paths that contain custom static files (such as style sheets) here,
# relative to this directory. They are copied after the builtin static files,
# so a file named "default.css" will overwrite the builtin "default.css".
html_static_path = ['static']




# END