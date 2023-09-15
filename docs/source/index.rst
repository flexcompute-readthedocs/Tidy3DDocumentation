Tidy3D Documentation
====================

.. To do items:
.. * open simple example in colab with API saved as environment variable and `!pip install tidy3d` in the first line.
.. * toggle between command line - notebook / python instructions in section 1
Tidy3D is a software package for solving extremely large electrodynamics problems using the finite-difference time-domain (FDTD) method. It can be controlled through either an `open source python package <https://github.com/flexcompute/tidy3d>`_ or a `web-based graphical user interface <https://tidy3d.simulation.cloud>`_.

If you do not wish to install, please click this button to `get started quickly <https://tidy3d.simulation.cloud/notebook?file=StartHere.ipynb>`.

.. `TODO: open example in colab <https://github.com/flexcompute/tidy3d>`_

1. Set up Tidy3d
~~~~~~~~~~~~~~~~

Install the python library `tidy3d <https://github.com/flexcompute/tidy3d>`_ for creating, managing, and postprocessing simulations with

.. code-block:: bash

   pip install tidy3d

Next, configure your tidy3d package with the API key from your account.

`Get your free API key <https://tidy3d.simulation.cloud/account?tab=apikey>`_

.. code-block:: bash

   tidy3d configure

And enter your API key when prompted.

For more detailed installation instructions, see `this page <https://docs.flexcompute.com/projects/tidy3d/en/latest/quickstart.html>`_.

2. Run a Simulation
~~~~~~~~~~~~~~~~~~~

Start running simulations with just a few lines of code. Run this sample code to simulate a 3D dielectric box in Tidy3D and plot the corresponding field pattern.

.. code-block:: python

   # import the tidy3d package and configure it with your API key
   import tidy3d as td
   import tidy3d.web as web

   # set up global parameters of simulation ( speed of light / wavelength in micron )
   freq0 = td.C_0 / 0.75

   # create structure - a box centered at 0, 0, 0 with a size of 1.5 micron and permittivity of 2
   square = td.Structure(
       geometry=td.Box(center=(0, 0, 0), size=(1.5, 1.5, 1.5)), 
       medium=td.Medium(permittivity=2.0)
   )

   # create source - A uniform current source with frequency freq0 on the left side of the domain
   source = td.UniformCurrentSource(
       center=(-1.5, 0, 0),
       size=(0, 0.4, 0.4),
       source_time=td.GaussianPulse(freq0=freq0, fwidth=freq0 / 10.0),
       polarization="Ey",
   )

   # create monitor - Measures electromagnetic fields within the entire domain at z=0
   monitor = td.FieldMonitor(
       size=(td.inf, td.inf, 0),
       freqs=[freq0],
       name="fields",
       colocate=True,
   )

   # Initialize simulation - Combine all objects together into a single specification to run
   sim = td.Simulation(
       size=(4, 3, 3),
       grid_spec=td.GridSpec.auto(min_steps_per_wvl=25),
       structures=[square],
       sources=[source],
       monitors=[monitor],
       run_time=120/freq0,
   )

   print(f"simulation grid is shaped {sim.grid.num_cells} for {int(np.prod(sim.grid.num_cells)/1e6)} million cells.")

   # run simulation through the cloud and plot the field data computed by the solver and stored in the monitor
   data = td.web.run(sim, task_name="quickstart", path="data/data.hdf5", verbose=True)
   ax = data.plot_field("fields", "Ey", z=0)

This will produce the following plot, which visualizes the electromagnetic fields on the central plane.

.. image:: _static/quickstart_fields.png
   :width: 1200

3. Analyze Results
~~~~~~~~~~~~~~~~~~

a) Postprocess simulation data using the same python session, or

b) View the results of this simulation on our web-based `graphical user interface <https://tidy3d.simulation.cloud>`_.

4. Learn More
~~~~~~~~~~~~~

.. toctree::
   :maxdepth: 1

   quickstart
   examples
   faq
   howdoi
   api
   changelog
   Tidy3D Solver Technology <https://www.flexcompute.com/tidy3d/solver/>


