# !/usr/bin/env python
#
# tidy3d documentation build configuration file, created by
# sphinx-quickstart on Fri Jun  9 13:47:02 2017.
#
# This file is execfile()d with the current directory set to its
# containing dir.
#
# Note that not all possible configuration values are present in this
# autogenerated file.
#
# All configuration values have a default; values that are commented out
# serve to show the default.

# If extensions (or modules to document with autodoc) are in another
# directory, add these directories to sys.path here. If the directory is
# relative to the documentation root, use os.path.abspath to make it
# absolute, like shown here.
#
import datetime
import logging
import os
import re
import subprocess
import sys

import tidy3d

# import sphinxcontrib.divparams as divparams

full_build = True

# TODO sort this out
here = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, os.path.abspath("_ext"))
# sys.path.insert(0, os.path.abspath("source"))
# sys.path.insert(0, os.path.abspath("notebooks"))
# # sys.path.insert(0, os.path.abspath(""))
# sys.path.insert(0, os.path.abspath("../tidy3d"))
# sys.path.insert(0, os.path.abspath("../tidy3d/components"))
# sys.path.insert(0, os.path.abspath("../tidy3d/components/base_sim"))
# sys.path.insert(0, os.path.abspath("../tidy3d/web"))
# sys.path.insert(0, os.path.abspath("../tidy3d/plugins"))

# -- Project information -----------------------------------------------------

project = "Tidy3D"
author = "Flexcompute"
year = datetime.date.today().strftime("%Y")
copyright = f"Flexcompute 2020-{year}"
master_doc = "index"  # The master toctree document.s

# -- General configuration ---------------------------------------------

# If your documentation needs a minimal Sphinx version, state it here.
#
# needs_sphinx = '1.0'

# Add any Sphinx extension module names here, as strings. They can be
# extensions coming with Sphinx (named 'sphinx.ext.*') or your custom ones.
add_module_names = False  # Remove namespaces from class/method signatures
autosummary_generate = full_build  # Turn on sphinx.ext.autosummary
# autoclass_content = "both"  # Add __init__ doc (ie. params) to class summaries
# autodoc_inherit_docstrings = True  # If no docstring, inherit from base class
autodoc_class_signature = "separated"
autodoc_default_options = {
    "members": True,
    "member-order": "bysource",
    "undoc-members": True,
}
autodoc_typehints = "none"
## TODO DEBATE KEEP
# autoclass_content = "class"
##
copybutton_prompt_text = r">>> |\.\.\. |\$ |In \[\d*\]: | {2,5}\.\.\.: | {5,8}: "
copybutton_prompt_is_regexp = True
custom_sitemap_excludes = [r"/notebooks/"]
# divparams_enable_postprocessing = True # TODO FIX
exclude_patterns = [
    "_docs/",
    "_templates/",
    "_ext/",
    "**.ipynb_checkpoints",
    ".DS_Store",
    "Thumbs.db",
    "faq/_faqs/*",
    "scripts/*",
    "tests/*",
    ".github/*",
]
extensions = [
    "IPython.sphinxext.ipython_directive",
    "IPython.sphinxext.ipython_console_highlighting",
    "nbsphinx",  # Integrate Jupyter Notebooks and Sphinx
    "notfound.extension",
    "myst_parser",
    # "sphinxcontrib.divparams", # TODO FIX
    "sphinx.ext.autodoc",  # Core Sphinx library for auto html doc generation from docstrings
    "sphinx.ext.autosummary",  # Create neat summary tables for modules/classes/methods etc
    "sphinx.ext.coverage",
    "sphinx.ext.extlinks",
    "sphinx.ext.intersphinx",  # Link to other project's documentation (see mapping below)
    "sphinx.ext.imgconverter",
    "sphinx.ext.mathjax",
    "sphinx.ext.napoleon",
    "sphinx.ext.todo",
    "sphinx.ext.viewcode",  # Add a link to the Python source code for classes, functions etc.
    "sphinx_copybutton",
    "sphinx_favicon",
    "sphinx_sitemap",
    "sphinx_tabs.tabs",
    "sphinxemoji.sphinxemoji",
    "custom-meta",  # In _ext, these need to be at the end of the extensions list
    "custom-sitemap",  # In _ext, these need to be at the end of the extensions list
    "custom-robots",  # In _ext, these need to be at the end of the extensions list
]
extlinks = {}
favicons = [
    {
        "sizes": "16x16",
        "href": "logo.svg",
    }
]
# Grouping the document tree into LaTeX files. List of tuples
# (source start file, target name, title, author, documentclass
# [howto, manual, or own class]).
language = "en"
latex_documents = [
    (master_doc, "main.tex", "tidy3d Documentation", "Flexcompute", "manual"),
]
html_baseurl = "https://docs.flexcompute.com/projects/tidy3d/"  # for sphinx-sitemap
html_css_files = [
    "css/custom.css",
]
html_extra_path = ["./_static/robots.txt", "./_static/"]
html_js_files = ["js/custom-download.js"]
htmlhelp_basename = "tidy3ddoc"
html_show_sourcelink = True  # Remove 'view source code' from top of page (for html, not python)
html_sourcelink_suffix = ""
html_static_path = [
    "./_static",
    # divparams.get_static_path() # TODO FIX
]
html_theme = "sphinx_book_theme"
html_title = "Tidy3D Electromagnetic Solver"
html_theme_options = {
    "logo": {
        "image_light": "./_static/img/Tidy3D-logo.svg",
        "image_dark": "./_static/img/Tidy3D-logo-white.svg",
    },
    "path_to_docs": "docs",
    "repository_url": "https://github.com/flexcompute/tidy3d",
    "repository_branch": "main",
    "launch_buttons": {
        "colab_url": "https://colab.research.google.com",
        "notebook_interface": "jupyterlab",
    },
    "use_edit_page_button": False,
    "use_issues_button": True,
    "use_repository_button": True,
    "use_download_button": True,
    "pygment_light_style": "colorful",
    "pygment_dark_style": "material",
}
latex_engine = "xelatex"
language = "en"
include_patterns = [
    "tidy3d/*",
    "faq/docs/**",
    "notebooks/*.ipynb",
    "notebooks/docs/*",
    "**.rst",
    "**.png",
    "**.svg",
    "**.txt",
    "**/sitemap.xml",
]
napoleon_google_docstring = False
napoleon_numpy_docstring = True
napoleon_include_init_with_doc = False
napoleon_include_private_with_doc = False
napoleon_include_special_with_doc = True
napoleon_use_admonition_for_examples = False
napoleon_use_admonition_for_notes = False
napoleon_use_admonition_for_references = False
napoleon_use_ivar = False
napoleon_use_param = True
napoleon_use_rtype = True
man_pages = [(master_doc, "tidy3d", "tidy3d Documentation", [author], 1)]
mathjax3_config = {
    "tex": {"tags": "ams", "useLabelIds": True},
}
myst_enable_extensions = [
    "amsmath",
    "dollarmath",
]
nbsphinx_allow_errors = True  # Continue through Jupyter errors
nbsphinx_execute = "never"
project = "tidy3d"
release = tidy3d.__version__
set_type_checking_flag = True  # Enable 'expensive' imports for sphinx_autodoc_typehints
sitemap_url_scheme = "{lang}{version}{link}"
sphinx_tabs_disable_css_loading = True
source_suffix = [".rst", ".md"]
templates_path = [
    "./_templates",
    # divparams.get_templates_path() # TODO FIX
]
texinfo_documents = [
    (
        master_doc,
        "tidy3d",
        "tidy3d Documentation",
        author,
        "tidy3d",
        "One line description of project.",
        "Miscellaneous",
    ),
]
todo_include_todos = False

GIT_TAG_OUTPUT = subprocess.check_output(["git", "tag", "--points-at", "HEAD"])
GIT_BRANCH_OUTPUT = subprocess.check_output(["git", "rev-parse", "--abbrev-ref", "HEAD"])
current_tag = GIT_TAG_OUTPUT.decode().strip()
current_branch = GIT_BRANCH_OUTPUT.decode().strip()
print(current_tag, current_branch)
if not current_tag and current_branch:
    if current_branch == "develop":
        version = "stable"
    elif current_branch == "latest":
        version = "latest"
    else:
        version = "latest"
elif current_tag:
    if re.match(r"^v(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$", current_tag):
        version = current_tag
    else:
        version = "latest"
# version = tidy3d.__version__

latex_elements = {
    "preamble": r"""
    \usepackage[utf8]{inputenc}
    \usepackage[T1]{fontenc}
    \usepackage[pdfa=true]{hyperref}
    \usepackage{cmap}
    """
}

# latex_elements: dict = {
#     # "preamble": r"\usepackage{bm}\n\usepackage{amssymb}\n\usepackage{esint}",
#     # The paper size ('letterpaper' or 'a4paper').
#     #
#     # 'papersize': 'letterpaper',
#     # The font size ('10pt', '11pt' or '12pt').
#     #
#     # 'pointsize': '10pt',
#     # Additional stuff for the LaTeX preamble.
#     #
#     # 'preamble': '',
#     # Latex figure (float) alignment
#     #
#     # 'figure_align': 'htbp',
# }


class ImportWarningFilter(logging.Filter):
    def filter(self, record):
        # Suppress specific autosummary import warnings
        message = record.getMessage()
        if "autosummary: failed to import" in message and any(
            phrase in message
            for phrase in ["ModuleNotFoundError", "ValueError", "KeyError", "AttributeError"]
        ):
            return False
        return True


class AutosummaryFilter(logging.Filter):
    """
    This is basically a hack until I finally get round to writing our own custom sphinx extension which will customise
    the way we represent our documentation properly. The goal of adding these filters is that at least we'll get useful
    information on errors, rather than those related to the docs memory - stub page generation tradeoff.
    """

    def filter(self, record):
        # Suppress "autosummary: stub file not found" warnings
        if "autosummary" in record.getMessage() and "stub file not found" in record.getMessage():
            return False
        return True


def add_import_warning_filter(app):
    # Get the Sphinx logger
    logger = logging.getLogger("sphinx")
    # Add the custom filter to the logger
    logger.addFilter(ImportWarningFilter())


def add_autosummary_filter(app):
    # Get the Sphinx logger
    logger = logging.getLogger("sphinx")
    # Add the custom filter to the logger
    logger.addFilter(AutosummaryFilter())


def setup(app):
    # Apply the custom filter early in the build process
    app.connect("builder-inited", add_autosummary_filter)
    app.connect("builder-inited", add_import_warning_filter)
