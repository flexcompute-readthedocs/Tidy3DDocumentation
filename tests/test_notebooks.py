import os
import sys

import pytest

# note: these libraries throw Deprecation warnings in python 3.9, so they are ignored in pytest.ini
import nbconvert
import nbformat
from nbconvert.preprocessors import CellExecutionError
from nbconvert.preprocessors import ExecutePreprocessor

sys.path.append("../tidy3d")

ep = ExecutePreprocessor(timeout=1000, kernel_name="python3")

# get all notebook files
NOTEBOOK_DIR = "docs/source/notebooks/"
notebook_filenames = [
    NOTEBOOK_DIR + f
    for f in os.listdir(NOTEBOOK_DIR)
    if ".ipynb" in f and f != ".ipynb_checkpoints"
]

# if you want to run only some notebooks, put here, if empty, run all
run_only = []
# run_only = ["HighQ_Si"]#, "HighQ_Ge", "RingResonator"]
if len(run_only):
    notebook_filenames = [NOTEBOOK_DIR + base + ".ipynb" for base in run_only]

# for name in notebook_filenames:
#     print(f"'{name}'")
""" 
as of 5/18/22
'docs/source/notebooks/Dispersion.ipynb'
'docs/source/notebooks/Modes_bent_angled.ipynb'
'docs/source/notebooks/StartHere.ipynb'
'docs/source/notebooks/VizData.ipynb'
'docs/source/notebooks/Modal_sources_monitors.ipynb'
'docs/source/notebooks/Near2FarSphereRCS.ipynb'
'docs/source/notebooks/HighQ_Ge.ipynb'
'docs/source/notebooks/WhatsNew.ipynb'
'docs/source/notebooks/Metalens.ipynb'
'docs/source/notebooks/GDS_import.ipynb'
'docs/source/notebooks/RingResonator.ipynb'
'docs/source/notebooks/HighQ_Si.ipynb'
'docs/source/notebooks/GratingCoupler.ipynb'
'docs/source/notebooks/Simulation.ipynb'
'docs/source/notebooks/ModeSolver.ipynb'
'docs/source/notebooks/L3_cavity.ipynb'
'docs/source/notebooks/WebAPI.ipynb'
'docs/source/notebooks/ParameterScan.ipynb'
'docs/source/notebooks/VizSimulation.ipynb'
'docs/source/notebooks/SMatrix.ipynb'
'docs/source/notebooks/Fitting.ipynb'
'docs/source/notebooks/AutoGrid.ipynb'
'docs/source/notebooks/Near2Far.ipynb'
'docs/source/notebooks/Adjoint.ipynb'
"""


@pytest.mark.parametrize("fname", notebook_filenames)
def test_notebooks(fname):
    # loop through notebooks in notebook_filenames and test each of them separately
    _run_notebook(fname)


def _run_notebook(notebook_fname):

    # open the notebook
    with open(notebook_fname) as f:
        nb = nbformat.read(f, as_version=4)

        # try running the notebook
        try:
            # run from the `notebooks/` directory
            out = ep.preprocess(nb, {"metadata": {"path": f"{NOTEBOOK_DIR}"}})

        # if there is an error, print message and fail test
        except CellExecutionError as e:
            out = None
            msg = 'Error executing the notebook "%s".\n\n' % notebook_fname
            msg += 'See notebook "%s" for the traceback.' % notebook_fname
            print(msg)
            raise

        # write the executed notebook to file
        finally:
            with open(notebook_fname, mode="w", encoding="utf-8") as f:
                nbformat.write(nb, f)

        # can we get notebook's local variables and do more individual tests?
