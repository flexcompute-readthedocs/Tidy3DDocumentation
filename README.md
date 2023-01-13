# Tidy3D Documentation

[![Notebooks](https://mybinder.org/badge_logo.svg)](https://mybinder.org/v2/gh/flexcompute-readthedocs/tidy3d-docs/readthedocs?labpath=docs%2Fsource%2Fnotebooks)
[![Documentation Status](https://readthedocs.com/projects/flexcompute-tidy3ddocumentation/badge/?version=latest)](https://flexcompute-tidy3ddocumentation.readthedocs-hosted.com/?badge=latest)
![tests](https://github.com/flexcompute/tidy3d/actions/workflows//run_tests.yml/badge.svg)

## Website

The website can be found [here](https://flexcompute-tidy3ddocumentation.readthedocs-hosted.com/).

It is hosted by readthedocs, the admin site can be found [here](https://readthedocs.com/dashboard/).

## Notebooks

The notebooks are in `docs/source/notebooks`.

To run the notebooks from browser, click [this link](https://mybinder.org/v2/gh/flexcompute/Tidy3D-docs/HEAD?filepath=docs/notebooks/) or the "Binder" tag at the top of this README.

## Setup

First time you want to use the docs, install all packages and make the docs building script executable.

```bash
git submodule init tidy3d
git submodule update tidy3d
pip install -r tidy3d/requirements/dev.txt
pip install -r docs/requirements.txt
pip install -r tests/requirements.txt
```

## Compiling

To compile the docs:

```bash
cd docs/source
rm -rf _build
rm -rf _autosummary
python -m sphinx -T -b html -d _build/doctrees -D language=en . _build/html
open _build/html/index.html
```

## Tests

There is one test, which runs all of the notebooks and fails if there are any errors.

To run the test:

```bash
pytest -rA tests
```

## Formatting notebooks

Before release, we may want to format the code using [jupyterblack](https://github.com/irahorecka/jupyterblack).

This package may be installed via
```
pip install jupyterblack
```
and used to format a single notebook `X.ipynb` as
```
jblack docs/source/notebooks/X.ipynb
```
or all notebooks as 
```
jblack docs/source/notebooks/*.ipynb
```

Note: is is not in the standard requiremenents yet as we are still experimenting with it.

## Git Friendly Notebooks

We use nbdev, documentation [here](https://nbdev.fast.ai/tutorials/git_friendly_jupyter.html).

```
pip install nbdev
nbdev_install_hooks
```

