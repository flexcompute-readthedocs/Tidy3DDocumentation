# autograd wrapper for web functions

import tidy3d as td
from tidy3d.components.autograd import primitive, defvjp, AutogradFieldMap, get_static  # noqa: 401
import typing

import numpy as np

from .webapi import run as run_webapi


""" Helper Functions """


# TODO: move these somewhere else


def split_list(x: list[typing.Any], index: int) -> (list[typing.Any], list[typing.Any]):
    """Split a list at a given index."""
    x = list(x)
    return x[:index], x[index:]


def split_data_list(sim_data: td.SimulationData, num_mnts_original: int) -> tuple[list, list]:
    """Split data list into original, adjoint field, and adjoint permittivity."""

    data_all = list(sim_data.data)
    num_mnts_adjoint = (len(data_all) - num_mnts_original) // 2

    td.log.info(
        f" -> {num_mnts_original} monitors, {num_mnts_adjoint} adjoint field monitors, {num_mnts_adjoint} adjoint eps monitors."
    )

    data_original, data_adjoint = split_list(data_all, index=num_mnts_original)

    return data_original, data_adjoint


def E_to_D(fld_data: td.FieldData, eps_data: td.PermittivityData) -> td.FieldData:
    """Convert electric field to displacement field."""
    return multiply_field_data(fld_data, eps_data)


def derivative_map_E(fld_fwd: td.FieldData, fld_adj: td.FieldData) -> td.FieldData:
    """Get td.FieldData where the Ex, Ey, Ez components store the gradients w.r.t. these."""
    return multiply_field_data(fld_fwd, fld_adj)


def derivative_map_D(
    fld_fwd: td.FieldData,
    eps_fwd: td.PermittivityData,
    fld_adj: td.FieldData,
    eps_adj: td.PermittivityData,
) -> td.FieldData:
    """Get td.FieldData where the Ex, Ey, Ez components store the gradients w.r.t. D fields."""
    fwd_D = E_to_D(fld_data=fld_fwd, eps_data=eps_fwd)
    adj_D = E_to_D(fld_data=fld_adj, eps_data=eps_adj)
    return multiply_field_data(fwd_D, adj_D)


def multiply_field_data(
    fld_1: td.FieldData, fld_2: typing.Union[td.FieldData, td.PermittivityData]
) -> td.FieldData:
    """Elementwise multiply two field data objects, writes data into ``fld_1`` copy."""

    def get_field_key(dim: str, fld_data: typing.Union[td.FieldData, td.PermittivityData]) -> str:
        """Get the key corresponding to the scalar field along this dimension."""
        return f"E{dim}" if isinstance(fld_data, td.FieldData) else f"eps_{dim}{dim}"

    field_components = {}
    for dim in "xyz":
        key_1 = get_field_key(dim=dim, fld_data=fld_1)
        key_2 = get_field_key(dim=dim, fld_data=fld_2)
        cmp_1 = fld_1.field_components[key_1]
        cmp_2 = fld_2.field_components[key_2]
        mult = cmp_1 * cmp_2
        field_components[key_1] = mult
    return fld_1.updated_copy(**field_components)


""" Run Functions """

# keys for data into auxiliary dictionary
AUX_KEY_SIM_DATA_ORIGINAL = "sim_data"
AUX_KEY_SIM_DATA_FWD = "sim_data_fwd_adjoint"

# TODO: run_batch version


def _run_tidy3d(simulation: td.Simulation, task_name: str, **run_kwargs) -> td.SimulationData:
    """Run a simulation without any tracers using regular web.run()."""
    td.log.info("running regular simulation with '_run_tidy3d()'")
    # TODO: set task_type to "tidy3d adjoint autograd?"
    data = run_webapi(simulation, task_name=task_name, **run_kwargs)
    return data


@primitive
def _run_primitive(
    sim_fields: AutogradFieldMap,
    simulation: td.Simulation,
    task_name: str,
    aux_data: dict,
    **run_kwargs,
) -> AutogradFieldMap:
    """Autograd-traced 'run()' function: runs simulation, strips tracer data, caches fwd data."""

    td.log.info("running primitive '_run_primitive()'")

    # rid passed simulation of tracers and record how many monitors are in it (for reconstruction)
    # NOTE: will also validate that the un-traced simulation is valid before running
    sim_original = simulation.to_static()
    num_mnts_original = len(sim_original.monitors)

    # make and run a sim with combined original & adjoint monitors
    sim_combined = sim_original.with_adjoint_monitors(sim_fields)
    sim_data_combined = _run_tidy3d(sim_combined, task_name=task_name, **run_kwargs)

    # split the data and monitors into the original ones & adjoint gradient ones (for 'fwd')
    data_original, data_fwd = split_data_list(
        sim_data=sim_data_combined, num_mnts_original=num_mnts_original
    )
    _, monitors_fwd = split_list(sim_combined.monitors, index=num_mnts_original)

    # reconstruct the simulation data for the user, using original sim, and data for original mnts
    sim_data_original = sim_data_combined.updated_copy(
        simulation=sim_original, data=data_original, deep=False
    )

    # construct the 'forward' simulation and its data, which is only used for for gradient calc.
    sim_fwd = sim_combined.updated_copy(monitors=monitors_fwd)
    sim_data_fwd = sim_data_combined.updated_copy(
        simulation=sim_fwd,
        data=data_fwd,
        deep=False,
    )

    # cache these two SimulationData objects for later (note: the Simulations are already inside)
    aux_data[AUX_KEY_SIM_DATA_ORIGINAL] = sim_data_original
    aux_data[AUX_KEY_SIM_DATA_FWD] = sim_data_fwd

    # strip out the tracer AutogradFieldMap for the .data from the original sim
    data_traced = sim_data_original.strip_traced_fields()

    # need to get the static version of the arrays, otherwise get ArrayBox of ArrayBox
    # NOTE: this is a bit confusing to me, why does autograd make them ArrayBox out of _run_tidy3d?

    data_traced = {path: value for path, value in data_traced.items() if path[0] == "data"}

    # return the AutogradFieldMap that autograd registers as the "output" of the primitive
    return data_traced


def run(simulation: td.Simulation, task_name: str, **run_kwargs) -> td.SimulationData:
    """User-facing run function, compatible with autograd."""
    """
    Submits a :class:`.Simulation` to server, starts running, monitors progress, downloads,
    and loads results as a :class:`.SimulationDataType` object.

    Parameters
    ----------
    simulation : :class:`.Simulation`
        Simulation to upload to server.
    task_name : str
        Name of task.
    folder_name : str = "default"
        Name of folder to store task on web UI.
    path : str = "simulation_data.hdf5"
        Path to download results file (.hdf5), including filename.
    callback_url : str = None
        Http PUT url to receive simulation finish event. The body content is a json file with
        fields ``{'id', 'status', 'name', 'workUnit', 'solverVersion'}``.
    verbose : bool = True
        If ``True``, will print progressbars and status, otherwise, will run silently.
    simulation_type : str = "tidy3d"
        Type of simulation being uploaded.
    progress_callback_upload : Callable[[float], None] = None
        Optional callback function called when uploading file with ``bytes_in_chunk`` as argument.
    progress_callback_download : Callable[[float], None] = None
        Optional callback function called when downloading file with ``bytes_in_chunk`` as argument.
    solver_version: str = None
        target solver version.
    worker_group: str = None
        worker group

    Returns
    -------
    :class:`.SimulationData`
        Object containing solver results for the supplied simulation.

    Notes
    -----

        Submitting a simulation to our cloud server is very easily done by a simple web API call.

        .. code-block:: python

            sim_data = tidy3d.web.api.webapi.run(simulation, task_name='my_task', path='out/data.hdf5')

        The :meth:`tidy3d.web.api.webapi.run()` method shows the simulation progress by default.  When uploading a
        simulation to the server without running it, you can use the :meth:`tidy3d.web.api.webapi.monitor`,
        :meth:`tidy3d.web.api.container.Job.monitor`, or :meth:`tidy3d.web.api.container.Batch.monitor` methods to
        display the progress of your simulation(s).

    Examples
    --------

        To differentiate an objective function depending on some parameters through ``run_adjoint`

        .. code-block:: python

            def objective_funcion(params):

                sim = make_simulation(params)

                # Run the simulation.
                sim_data = web.run_autograd(simulation, task_name='task_name', path='out/sim.hdf5')

                return postprocess(sim_data)

            import autograd as ag
            ag.grad(objective_function)(parameters)

    See Also
    --------

    :meth:`tidy3d.web.api.webapi.run`
        Run a task (without autograd)

    """

    td.log.info("running user-facing run()")

    # get a mapping of all the traced fields in the provided simulation
    traced_fields_sim = simulation.strip_traced_fields()

    # if we register this as not needing adjoint at all (no tracers), call regular run function
    if not traced_fields_sim:
        td.log.info(
            "No autograd derivative tracers found in the 'Simulation' passed to 'run'. "
            "This could indicate that there is no path from your objective function arguments "
            "to the 'Simulation'. If this is unexpected, double check your objective function "
            "pre-processing. Running regular tidy3d simulation."
        )
        return _run_tidy3d(simulation, task_name=task_name, **run_kwargs)

    td.log.info("Found derivative tracers in the 'Simulation', running adjoint forward pass.")

    # will store the SimulationData for original and forward so we can access them later
    aux_data = {}

    # run our custom @primitive, passing the traced fields first to register with autograd
    traced_fields_data = _run_primitive(
        traced_fields_sim,
        simulation=simulation,
        task_name=task_name,
        aux_data=aux_data,
        **run_kwargs,
    )
    traced_fields_data = {key: val for key, val in traced_fields_data.items() if key[0] == "data"}

    # grab the user's 'SimulationData' and return with the autograd-tracers inserted
    sim_data_original = aux_data[AUX_KEY_SIM_DATA_ORIGINAL]
    return sim_data_original.insert_traced_fields(traced_fields_data)


def _run_bwd(
    data_fields_original: AutogradFieldMap,
    sim_fields_original: AutogradFieldMap,
    simulation: td.Simulation,
    task_name: str,
    aux_data: dict,
    **run_kwargs,
) -> typing.Callable[[AutogradFieldMap], AutogradFieldMap]:
    """VJP-maker for ``_run_primitive()``. Constructs and runs adjoint simulation, computes grad."""

    # get the fwd epsilon and field data from the cached aux_data
    sim_data_orig = aux_data[AUX_KEY_SIM_DATA_ORIGINAL]
    sim_data_fwd = aux_data[AUX_KEY_SIM_DATA_FWD]

    td.log.info("constructing custom vjp function for backwards pass.")

    def vjp(data_fields_vjp: AutogradFieldMap) -> AutogradFieldMap:
        """dJ/d{sim.traced_fields()} as a function of Function of dJ/d{data.traced_fields()}"""

        td.log.info("Running custom vjp (adjoint) pipeline.")

        # immediately filter out any data_vjps with all 0's in the data
        data_fields_vjp = {
            key: get_static(value)
            for key, value in data_fields_vjp.items()
            if not np.all(value == 0.0)
        }

        # insert the raw VJP data into the .data of the original SimulationData
        sim_data_vjp = sim_data_orig.insert_traced_fields(field_mapping=data_fields_vjp)

        # make adjoint simulation from that SimulationData
        data_vjp_paths = set(data_fields_vjp.keys())
        sim_adj = sim_data_vjp.make_adjoint_sim(
            data_vjp_paths=data_vjp_paths, adjoint_monitors=sim_data_fwd.simulation.monitors
        )

        td.log.info(f"Adjoint simulation created with {len(sim_adj.sources)} sources.")

        # no adjoint sources, no gradient for you :(
        if not len(sim_adj.sources):
            td.log.warning(
                "No adjoint sources generated. "
                "There is likely zero output in the data, or you have no traceable monitors. "
                "As a result, the 'SimulationData' returned has no contribution to the gradient. "
                "Skipping the adjoint simulation. "
                "If this is unexpected, please double check the post-processing function to ensure "
                "there is a path from the 'SimulationData' to the objective function return value."
            )

            # TODO: add a test for this
            # construct a VJP of all zeros for all tracers in the original simulation
            return {path: 0 * value for path, value in sim_fields_original.items()}

        # run adjoint simulation
        task_name_adj = task_name + "_adjoint"
        sim_data_adj = _run_tidy3d(sim_adj, task_name=task_name_adj, **run_kwargs)

        # map of index into 'structures' to the list of paths we need vjps for
        sim_vjp_map = {}
        for _, structure_index, *structure_path in sim_fields_original.keys():
            structure_path = tuple(structure_path)
            if structure_index in sim_vjp_map:
                sim_vjp_map[structure_index].append(structure_path)
            else:
                sim_vjp_map[structure_index] = [structure_path]

        # store the derivative values given the forward and adjoint data
        sim_fields_vjp = {}
        for structure_index, structure_paths in sim_vjp_map.items():
            # grab the forward and adjoint data
            fld_fwd = sim_data_fwd.get_adjoint_data(structure_index, data_type="fld")
            eps_fwd = sim_data_fwd.get_adjoint_data(structure_index, data_type="eps")
            fld_adj = sim_data_adj.get_adjoint_data(structure_index, data_type="fld")
            eps_adj = sim_data_adj.get_adjoint_data(structure_index, data_type="eps")

            # maps of the E_fwd * E_adj and D_fwd * D_adj, each as as td.FieldData & 'Ex', 'Ey', 'Ez'
            E_der_map = derivative_map_E(fld_fwd=fld_fwd, fld_adj=fld_adj)
            D_der_map = derivative_map_D(
                fld_fwd=fld_fwd, eps_fwd=eps_fwd, fld_adj=fld_adj, eps_adj=eps_adj
            )

            # compute the derivatives for this structure
            structure = sim_data_fwd.simulation.structures[structure_index]
            vjp_value_map = structure.compute_derivatives(
                structure_paths=structure_paths,
                E_der_map=E_der_map,
                D_der_map=D_der_map,
                eps_structure=eps_fwd,
                eps_sim=sim_data_orig.simulation.medium.permittivity,
                bounds=structure.geometry.bounds,  # TODO: pass intersecting bounds with sim?
            )

            # extract VJPs and put back into sim_fields_vjp AutogradFieldMap
            for structure_path, vjp_value in vjp_value_map.items():
                sim_path = tuple(["structures", structure_index] + list(structure_path))
                sim_fields_vjp[sim_path] = vjp_value

        return sim_fields_vjp

    return vjp


defvjp(_run_primitive, _run_bwd, argnums=[0])
