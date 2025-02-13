"""Tests adjoint plugin."""

import builtins
import time
from typing import Dict, List, Tuple

import gdstk
import h5py
import jax
import jax.numpy as jnp
import matplotlib.pyplot as plt
import numpy as np
import pydantic.v1 as pydantic
import pytest
import tidy3d as td
import trimesh
from jax import grad
from jax.test_util import check_grads
from numpy.testing import assert_allclose
from tidy3d.exceptions import AdjointError, DataError, Tidy3dKeyError
from tidy3d.plugins.adjoint.components import simulation
from tidy3d.plugins.adjoint.components.data.data_array import (
    JAX_DATA_ARRAY_TAG,
    VALUE_FILTER_THRESHOLD,
    JaxDataArray,
)
from tidy3d.plugins.adjoint.components.data.dataset import JaxPermittivityDataset
from tidy3d.plugins.adjoint.components.data.monitor_data import (
    JaxDiffractionData,
    JaxFieldData,
    JaxModeData,
)
from tidy3d.plugins.adjoint.components.data.sim_data import JaxSimulationData
from tidy3d.plugins.adjoint.components.geometry import (
    MAX_NUM_VERTICES,
    JaxBox,
    JaxComplexPolySlab,
    JaxGeometryGroup,
    JaxPolySlab,
)
from tidy3d.plugins.adjoint.components.medium import (
    MAX_NUM_CELLS_CUSTOM_MEDIUM,
    JaxAnisotropicMedium,
    JaxCustomMedium,
    JaxMedium,
)
from tidy3d.plugins.adjoint.components.simulation import RUN_TIME_FACTOR, JaxInfo, JaxSimulation
from tidy3d.plugins.adjoint.components.structure import (
    JaxStructure,
    JaxStructureStaticGeometry,
    JaxStructureStaticMedium,
)
from tidy3d.plugins.adjoint.utils.filter import BinaryProjector, CircularFilter, ConicFilter
from tidy3d.plugins.adjoint.utils.penalty import ErosionDilationPenalty, RadiusPenalty
from tidy3d.plugins.adjoint.web import run, run_async, run_async_local, run_local
from tidy3d.plugins.polyslab import ComplexPolySlab
from tidy3d.web.api.container import BatchData
from xarray import DataArray

from ..test_components.test_custom import CUSTOM_MEDIUM
from ..utils import AssertLogLevel, assert_log_level, run_async_emulated, run_emulated

TMP_PATH = None
FWD_SIM_DATA_FILE = "adjoint_grad_data_fwd.hdf5"
SIM_VJP_FILE = "adjoint_sim_vjp_file.hdf5"
RUN_FILE = "simulation.hdf5"
NUM_PROC_PARALLEL = 2

EPS = 2.0
SIZE = (1.0, 2.0, 3.0)
CENTER = (2.0, -1.0, 1.0)
VERTICES = ((-1.0, -1.0), (0.0, 0.0), (-1.0, 0.0))
POLYSLAB_AXIS = 2
FREQ0 = 2e14
BASE_EPS_VAL = 2.0
SIM_RUN_TIME = 1e-12
# name of the output monitor used in tests
MNT_NAME = "mode"

src = td.PointDipole(
    center=(0, 0, 0),
    source_time=td.GaussianPulse(freq0=FREQ0, fwidth=FREQ0 / 10),
    polarization="Ex",
)


@pytest.fixture
def use_emulated_run(monkeypatch, tmp_path_factory):
    """If this fixture is used, the `tests.utils.run_emulated` function is used for simulation."""
    global TMP_PATH
    import tidy3d.plugins.adjoint.web as adjoint_web

    TMP_PATH = tmp_path_factory.mktemp("adjoint")
    monkeypatch.setattr(adjoint_web, "tidy3d_run_fn", run_emulated)
    monkeypatch.setattr(td.web, "run", run_emulated)
    monkeypatch.setattr(adjoint_web, "webapi_run_adjoint_fwd", run_emulated_fwd)
    monkeypatch.setattr(adjoint_web, "webapi_run_adjoint_bwd", run_emulated_bwd)


@pytest.fixture
def use_emulated_run_async(monkeypatch, tmp_path_factory):
    """If this fixture is used, the `tests.utils.run_emulated` function is used for simulation."""
    global TMP_PATH
    import tidy3d.plugins.adjoint.web as adjoint_web

    TMP_PATH = tmp_path_factory.mktemp("adjoint")
    monkeypatch.setattr(adjoint_web, "tidy3d_run_async_fn", run_async_emulated)
    monkeypatch.setattr(td.web, "run_async", run_async_emulated)
    monkeypatch.setattr(adjoint_web, "webapi_run_async_adjoint_fwd", run_async_emulated_fwd)
    monkeypatch.setattr(adjoint_web, "webapi_run_async_adjoint_bwd", run_async_emulated_bwd)


# Emulated forward and backward run functions
def run_emulated_fwd(
    simulation: td.Simulation,
    jax_info: JaxInfo,
    task_name: str,
    folder_name: str,
    path: str,
    callback_url: str,
    verbose: bool,
):
    """Runs the forward simulation on our servers, stores the gradient data for later."""

    # Simulation data with both original and gradient data
    sim_data = run_emulated(
        simulation=simulation,
        task_name=str(task_name),
        path=path,
    )

    # simulation data (without gradient data), written to the path file
    sim_data_orig, sim_data_store = JaxSimulationData.split_fwd_sim_data(
        sim_data=sim_data, jax_info=jax_info
    )

    # Test file IO
    sim_data_orig.to_file(path)
    sim_data_orig = td.SimulationData.from_file(path)

    # gradient data stored for later use
    jax_sim_data_store = JaxSimulationData.from_sim_data(sim_data_store, jax_info)
    jax_sim_data_store.to_file(str(TMP_PATH / FWD_SIM_DATA_FILE))

    task_id = "test"
    return sim_data_orig, task_id


def run_emulated_bwd(
    sim_adj: td.Simulation,
    jax_info_adj: JaxInfo,
    fwd_task_id: str,
    task_name: str,
    folder_name: str,
    callback_url: str,
    verbose: bool,
    num_proc: int = None,
) -> JaxSimulation:
    """Runs adjoint simulation on our servers, grabs the gradient data from fwd for processing."""

    if num_proc is None:
        num_proc = NUM_PROC_PARALLEL

    # Forward data
    sim_data_fwd = JaxSimulationData.from_file(str(TMP_PATH / FWD_SIM_DATA_FILE))
    grad_data_fwd = sim_data_fwd.grad_data_symmetry
    grad_eps_data_fwd = sim_data_fwd.grad_eps_data_symmetry

    # Adjoint data
    sim_data_adj = run_emulated(
        simulation=sim_adj,
        task_name=str(task_name),
        path=str(TMP_PATH / RUN_FILE),
    )

    jax_sim_data_adj = JaxSimulationData.from_sim_data(sim_data_adj, jax_info_adj)
    grad_data_adj = jax_sim_data_adj.grad_data_symmetry

    # get gradient and insert into the resulting simulation structure medium
    sim_vjp = jax_sim_data_adj.simulation.store_vjp(
        grad_data_fwd, grad_data_adj, grad_eps_data_fwd, num_proc=num_proc
    )

    # write VJP sim to and from file to emulate webapi download and loading
    sim_vjp.to_file(str(TMP_PATH / SIM_VJP_FILE))
    sim_vjp = JaxSimulation.from_file(str(TMP_PATH / SIM_VJP_FILE))

    return sim_vjp


# Emulated forward and backward run functions
def run_async_emulated_fwd(
    simulations: Tuple[td.Simulation, ...],
    jax_infos: Tuple[JaxInfo, ...],
    folder_name: str,
    path_dir: str,
    callback_url: str,
    verbose: bool,
) -> Tuple[BatchData, Dict[str, str]]:
    """Runs the forward simulation on our servers, stores the gradient data for later."""

    sim_datas_orig = {}
    task_ids = []

    for i, (sim, jax_info) in enumerate(zip(simulations, jax_infos)):
        sim_data_orig, task_id = run_emulated_fwd(
            simulation=sim,
            jax_info=jax_info,
            task_name=str(i),
            folder_name=folder_name,
            path=path_dir + str(i) + ".hdf5",
            callback_url=callback_url,
            verbose=verbose,
        )
        task_ids.append(task_id)
        sim_datas_orig[str(i)] = sim_data_orig

    return sim_datas_orig, task_ids


def run_async_emulated_bwd(
    simulations: Tuple[td.Simulation, ...],
    jax_infos: Tuple[JaxInfo, ...],
    folder_name: str,
    path_dir: str,
    callback_url: str,
    verbose: bool,
    parent_tasks: List[List[str]],
) -> List[JaxSimulation]:
    """Runs adjoint simulation on our servers, grabs the gradient data from fwd for processing."""

    sim_vjps_orig = []

    for i, (sim, jax_info, _) in enumerate(zip(simulations, jax_infos, parent_tasks)):
        sim_vjp = run_emulated_bwd(
            sim_adj=sim,
            jax_info_adj=jax_info,
            fwd_task_id="test",
            task_name=str(i),
            folder_name=folder_name,
            callback_url=callback_url,
            verbose=verbose,
            num_proc=None,
        )
        sim_vjps_orig.append(sim_vjp)

    return sim_vjps_orig


def make_sim(
    permittivity: float,
    size: Tuple[float, float, float],
    vertices: tuple,
    base_eps_val: float,
    custom_medium: bool = True,
) -> JaxSimulation:
    """Construt a simulation out of some input parameters."""

    box = td.Box(size=(0.2, 0.2, 0.2), center=(5, 0, 2))
    med = td.Medium(permittivity=2.0)
    extraneous_structure = td.Structure(geometry=box, medium=med)

    # NOTE: Any new input structures should be added below as they are made

    # JaxBox
    jax_box1 = JaxBox(size=size, center=(1, 0, 2))
    jax_med1 = JaxMedium(permittivity=permittivity, conductivity=permittivity * 0.1)
    jax_struct1 = JaxStructure(geometry=jax_box1, medium=jax_med1)

    jax_box2 = JaxBox(size=size, center=(-1, 0, -3))
    jax_med2 = JaxAnisotropicMedium(
        xx=JaxMedium(permittivity=permittivity),
        yy=JaxMedium(permittivity=permittivity + 2),
        zz=JaxMedium(permittivity=permittivity * 2),
    )
    jax_struct2 = JaxStructure(geometry=jax_box2, medium=jax_med2)

    jax_polyslab1 = JaxPolySlab(axis=POLYSLAB_AXIS, vertices=vertices, slab_bounds=(-1, 1))
    jax_struct3 = JaxStructure(geometry=jax_polyslab1, medium=jax_med1)

    jax_complexpolyslab = JaxComplexPolySlab(
        axis=POLYSLAB_AXIS, vertices=vertices, slab_bounds=(-1, 1), sidewall_angle=np.deg2rad(10)
    )
    jax_struct_complex = [
        JaxStructure(geometry=p, medium=jax_med1) for p in jax_complexpolyslab.sub_polyslabs
    ]

    # custom medium
    Nx, Ny, Nz = 10, 1, 10
    (xmin, ymin, zmin), (xmax, ymax, zmax) = jax_box1.bounds
    coords = dict(
        x=np.linspace(xmin, xmax, Nx).tolist(),
        y=np.linspace(ymin, ymax, Ny).tolist(),
        z=np.linspace(zmin, zmax, Nz).tolist(),
        f=(FREQ0,),
    )

    jax_box_custom = JaxBox(size=size, center=(1, 0, 2))
    values = base_eps_val + np.random.random((Nx, Ny, Nz, 1))

    # adding this line breaks things without enforcing that the vjp for custom medium is complex
    values = (1 + 1j) * values
    values = values + (1 + 1j) * values / 0.5

    eps_ii = JaxDataArray(values=values, coords=coords)
    field_components = {f"eps_{dim}{dim}": eps_ii for dim in "xyz"}
    jax_eps_dataset = JaxPermittivityDataset(**field_components)
    jax_med_custom = JaxCustomMedium(eps_dataset=jax_eps_dataset)
    jax_struct_custom = JaxStructure(geometry=jax_box_custom, medium=jax_med_custom)

    field_components_anis = {
        f"eps_{dim}{dim}": const * eps_ii for const, dim in zip([1.0, 2.0, 3.0], "xyz")
    }
    jax_eps_dataset_anis = JaxPermittivityDataset(**field_components_anis)
    jax_med_custom_anis = JaxCustomMedium(eps_dataset=jax_eps_dataset_anis)
    jax_struct_custom_anis = JaxStructure(geometry=jax_box_custom, medium=jax_med_custom_anis)

    jax_geo_group = JaxGeometryGroup(geometries=[jax_polyslab1, jax_polyslab1])
    jax_struct_group = JaxStructure(geometry=jax_geo_group, medium=jax_med1)

    jax_struct_static_med = JaxStructureStaticMedium(
        geometry=jax_box1,
        medium=td.Medium(),  # material_library["Ag"]["Rakic1998BB"]
    )
    jax_struct_static_geo = JaxStructureStaticGeometry(
        geometry=td.Box(size=(1, 1, 1)), medium=jax_med1
    )

    # TODO: Add new geometries as they are created.

    # NOTE: Any new output monitors should be added below as they are made

    # ModeMonitors
    output_mnt1 = td.ModeMonitor(
        size=(10, 10, 0),
        mode_spec=td.ModeSpec(num_modes=3),
        freqs=[FREQ0, FREQ0 * 1.1],
        name=MNT_NAME + "1",
    )

    # DiffractionMonitor
    output_mnt2 = td.DiffractionMonitor(
        center=(0, 0, 4),
        size=(td.inf, td.inf, 0),
        normal_dir="+",
        freqs=[FREQ0],
        name=MNT_NAME + "2",
    )

    output_mnt3 = td.FieldMonitor(
        size=(2, 0, 2),
        freqs=[FREQ0],
        name=MNT_NAME + "3",
    )

    output_mnt4 = td.FieldMonitor(
        size=(0, 0, 0),
        freqs=np.array([FREQ0, FREQ0 * 1.1]),
        name=MNT_NAME + "4",
    )

    extraneous_field_monitor = td.FieldMonitor(
        size=(10, 10, 0),
        freqs=np.array([1e14, 2e14]),
        name="field",
    )

    if custom_medium:
        input_structures = (
            jax_struct1,
            jax_struct2,
            jax_struct_custom,
            jax_struct3,
            *jax_struct_complex,
            jax_struct_group,
            jax_struct_custom_anis,
            jax_struct_static_med,
            jax_struct_static_geo,
        )
    else:
        input_structures = (
            jax_struct1,
            jax_struct2,
            jax_struct3,
            *jax_struct_complex,
            jax_struct_group,
            jax_struct_static_med,
            jax_struct_static_geo,
        )

    sim = JaxSimulation(
        size=(10, 10, 10),
        run_time=SIM_RUN_TIME,
        grid_spec=td.GridSpec(wavelength=4.0),
        monitors=(extraneous_field_monitor,),
        structures=(extraneous_structure,),
        input_structures=input_structures,
        output_monitors=(output_mnt1, output_mnt2, output_mnt3, output_mnt4),
        sources=[src],
        boundary_spec=td.BoundarySpec.pml(x=False, y=False, z=False),
        symmetry=(1, 0, -1),
    )

    return sim


def objective(amp: complex) -> float:
    """Objective function as a function of the complex amplitude."""
    return abs(amp) ** 2


def extract_amp(sim_data: td.SimulationData) -> complex:
    """get the amplitude from a simulation data object."""

    ret_value = 0.0

    # ModeData
    mnt_name = MNT_NAME + "1"
    mnt_data = sim_data[mnt_name]
    amps = mnt_data.amps
    ret_value += amps.sel(direction="+", f=2e14, mode_index=0)
    ret_value += amps.isel(direction=0, f=0, mode_index=0)
    ret_value += amps.sel(direction="-", f=2e14, mode_index=1)
    ret_value += amps.sel(mode_index=1, f=2e14, direction="-")
    ret_value += amps.sel(direction="-", f=2e14).isel(mode_index=1)

    # DiffractionData
    mnt_name = MNT_NAME + "2"
    mnt_data = sim_data[mnt_name]
    ret_value += mnt_data.amps.sel(orders_x=0, orders_y=0, f=2e14, polarization="p")
    ret_value += mnt_data.amps.sel(orders_x=-1, orders_y=1, f=2e14, polarization="p")
    ret_value += mnt_data.amps.isel(orders_x=0, orders_y=1, f=0, polarization=0)
    ret_value += mnt_data.Er.isel(orders_x=0, orders_y=1, f=0)
    ret_value += mnt_data.power.sel(orders_x=-1, orders_y=1, f=2e14)

    # FieldData
    mnt_name = MNT_NAME + "3"
    mnt_data = sim_data[mnt_name]
    ret_value += jnp.sum(jnp.array(mnt_data.Ex.values))
    ret_value += jnp.sum(jnp.array(mnt_data.Ex.interp(z=0).values))

    # this should work when we figure out a jax version of xr.DataArray
    sim_data.get_intensity(mnt_name)
    # ret_value += jnp.sum(jnp.array(mnt_data.flux().values))

    # FieldData (dipole)
    mnt_name = MNT_NAME + "4"
    mnt_data = sim_data[mnt_name]
    ret_value += jnp.sum(jnp.array(mnt_data.Ex.values))

    return ret_value


def test_run_flux(use_emulated_run):
    td.config.logging_level = "ERROR"

    def make_components(eps, size, vertices, base_eps_val):
        sim = make_sim(permittivity=eps, size=size, vertices=vertices, base_eps_val=base_eps_val)
        td.config.logging_level = "WARNING"
        sim = sim.updated_copy(
            sources=[
                td.PointDipole(
                    center=(0, 0, 0),
                    polarization="Ex",
                    source_time=td.GaussianPulse(freq0=2e14, fwidth=1e15),
                )
            ]
        )
        sim_data = run_local(sim, task_name="test", path=str(TMP_PATH / RUN_FILE))
        mnt_data = sim_data[MNT_NAME + "3"]
        flat_components = {}
        for key, fld in mnt_data.field_components.items():
            values = jnp.array(jax.lax.stop_gradient(fld.values))[:, 1, ...]
            values = values[:, None, ...]
            coords = dict(fld.coords).copy()
            coords["y"] = [0.0]
            if isinstance(fld, td.ScalarFieldDataArray):
                flat_components[key] = td.ScalarFieldDataArray(values, coords=coords)
            else:
                flat_components[key] = fld.updated_copy(values=values, coords=coords)
        return mnt_data.updated_copy(**flat_components)

    mnt_data = make_components(EPS, SIZE, VERTICES, BASE_EPS_VAL)

    # whether to run the flux pipeline through jax (True) or regular tidy3d (False)
    use_jax = True
    if not use_jax:
        td_field_components = {}
        for fld, jax_data_array in mnt_data.field_components.items():
            data_array = td.ScalarFieldDataArray(
                np.array(jax_data_array.values), coords=jax_data_array.coords
            )
            td_field_components[fld] = data_array

        mnt_data = td.FieldData(monitor=mnt_data.monitor, **td_field_components)

    def get_flux(x):
        fld_components = {}
        for fld, fld_component in mnt_data.field_components.items():
            new_values = x * fld_component.values
            if isinstance(fld_component, td.ScalarFieldDataArray):
                fld_data = td.ScalarFieldDataArray(new_values, coords=fld_component.coords)
            else:
                fld_data = fld_component.updated_copy(values=new_values)
            fld_components[fld] = fld_data

        mnt_data2 = mnt_data.updated_copy(**fld_components)

        return jnp.sum(mnt_data2.flux)

    _ = get_flux(1.0)

    if use_jax:
        get_flux_grad = jax.grad(get_flux)
        _ = get_flux_grad(1.0)


@pytest.mark.xfail(reason="Gradients changed due to new input structures in pre/2.7")
@pytest.mark.parametrize("local", (True, False))
def test_adjoint_pipeline(local, use_emulated_run, tmp_path):
    """Test computing gradient using jax."""

    td.config.logging_level = "ERROR"

    run_fn = run_local if local else run

    sim = make_sim(permittivity=EPS, size=SIZE, vertices=VERTICES, base_eps_val=BASE_EPS_VAL)
    _ = run_fn(sim, task_name="test", path=str(tmp_path / RUN_FILE))

    def f(permittivity, size, vertices, base_eps_val):
        sim = make_sim(
            permittivity=permittivity, size=size, vertices=vertices, base_eps_val=base_eps_val
        )
        sim_data = run_fn(sim, task_name="test", path=str(tmp_path / RUN_FILE))
        amp = extract_amp(sim_data)
        return objective(amp)

    grad_f = grad(f, argnums=(0, 1, 2, 3))
    df_deps, df_dsize, df_dvertices, d_eps_base = grad_f(EPS, SIZE, VERTICES, BASE_EPS_VAL)

    # fail if all gradients close to zero
    assert not all(
        np.all(np.isclose(x, 0)) for x in (df_deps, df_dsize, df_dvertices, d_eps_base)
    ), "No gradients registered"

    # fail if any gradients close to zero
    assert not any(
        np.any(np.isclose(x, 0)) for x in (df_deps, df_dsize, df_dvertices, d_eps_base)
    ), "Some of the gradients are zero unexpectedly."

    # fail if some gradients dont match the pre/2.6 grads (before refactor).
    if local:
        assert np.isclose(df_deps, 1284453200000000.0), "local grad doesn't match previous value."
    else:
        assert np.isclose(df_deps, 0.031678755), "non-local grad doesn't match previous value."

    print("gradient: ", df_deps, df_dsize, df_dvertices, d_eps_base)


@pytest.mark.parametrize("local", (True, False))
def test_adjoint_pipeline_2d(local, use_emulated_run):
    run_fn = run_local if local else run

    sim = make_sim(permittivity=EPS, size=SIZE, vertices=VERTICES, base_eps_val=BASE_EPS_VAL)

    sim_size_2d = list(sim.size)
    sim_size_2d[1] = 0
    sim = sim.updated_copy(size=sim_size_2d)

    _ = run_fn(sim, task_name="test", path=str(TMP_PATH / RUN_FILE))

    def f(permittivity, size, vertices, base_eps_val):
        sim = make_sim(
            permittivity=permittivity, size=size, vertices=vertices, base_eps_val=base_eps_val
        )
        sim_size_2d = list(sim.size)
        sim_size_2d[1] = 0

        sim = sim.updated_copy(size=sim_size_2d)

        sim_data = run_fn(sim, task_name="test", path=str(TMP_PATH / RUN_FILE))
        amp = extract_amp(sim_data)
        return objective(amp)

    grad_f = grad(f, argnums=(0, 1, 2, 3))
    df_deps, df_dsize, df_dvertices, d_eps_base = grad_f(EPS, SIZE, VERTICES, BASE_EPS_VAL)


def test_adjoint_setup_fwd(use_emulated_run):
    """Test that the forward pass works as expected."""
    sim = make_sim(permittivity=EPS, size=SIZE, vertices=VERTICES, base_eps_val=BASE_EPS_VAL)
    sim_data_orig, (task_id_fwd) = run.fwd(
        simulation=sim,
        task_name="test",
        folder_name="default",
        path=str(TMP_PATH / RUN_FILE),
        callback_url=None,
        verbose=False,
    )


def _test_adjoint_setup_adj(use_emulated_run):
    """Test that the adjoint pass works as expected."""
    sim_orig = make_sim(permittivity=EPS, size=SIZE, vertices=VERTICES, base_eps_val=BASE_EPS_VAL)

    # call forward pass
    sim_data_fwd, (sim_data_fwd,) = run.fwd(
        simulation=sim_orig,
        task_name="test",
        folder_name="default",
        path=str(TMP_PATH / RUN_FILE),
        callback_url=None,
    )

    # create some contrived vjp sim_data to be able to call backward pass
    sim_data_vjp = sim_data_fwd.copy()
    output_data_vjp = []
    for mode_data in sim_data_vjp.output_data:
        new_values = 0 * np.array(mode_data.amps.values)
        new_values[0, 0, 0] = 1 + 1j
        amps_vjp = mode_data.amps.copy(update=dict(values=new_values.tolist()))
        mode_data_vjp = mode_data.copy(update=dict(amps=amps_vjp))
        output_data_vjp.append(mode_data_vjp)
    sim_data_vjp = sim_data_vjp.copy(update=dict(output_data=output_data_vjp))
    (sim_vjp,) = run.bwd(
        task_name="test",
        folder_name="default",
        path=str(TMP_PATH / RUN_FILE),
        callback_url=None,
        res=(sim_data_fwd,),
        sim_data_vjp=sim_data_vjp,
    )

    # check the lengths of various tuples are correct
    assert len(sim_vjp.monitors) == len(sim_orig.monitors)
    assert len(sim_vjp.structures) == len(sim_orig.structures)
    assert len(sim_vjp.input_structures) == len(sim_orig.input_structures)


def test_multiple_freqs():
    """Test that sim validation doesnt fail when output monitors have multiple frequencies."""

    output_mnt = td.ModeMonitor(
        size=(10, 10, 0),
        mode_spec=td.ModeSpec(num_modes=3),
        freqs=[1e14, 2e14],
        name=MNT_NAME,
    )

    _ = JaxSimulation(
        size=(10, 10, 10),
        run_time=SIM_RUN_TIME,
        grid_spec=td.GridSpec(wavelength=1.0),
        monitors=(),
        structures=(),
        output_monitors=(output_mnt,),
        input_structures=(),
    )


def test_different_freqs():
    """Test that sim validation doesnt fail when output monitors have different frequencies."""

    output_mnt1 = td.ModeMonitor(
        size=(10, 10, 0),
        mode_spec=td.ModeSpec(num_modes=3),
        freqs=[1e14],
        name=MNT_NAME + "1",
    )
    output_mnt2 = td.ModeMonitor(
        size=(10, 10, 0),
        mode_spec=td.ModeSpec(num_modes=3),
        freqs=[2e14],
        name=MNT_NAME + "2",
    )
    _ = JaxSimulation(
        size=(10, 10, 10),
        run_time=SIM_RUN_TIME,
        grid_spec=td.GridSpec(wavelength=1.0),
        monitors=(),
        structures=(),
        output_monitors=(output_mnt1, output_mnt2),
        input_structures=(),
    )


def test_get_freq_adjoint():
    """Test that the adjoint frequency property works as expected."""

    sim = JaxSimulation(
        size=(10, 10, 10),
        run_time=SIM_RUN_TIME,
        grid_spec=td.GridSpec(wavelength=1.0),
        monitors=(),
        structures=(),
        output_monitors=(),
        input_structures=(),
    )

    with pytest.raises(AdjointError):
        _ = sim.freqs_adjoint

    freq0 = 2e14
    freq1 = 3e14
    freq2 = 1e14
    output_mnt1 = td.ModeMonitor(
        size=(10, 10, 0),
        mode_spec=td.ModeSpec(num_modes=3),
        freqs=[freq0],
        name=MNT_NAME + "1",
    )
    output_mnt2 = td.ModeMonitor(
        size=(10, 10, 0),
        mode_spec=td.ModeSpec(num_modes=3),
        freqs=[freq1, freq2, freq0],
        name=MNT_NAME + "2",
    )
    sim = JaxSimulation(
        size=(10, 10, 10),
        run_time=SIM_RUN_TIME,
        grid_spec=td.GridSpec(wavelength=1.0),
        monitors=(),
        structures=(),
        output_monitors=(output_mnt1, output_mnt2),
        input_structures=(),
    )

    freqs = [freq0, freq1, freq2]
    freqs.sort()

    assert sim.freqs_adjoint == freqs


def test_get_fwidth_adjoint():
    """Test that the adjoint fwidth property works as expected."""

    from tidy3d.plugins.adjoint.components.simulation import FWIDTH_FACTOR

    freq0 = 2e14
    mnt = td.ModeMonitor(
        size=(10, 10, 0),
        mode_spec=td.ModeSpec(num_modes=3),
        freqs=[freq0],
        name=MNT_NAME + "1",
    )

    def make_sim(sources=(), fwidth_adjoint=None):
        """Make a sim with given sources and fwidth_adjoint specified."""
        return JaxSimulation(
            size=(10, 10, 10),
            run_time=SIM_RUN_TIME,
            grid_spec=td.GridSpec(wavelength=1.0),
            monitors=(),
            structures=(),
            output_monitors=(mnt,),
            input_structures=(),
            sources=sources,
            fwidth_adjoint=fwidth_adjoint,
        )

    # no sources, use FWIDTH * freq0
    sim = make_sim(sources=(), fwidth_adjoint=None)
    assert np.isclose(sim._fwidth_adjoint, FWIDTH_FACTOR * freq0)

    # a few sources, use average of fwidths
    fwidths = [1e14, 2e14, 3e14, 4e14]
    src_times = [td.GaussianPulse(freq0=freq0, fwidth=fwidth) for fwidth in fwidths]
    srcs = [td.PointDipole(source_time=src_time, polarization="Ex") for src_time in src_times]
    sim = make_sim(sources=srcs, fwidth_adjoint=None)
    assert np.isclose(sim._fwidth_adjoint, np.max(fwidths))

    # a few sources, with custom fwidth specified
    fwidth_custom = 3e13
    sim = make_sim(sources=srcs, fwidth_adjoint=fwidth_custom)
    assert np.isclose(sim._fwidth_adjoint, fwidth_custom)

    # no sources, custom fwidth specified
    sim = make_sim(sources=(), fwidth_adjoint=fwidth_custom)
    assert np.isclose(sim._fwidth_adjoint, fwidth_custom)


def test_jax_data_array():
    """Test mechanics of the JaxDataArray."""

    a = [1, 2, 3]
    b = [2, 3]
    c = [4]
    values = np.random.random((len(a), len(b), len(c)))
    coords = dict(a=a, b=b, c=c)

    # validate missing coord
    # with pytest.raises(AdjointError):
    # da = JaxDataArray(values=values, coords=dict(a=a, b=b))

    # validate coords in wrong order
    # with pytest.raises(AdjointError):
    # da = JaxDataArray(values=values, coords=dict(c=c, b=b, a=a))

    # creation
    da = JaxDataArray(values=values, coords=coords)
    _ = da.real
    _ = da.imag
    _ = da.as_list

    # isel multi
    z = da.isel(a=1, b=[0, 1], c=0)
    assert z.shape == (2,)

    # isel
    z = da.isel(a=1, b=1, c=0)
    z = da.isel(c=0, b=1, a=1)

    # sel
    z = da.sel(a=1, b=2, c=4)
    z = da.sel(c=4, b=2, a=1)

    # isel and sel
    z = da.sel(c=4, b=2).isel(a=0)
    z = da.isel(c=0, b=1).sel(a=1)

    # errors if coordinate not in data
    with pytest.raises(Tidy3dKeyError):
        da.sel(d=1)

    # errors if index out of range
    with pytest.raises(DataError):
        da.isel(c=1)
    with pytest.raises(DataError):
        da.isel(c=-1)
    with pytest.raises(DataError):
        da.sel(c=5)

    # not implemented
    # with pytest.raises(NotImplementedError):
    da.interp(b=2.5)

    assert np.isclose(da.interp(a=2, b=3, c=4), values[1, 1, 0])
    assert np.isclose(da.interp(a=1, b=2, c=4), values[0, 0, 0])

    with pytest.raises(Tidy3dKeyError):
        da.interp(d=3)

    da1d = JaxDataArray(values=[0.0, 1.0, 2.0, 3.0], coords=dict(x=[0, 1, 2, 3]))
    assert np.isclose(da1d.interp(x=0.5), 0.5)

    # duplicate coordinates
    sel_a_coords = [1, 2, 3, 2, 1]
    res = da.sel(a=sel_a_coords)
    assert res.coords["a"] == sel_a_coords
    assert res.values.shape[0] == len(sel_a_coords)

    a = [1, 2, 3]
    b = [2, 3, 4, 5]
    c = [4, 6]
    shape = (len(a), len(b), len(c))
    values = np.random.random(shape)
    coords = dict(a=a, b=b, c=c)
    da = JaxDataArray(values=values, coords=coords)
    da2 = da.sel(b=[3, 4])
    assert da2.shape == (3, 2, 2)

    da3 = da.interp(b=np.array([3, 4]))
    assert da3.shape == (3, 2, 2)

    assert da2 == da3

    n = 11
    cs = list(range(n))
    vals = np.random.uniform(0, 1, (n, n, 1, 1, 2))
    coords = dict(x=cs, y=cs, z=[0], f=[0], direction=["+", "-"])

    jda = JaxDataArray(values=vals, coords=coords)
    xda = DataArray(data=vals, coords=coords)

    # test exact, single value, non-numeric
    xda_vals = xda.sel(direction="+", method=None).values
    jda_vals = jda.sel(direction="+", method=None).values
    assert_allclose(xda_vals, jda_vals)

    # test exact, single value, 1d coordinate
    xda_vals = xda.sel(f=0, method=None).values
    jda_vals = jda.sel(f=0, method=None).values
    assert_allclose(xda_vals, jda_vals)

    # test exact, single value, 1d coordinate as list
    xda_vals = xda.sel(f=[0], method=None).values
    jda_vals = jda.sel(f=[0], method=None).values
    assert_allclose(xda_vals, jda_vals)

    # # disabled because it fails on xarray's side
    # # test nearest, single value, non-numeric
    # xda_vals = xda.sel(direction="+", method="nearest").values
    # jda_vals = jda.sel(direction="+", method="nearest").values
    # assert_allclose(xda_vals, jda_vals)

    # test exact, multiple values, non-numeric
    xda_vals = xda.sel(direction=["+", "-"], method=None).values
    jda_vals = jda.sel(direction=["+", "-"], method=None).values
    assert_allclose(xda_vals, jda_vals)

    # test nearest, single value
    xda_vals = xda.sel(x=0.1, method="nearest").values
    jda_vals = jda.sel(x=0.1, method="nearest").values
    assert_allclose(xda_vals, jda_vals)

    # test nearest, single value, 1d coordinate
    xda_vals = xda.sel(f=0.1, method="nearest").values
    jda_vals = jda.sel(f=0.1, method="nearest").values
    assert_allclose(xda_vals, jda_vals)

    # test nearest, single value, 1d coordinate as list
    xda_vals = xda.sel(f=[0.1], method="nearest").values
    jda_vals = jda.sel(f=[0.1], method="nearest").values
    assert_allclose(xda_vals, jda_vals)

    # test nearest, multiple values
    xda_vals = xda.sel(x=[0.0, 0.1, 0.3], method="nearest").values
    jda_vals = jda.sel(x=[0.0, 0.1, 0.3], method="nearest").values
    assert_allclose(xda_vals, jda_vals)

    # test nearest, multiple coords, single value
    xda_vals = xda.sel(x=0.1, y=-0.3, method="nearest").values
    jda_vals = jda.sel(x=0.1, y=-0.3, method="nearest").values
    assert_allclose(xda_vals, jda_vals)

    # test nearest, multiple coords, multiple values
    xda_vals = xda.sel(x=[-1.5, 0.1], y=[-0.3, 0.0, 0.9], method="nearest").values
    jda_vals = jda.sel(x=[-1.5, 0.1], y=[-0.3, 0.0, 0.9], method="nearest").values
    assert_allclose(xda_vals, jda_vals)

    # test nearest, multiple coords, duplicate values
    xda_vals = xda.sel(x=[-1.5, 0.2, 0.1, -1.5, 0.2], y=[-0.3, 0.0, 0.9], method="nearest")
    jda_vals = jda.sel(x=[-1.5, 0.2, 0.1, -1.5, 0.2], y=[-0.3, 0.0, 0.9], method="nearest")
    assert_allclose(xda_vals.values, jda_vals.values)
    assert_allclose(xda_vals.coords["x"], jda_vals.coords["x"])


def test_jax_sim_data(use_emulated_run):
    """Test mechanics of the JaxSimulationData."""

    sim = make_sim(permittivity=EPS, size=SIZE, vertices=VERTICES, base_eps_val=BASE_EPS_VAL)
    sim_data = run(sim, task_name="test", path=str(TMP_PATH / RUN_FILE))

    for i in range(len(sim.output_monitors)):
        mnt_name = MNT_NAME + str(i + 1)
        _ = sim_data.output_data[i]
        _ = sim_data.output_monitor_data[mnt_name]
        _ = sim_data[mnt_name]


def test_intersect_structures(log_capture):
    """Test validators for structures touching and intersecting."""

    SIZE_X = 1.0
    OVERLAP = 1e-4

    def make_sim_intersect(spacing: float, is_vjp: bool = False) -> JaxSimulation:
        """Make a sim with two boxes spaced by some variable amount."""
        box1 = JaxBox(center=(-SIZE_X / 2 - spacing / 2, 0, 0), size=(SIZE_X, 1, 1))
        box2 = JaxBox(center=(+SIZE_X / 2 + spacing / 2, 0, 0), size=(SIZE_X, 1, 1))
        medium = JaxMedium(permittivity=2.0)
        struct1 = JaxStructure(geometry=box1, medium=medium)
        struct2 = JaxStructure(geometry=box2, medium=medium)
        src = td.PointDipole(
            source_time=td.GaussianPulse(freq0=2e14, fwidth=1e13),
            polarization="Ex",
        )
        return JaxSimulation(
            size=(2, 2, 2),
            input_structures=(struct1, struct2),
            grid_spec=td.GridSpec(wavelength=1.0),
            run_time=SIM_RUN_TIME,
            sources=(src,),
            boundary_spec=td.BoundarySpec.pml(x=True, y=True, z=True),
        )

    # shouldnt error, boxes spaced enough
    _ = make_sim_intersect(spacing=+OVERLAP)

    # shouldnt error, just warn because of touching but not intersecting
    _ = make_sim_intersect(spacing=0.0)
    assert_log_level(log_capture, "WARNING")


def test_structure_overlaps():
    """Test weird overlap edge cases, eg with box out of bounds and 2D sim."""

    box = JaxBox(center=(0, 0, 0), size=(td.inf, 2, 1))
    medium = JaxMedium(permittivity=2.0)
    struct = JaxStructure(geometry=box, medium=medium)
    src = td.PointDipole(
        source_time=td.GaussianPulse(freq0=2e14, fwidth=1e13),
        polarization="Ex",
    )

    _ = JaxSimulation(
        size=(2, 0, 2),
        input_structures=(struct,),
        grid_spec=td.GridSpec(wavelength=1.0),
        run_time=SIM_RUN_TIME,
        sources=(src,),
        boundary_spec=td.BoundarySpec(
            x=td.Boundary.pml(),
            y=td.Boundary.periodic(),
            z=td.Boundary.pml(),
        ),
    )


def test_validate_subpixel():
    """Make sure errors if subpixel is off."""
    with pytest.raises(pydantic.ValidationError):
        _ = JaxSimulation(
            size=(10, 10, 10),
            run_time=SIM_RUN_TIME,
            grid_spec=td.GridSpec(wavelength=1.0),
            subpixel=False,
        )


# def test_validate_3D_geometry():
#     """Make sure it errors if the size of a JaxBox is 1d or 2d."""

#     b = JaxBox(center=(0,0,0), size=(1,1,1))

#     with pytest.raises(AdjointError):
#         b = JaxBox(center=(0,0,0), size=(0,1,1))

#     with pytest.raises(AdjointError):
#         b = JaxBox(center=(0,0,0), size=(0,1,0))

#     p = JaxPolySlab(vertices=VERTICES, axis=2, slab_bounds=(0,1))

#     with pytest.raises(AdjointError):
#         p = JaxPolySlab(vertices=VERTICES, axis=2, slab_bounds=(0,0))


def test_plot_sims():
    """Make sure plotting functions without erroring."""

    sim = JaxSimulation(
        size=(10, 10, 10),
        run_time=SIM_RUN_TIME,
        grid_spec=td.GridSpec(wavelength=1.0),
    )
    sim.plot(x=0)
    plt.close()
    sim.plot_eps(x=0)
    plt.close()


def test_flip_direction():
    """Make sure flip direction fails when direction happens to neither be '+' nor '-'"""
    with pytest.raises(AdjointError):
        JaxModeData.flip_direction("NOT+OR-")


def test_strict_types():
    """Test that things fail if you try to use just any object in a Jax component."""
    with pytest.raises(pydantic.ValidationError):
        _ = JaxBox(size=(1, 1, [1, 2]), center=(0, 0, 0))


def _test_polyslab_box(use_emulated_run):
    """Make sure box made with polyslab gives equivalent gradients.
    Note: doesn't pass now since JaxBox samples the permittivity inside and outside the box,
    and a random permittivity data is created by the emulated run function. JaxPolySlab just
    uses the slab permittivity and the background simulation permittivity."""

    np.random.seed(0)

    def f(size, center, is_box=True):
        jax_med = JaxMedium(permittivity=2.0)
        POLYSLAB_AXIS = 2

        if is_box:
            size = list(size)
            size[POLYSLAB_AXIS] = jax.lax.stop_gradient(size[POLYSLAB_AXIS])
            center = list(center)
            center[POLYSLAB_AXIS] = jax.lax.stop_gradient(center[POLYSLAB_AXIS])

            # JaxBox
            jax_box = JaxBox(size=size, center=center)
            jax_struct = JaxStructure(geometry=jax_box, medium=jax_med)

        else:
            size_axis, (size_1, size_2) = JaxPolySlab.pop_axis(size, axis=POLYSLAB_AXIS)
            cent_axis, (cent_1, cent_2) = JaxPolySlab.pop_axis(center, axis=POLYSLAB_AXIS)

            pos_x2 = cent_1 + size_1 / 2.0
            pos_x1 = cent_1 - size_1 / 2.0
            pos_y1 = cent_2 - size_2 / 2.0
            pos_y2 = cent_2 + size_2 / 2.0

            vertices = ((pos_x1, pos_y1), (pos_x2, pos_y1), (pos_x2, pos_y2), (pos_x1, pos_y2))
            slab_bounds = (cent_axis - size_axis / 2, cent_axis + size_axis / 2)
            slab_bounds = tuple(jax.lax.stop_gradient(x) for x in slab_bounds)
            jax_polyslab = JaxPolySlab(
                vertices=vertices, axis=POLYSLAB_AXIS, slab_bounds=slab_bounds
            )
            jax_struct = JaxStructure(geometry=jax_polyslab, medium=jax_med)

        # ModeMonitors
        output_mnt1 = td.ModeMonitor(
            size=(td.inf, td.inf, 0),
            mode_spec=td.ModeSpec(num_modes=3),
            freqs=[2e14],
            name=MNT_NAME + "1",
        )

        # DiffractionMonitor
        output_mnt2 = td.DiffractionMonitor(
            center=(0, 0, 4),
            size=(td.inf, td.inf, 0),
            normal_dir="+",
            freqs=[2e14],
            name=MNT_NAME + "2",
        )

        sim = JaxSimulation(
            size=(10, 10, 10),
            run_time=SIM_RUN_TIME,
            grid_spec=td.GridSpec(wavelength=1.0),
            boundary_spec=td.BoundarySpec.all_sides(boundary=td.Periodic()),
            output_monitors=(output_mnt1, output_mnt2),
            input_structures=(jax_struct,),
            sources=[
                td.PointDipole(
                    source_time=td.GaussianPulse(freq0=1e14, fwidth=1e14),
                    center=(0, 0, 0),
                    polarization="Ex",
                )
            ],
        )

        sim_data = run(sim, task_name="test")
        amp = extract_amp(sim_data)
        return objective(amp)

    f_b = lambda size, center: f(size, center, is_box=True)
    f_p = lambda size, center: f(size, center, is_box=False)

    g_b = grad(f_b, argnums=(0, 1))
    g_p = grad(f_p, argnums=(0, 1))

    gs_b, gc_b = g_b(SIZE, CENTER)
    gs_p, gc_p = g_p(SIZE, CENTER)

    gs_b, gc_b, gs_p, gc_p = map(np.array, (gs_b, gc_b, gs_p, gc_p))

    print("grad_size_box  = ", gs_b)
    print("grad_size_poly = ", gs_p)
    print("grad_cent_box  = ", gc_b)
    print("grad_cent_poly = ", gc_p)

    print(gs_b / (gs_p + 1e-12))
    print(gc_b / (gc_p + 1e-12))

    assert np.allclose(gs_b, gs_p), f"size gradients dont match, got {gs_b} and {gs_p}"
    assert np.allclose(gc_b, gc_p), f"center gradients dont match, got {gc_b} and {gc_p}"


@pytest.mark.parametrize("sim_size_axis", [0, 10])
def test_polyslab_2d(sim_size_axis, use_emulated_run):
    """Make sure box made with polyslab gives equivalent gradients (note, doesn't pass now)."""

    np.random.seed(0)

    def f(size, center):
        jax_med = JaxMedium(permittivity=2.0)
        POLYSLAB_AXIS = 2

        size_axis, (size_1, size_2) = JaxPolySlab.pop_axis(size, axis=POLYSLAB_AXIS)
        cent_axis, (cent_1, cent_2) = JaxPolySlab.pop_axis(center, axis=POLYSLAB_AXIS)

        pos_x2 = cent_1 + size_1 / 2.0
        pos_x1 = cent_1 - size_1 / 2.0
        pos_y1 = cent_2 - size_2 / 2.0
        pos_y2 = cent_2 + size_2 / 2.0

        vertices = ((pos_x1, pos_y1), (pos_x2, pos_y1), (pos_x2, pos_y2), (pos_x1, pos_y2))
        slab_bounds = (cent_axis - size_axis / 2, cent_axis + size_axis / 2)
        slab_bounds = tuple(jax.lax.stop_gradient(x) for x in slab_bounds)
        jax_polyslab = JaxPolySlab(vertices=vertices, axis=POLYSLAB_AXIS, slab_bounds=slab_bounds)
        jax_struct = JaxStructure(geometry=jax_polyslab, medium=jax_med)

        # ModeMonitors
        output_mnt1 = td.ModeMonitor(
            size=(td.inf, td.inf, 0),
            mode_spec=td.ModeSpec(num_modes=3),
            freqs=[2e14],
            name=MNT_NAME + "1",
        )

        # DiffractionMonitor
        output_mnt2 = td.DiffractionMonitor(
            center=(0, 4, 0),
            size=(td.inf, 0, td.inf),
            normal_dir="+",
            freqs=[2e14],
            name=MNT_NAME + "2",
        )

        output_mnt3 = td.FieldMonitor(
            size=(2, 0, 2),
            freqs=[FREQ0],
            name=MNT_NAME + "3",
        )

        output_mnt4 = td.FieldMonitor(
            size=(0, 0, 0),
            freqs=[FREQ0],
            name=MNT_NAME + "4",
        )

        sim = JaxSimulation(
            size=(10, 10, sim_size_axis),
            run_time=SIM_RUN_TIME,
            grid_spec=td.GridSpec(wavelength=1.0),
            boundary_spec=td.BoundarySpec.all_sides(boundary=td.Periodic()),
            output_monitors=(output_mnt1, output_mnt2, output_mnt3, output_mnt4),
            input_structures=(jax_struct,),
            sources=[
                td.PointDipole(
                    source_time=td.GaussianPulse(freq0=1e14, fwidth=1e14),
                    center=(0, 0, 0),
                    polarization="Ex",
                )
            ],
        )

        sim_data = run(sim, task_name="test")
        amp = extract_amp(sim_data)
        return objective(amp)

    f_b = lambda size, center: f(size, center)

    g_b = grad(f_b, argnums=(0, 1))

    gs_b, gc_b = g_b((1.0, 2.0, 100.0), CENTER)


@pytest.mark.parametrize("local", (True, False))
def test_adjoint_run_async(local, use_emulated_run_async):
    """Test differnetiating thorugh async adjoint runs"""

    run_fn = run_async_local if local else run_async

    def make_sim_simple(permittivity: float) -> JaxSimulation:
        """Make a sim as a function of a single parameter."""
        return make_sim(
            permittivity=permittivity, size=SIZE, vertices=VERTICES, base_eps_val=BASE_EPS_VAL
        )

    def f(x):
        """Objective function to differentiate."""

        sims = [make_sim_simple(permittivity=x + 1.0)]
        sim_data_list = run_fn(sims, path_dir=str(TMP_PATH))

        result = 0.0
        for sim_data in sim_data_list:
            amp = extract_amp(sim_data)
            result += objective(amp)

        return result

    # test evaluating the function
    x0 = 1.0
    # f0 = await f(x0)

    # and its derivatve
    _ = f(x0)
    g = jax.grad(f)
    _ = g(x0)


@pytest.mark.parametrize("axis", (0, 1, 2))
def test_diff_data_angles(axis):
    center = td.DiffractionMonitor.unpop_axis(2, (0, 0), axis)
    size = td.DiffractionMonitor.unpop_axis(0, (td.inf, td.inf), axis)

    SIZE_2D = 1.0
    ORDERS_X = [-1, 0, 1]
    ORDERS_Y = [-1, 0, 1]
    FS = [2e14]

    DIFFRACTION_MONITOR = td.DiffractionMonitor(
        center=center,
        size=size,
        freqs=FS,
        name="diffraction",
    )

    values = (1 + 1j) * np.random.random((len(ORDERS_X), len(ORDERS_Y), len(FS)))
    sim_size = [SIZE_2D, SIZE_2D]
    bloch_vecs = [0, 0]
    data = JaxDataArray(values=values, coords=dict(orders_x=ORDERS_X, orders_y=ORDERS_Y, f=FS))

    diff_data = JaxDiffractionData(
        monitor=DIFFRACTION_MONITOR,
        Etheta=data,
        Ephi=data,
        Er=data,
        Htheta=data,
        Hphi=data,
        Hr=data,
        sim_size=sim_size,
        bloch_vecs=bloch_vecs,
    )

    thetas, phis = diff_data.angles
    zeroth_order_theta = thetas.sel(orders_x=0, orders_y=0).isel(f=0)

    assert np.isclose(zeroth_order_theta, 0.0)


def _test_error_regular_web():
    """Test that a custom error is raised if running tidy3d through web.run()"""

    sim = make_sim(permittivity=EPS, size=SIZE, vertices=VERTICES, base_eps_val=BASE_EPS_VAL)
    import tidy3d.web as web

    with pytest.raises(ValueError):
        web.run(sim, task_name="test")


def test_value_filter():
    """Ensure value filter works as expected."""

    values = np.array([1, 0.5 * VALUE_FILTER_THRESHOLD, 2 * VALUE_FILTER_THRESHOLD, 0])
    coords = dict(x=list(range(4)))
    data = JaxDataArray(values=values, coords=coords)

    values_after, _ = data.nonzero_val_coords

    # assert that the terms <= VALUE_FILTER_THRESHOLD should be removed
    values_expected = np.array([1, 2 * VALUE_FILTER_THRESHOLD])
    assert np.allclose(np.array(values_after), values_expected)


def test_jax_info_to_file(tmp_path):
    """Test writing jax info to file."""

    sim = make_sim(permittivity=EPS, size=SIZE, vertices=VERTICES, base_eps_val=BASE_EPS_VAL)
    _, jax_info = sim.to_simulation()
    jax_info.to_file(str(tmp_path / "jax_info.json"))


def test_split_fwd_sim_data(tmp_path):
    """Test splitting of regular simulation data into user and server data."""

    jax_sim = make_sim(permittivity=EPS, size=SIZE, vertices=VERTICES, base_eps_val=BASE_EPS_VAL)
    sim, jax_info = jax_sim.to_simulation()
    sim_data = run_emulated(sim, task_name="test", path=str(tmp_path / "simulation_data.hdf5"))
    data_user, data_adj = JaxSimulationData.split_fwd_sim_data(sim_data=sim_data, jax_info=jax_info)


def test_save_load_simdata(use_emulated_run, tmp_path):
    """Make sure a simulation data can be saved and loaded from file and retain info."""

    sim = make_sim(permittivity=EPS, size=SIZE, vertices=VERTICES, base_eps_val=BASE_EPS_VAL)
    sim_data = run(sim, task_name="test", path=str(TMP_PATH / RUN_FILE))
    sim_data.to_file(str(tmp_path / "adjoint_simdata.hdf5"))
    sim_data2 = JaxSimulationData.from_file(str(tmp_path / "adjoint_simdata.hdf5"))
    assert sim_data == sim_data2


def _test_polyslab_scale(use_emulated_run):
    """Make sure box made with polyslab gives equivalent gradients (note, doesn't pass now)."""

    nums = np.logspace(np.log10(3), 3, 13)
    times = []
    for num_vertices in nums:
        num_vertices = int(num_vertices)

        angles = 2 * np.pi * np.arange(num_vertices) / num_vertices
        xs = np.cos(angles)
        ys = np.sin(angles)
        vertices = np.stack((xs, ys), axis=1).tolist()
        np.random.seed(0)
        start_time = time.time()

        def f(scale=1.0, vertices=vertices):
            jax_med = JaxMedium(permittivity=2.0)
            POLYSLAB_AXIS = 2

            size_axis, (size_1, size_2) = JaxPolySlab.pop_axis(SIZE, axis=POLYSLAB_AXIS)
            cent_axis, (cent_1, cent_2) = JaxPolySlab.pop_axis(CENTER, axis=POLYSLAB_AXIS)

            vertices_jax = [(scale * x, scale * y) for x, y in vertices]
            # vertices_jax = [(x, y) for x, y in vertices]

            slab_bounds = (cent_axis - size_axis / 2, cent_axis + size_axis / 2)
            slab_bounds = tuple(jax.lax.stop_gradient(x) for x in slab_bounds)
            jax_polyslab = JaxPolySlab(
                vertices=vertices_jax, axis=POLYSLAB_AXIS, slab_bounds=slab_bounds
            )
            jax_struct = JaxStructure(geometry=jax_polyslab, medium=jax_med)

            # ModeMonitors
            output_mnt1 = td.ModeMonitor(
                size=(td.inf, td.inf, 0),
                mode_spec=td.ModeSpec(num_modes=3),
                freqs=[2e14],
                name=MNT_NAME + "1",
            )

            # DiffractionMonitor
            output_mnt2 = td.DiffractionMonitor(
                center=(0, 4, 0),
                size=(td.inf, 0, td.inf),
                normal_dir="+",
                freqs=[2e14],
                name=MNT_NAME + "2",
            )

            sim = JaxSimulation(
                size=(10, 10, 10),
                run_time=SIM_RUN_TIME,
                grid_spec=td.GridSpec(wavelength=1.0),
                boundary_spec=td.BoundarySpec.all_sides(boundary=td.Periodic()),
                output_monitors=(output_mnt1, output_mnt2),
                input_structures=(jax_struct,),
                sources=[
                    td.PointDipole(
                        source_time=td.GaussianPulse(freq0=1e14, fwidth=1e14),
                        center=(0, 0, 0),
                        polarization="Ex",
                    )
                ],
            )

            sim_data = run(sim, task_name="test")
            amp = extract_amp(sim_data)
            return objective(amp)

        g = grad(f)

        _ = g(1.0)

        total_time = time.time() - start_time
        print(f"{num_vertices} vertices took {total_time:.2e} seconds")
        times.append(total_time)

    plt.plot(nums, times)
    plt.xlabel("number of vertices")
    plt.ylabel("time to compute gradient")
    plt.xscale("log")
    plt.yscale("log")
    plt.show()
    # plt.close()


def test_validate_vertices():
    """Test the maximum number of vertices."""

    def make_vertices(n: int) -> np.ndarray:
        """Make circular polygon vertices of shape (n, 2)."""
        angles = np.linspace(0, 2 * np.pi, n)
        return np.stack((np.cos(angles), np.sin(angles)), axis=-1)

    vertices_pass = make_vertices(MAX_NUM_VERTICES)
    ps = JaxPolySlab(vertices=vertices_pass, slab_bounds=(-1, 1))
    ps._validate_web_adjoint()

    vertices_fail = make_vertices(MAX_NUM_VERTICES + 1)
    ps = JaxPolySlab(vertices=vertices_fail, slab_bounds=(-1, 1))
    with pytest.raises(AdjointError):
        ps._validate_web_adjoint()


def _test_custom_medium_3D(use_emulated_run):
    """Ensure custom medium fails if 3D pixelated grid."""
    # NOTE: turned off since we relaxed this restriction

    jax_box = JaxBox(size=(1, 1, 1), center=(0, 0, 0))

    def make_custom_medium(Nx: int, Ny: int, Nz: int) -> JaxCustomMedium:
        # custom medium
        (xmin, ymin, zmin), (xmax, ymax, zmax) = jax_box.bounds
        coords = dict(
            x=np.linspace(xmin, xmax, Nx).tolist(),
            y=np.linspace(ymin, ymax, Ny).tolist(),
            z=np.linspace(zmin, zmax, Nz).tolist(),
            f=[FREQ0],
        )

        values = np.random.random((Nx, Ny, Nz, 1))
        eps_ii = JaxDataArray(values=values, coords=coords)
        field_components = {f"eps_{dim}{dim}": eps_ii for dim in "xyz"}
        jax_eps_dataset = JaxPermittivityDataset(**field_components)
        return JaxCustomMedium(eps_dataset=jax_eps_dataset)

    make_custom_medium(1, 1, 1)
    make_custom_medium(10, 1, 1)
    make_custom_medium(1, 10, 1)
    make_custom_medium(1, 1, 10)
    make_custom_medium(1, 10, 10)
    make_custom_medium(10, 1, 10)
    make_custom_medium(10, 10, 1)
    with pytest.raises(pydantic.ValidationError):
        make_custom_medium(10, 10, 10)


def test_custom_medium_size(use_emulated_run):
    """Ensure custom medium fails if too many cells provided."""

    jax_box = JaxBox(size=(1, 1, 1), center=(0, 0, 0))

    def make_custom_medium(num_cells: int) -> JaxCustomMedium:
        Nx = num_cells
        Ny = Nz = 1

        # custom medium
        (xmin, ymin, zmin), (xmax, ymax, zmax) = jax_box.bounds
        coords = dict(
            x=np.linspace(xmin, xmax, Nx).tolist(),
            y=np.linspace(ymin, ymax, Ny).tolist(),
            z=np.linspace(zmin, zmax, Nz).tolist(),
            f=[FREQ0],
        )

        values = np.random.random((Nx, Ny, Nz, 1))
        eps_ii = JaxDataArray(values=values, coords=coords)
        field_components = {f"eps_{dim}{dim}": eps_ii for dim in "xyz"}
        jax_eps_dataset = JaxPermittivityDataset(**field_components)
        return JaxCustomMedium(eps_dataset=jax_eps_dataset)

    med = make_custom_medium(num_cells=1)
    med._validate_web_adjoint()

    med = make_custom_medium(num_cells=MAX_NUM_CELLS_CUSTOM_MEDIUM)
    med._validate_web_adjoint()

    med = make_custom_medium(num_cells=MAX_NUM_CELLS_CUSTOM_MEDIUM + 1)
    with pytest.raises(td.exceptions.SetupError):
        med._validate_web_adjoint()


def test_jax_sim_io(tmp_path):
    jax_box = JaxBox(size=(1, 1, 1), center=(0, 0, 0))

    def make_custom_medium(num_cells: int) -> JaxCustomMedium:
        n = int(np.sqrt(num_cells))
        Nx = n
        Ny = n
        Nz = 1

        # custom medium
        (xmin, ymin, zmin), (xmax, ymax, zmax) = jax_box.bounds
        coords = dict(
            x=np.linspace(xmin, xmax, Nx).tolist(),
            y=np.linspace(ymin, ymax, Ny).tolist(),
            z=np.linspace(zmin, zmax, Nz).tolist(),
            f=[FREQ0],
        )

        values = np.random.random((Nx, Ny, Nz, 1)) + 1.0
        eps_ii = JaxDataArray(values=values, coords=coords)
        field_components = {f"eps_{dim}{dim}": eps_ii for dim in "xyz"}
        jax_eps_dataset = JaxPermittivityDataset(**field_components)
        return JaxCustomMedium(eps_dataset=jax_eps_dataset)

    num_cells = 200 * 200
    struct = JaxStructure(geometry=jax_box, medium=make_custom_medium(num_cells=num_cells))
    sim = JaxSimulation(
        size=(2, 2, 2),
        input_structures=[struct],
        run_time=SIM_RUN_TIME,
        grid_spec=td.GridSpec.auto(wavelength=1.0),
    )

    fname = str(tmp_path / "jax_sim_io_tmp.hdf5")
    sim.to_file(fname)

    with h5py.File(fname, "r") as f:
        assert "input_structures" in f.keys()
        json_string = str(f["JSON_STRING"][()])
        assert JAX_DATA_ARRAY_TAG in json_string

    sim2 = JaxSimulation.from_file(fname)

    assert sim == sim2


def test_num_input_structures(use_emulated_run, tmp_path, monkeypatch):
    """Assert proper error is raised if number of input structures is too large."""

    test_max_num_structs = 3  # monkeypatch for easier testing
    monkeypatch.setattr(simulation, "MAX_NUM_INPUT_STRUCTURES", test_max_num_structs)

    def make_sim_(permittivity=EPS, num_input_structures: int = 1) -> JaxSimulation:
        sim = make_sim(
            permittivity=permittivity, size=SIZE, vertices=VERTICES, base_eps_val=BASE_EPS_VAL
        )
        struct = sim.input_structures[0]
        return sim.updated_copy(input_structures=num_input_structures * [struct])

    sim = make_sim_(num_input_structures=test_max_num_structs)
    sim._validate_web_adjoint()

    sim = make_sim_(num_input_structures=test_max_num_structs + 1)
    with pytest.raises(AdjointError):
        sim._validate_web_adjoint()

    # make sure that the remote web API fails whereas the local one passes
    with pytest.raises(AdjointError):
        run(sim, task_name="test", path=str(tmp_path / RUN_FILE))

    # make sure it also errors in a gradient computation
    def f(permittivity):
        sim = make_sim_(permittivity=permittivity, num_input_structures=test_max_num_structs + 1)
        sim_data = run(sim, task_name="test", path=str(tmp_path / RUN_FILE))
        return objective(extract_amp(sim_data))

    with pytest.raises(AdjointError):
        _ = grad(f)(EPS)

    # no error when calling run_local directly
    run_local(sim, task_name="test", path=str(tmp_path / RUN_FILE))

    # no error when calling it inside a gradient computation
    def f(permittivity):
        sim = make_sim_(permittivity=permittivity, num_input_structures=test_max_num_structs + 1)
        sim_data = run_local(sim, task_name="test", path=str(tmp_path / RUN_FILE), num_proc=2)
        return objective(extract_amp(sim_data))

    _ = grad(f)(EPS)


@pytest.mark.parametrize("strict_binarize", (True, False))
def test_adjoint_utils(strict_binarize):
    """Test filtering, projection, and optimization routines."""

    sim = make_sim(permittivity=EPS, size=SIZE, vertices=VERTICES, base_eps_val=BASE_EPS_VAL)

    # projection / filtering
    image = sim.input_structures[2].medium.eps_dataset.eps_xx.values

    filter = ConicFilter(radius=1.5, design_region_dl=0.1)
    filter.evaluate(image)
    filter = CircularFilter(radius=1.5, design_region_dl=0.1)
    filter.evaluate(image)
    projector = BinaryProjector(vmin=1.0, vmax=2.0, beta=1.5, strict_binarize=strict_binarize)
    projector.evaluate(image)

    # radius of curvature

    polyslab = sim.input_structures[3].geometry

    radius_penalty = RadiusPenalty(min_radius=0.2, wrap=True)
    _ = radius_penalty.evaluate(polyslab.vertices)

    # erosion / dilation

    image_01 = np.random.random(image.shape)

    ed_penalty = ErosionDilationPenalty(
        length_scale=1.0, beta=10, pixel_size=0.01, eta0=0.45, delta_eta=0.02
    )

    val = ed_penalty.evaluate(image_01)
    assert val > 0


@pytest.mark.parametrize(
    "input_size_y, log_level_expected", [(13, None), (12, "WARNING"), (11, "WARNING"), (14, None)]
)
def test_adjoint_filter_sizes(log_capture, input_size_y, log_level_expected):
    """Warn if filter size along a dim is smaller than radius."""

    signal_in = np.ones((266, input_size_y))

    _filter = ConicFilter(radius=0.08, design_region_dl=0.015)
    _filter.evaluate(signal_in)

    assert_log_level(log_capture, log_level_expected)


def test_sim_data_plot_field(use_emulated_run):
    """Test splitting of regular simulation data into user and server data."""

    jax_sim = make_sim(permittivity=EPS, size=SIZE, vertices=VERTICES, base_eps_val=BASE_EPS_VAL)
    jax_sim_data = run(jax_sim, task_name="test")
    ax = jax_sim_data.plot_field("field", "Ez", "real", f=1e14)
    # plt.show()
    assert len(ax.collections) == 1


def test_pytreedef_errors(use_emulated_run):
    """Fix errors that occur when jax doesnt know how to handle array types in aux_data."""

    vertices = [(0, 0), (1, 0), (1, 1), (0, 1)]
    polyslab = td.PolySlab(vertices=vertices, slab_bounds=(0, 1), axis=2)
    ps = td.Structure(geometry=polyslab, medium=td.Medium())
    gg = td.Structure(
        geometry=td.GeometryGroup(geometries=[polyslab]),
        medium=td.Medium(),
    )
    ggg = td.Structure(
        geometry=td.GeometryGroup(geometries=[polyslab, td.GeometryGroup(geometries=[polyslab])]),
        medium=td.Medium(),
    )

    clip_operation = td.ClipOperation(
        operation="union", geometry_a=gg.geometry, geometry_b=ggg.geometry
    )
    gggg = td.Structure(
        geometry=clip_operation,
        medium=td.Medium(),
    )

    flux_mnt = td.FieldMonitor(
        center=(0, 0, 0),
        size=(1, 1, 0),
        freqs=1e14 * np.array([1, 2, 3]),  # this previously errored
        name="flux",
    )

    VERTICES = np.array(
        [[-1.5, -0.5, -0.5], [-0.5, -0.5, -0.5], [-1.5, 0.5, -0.5], [-1.5, -0.5, 0.5]]
    )
    FACES = np.array([[1, 2, 3], [0, 3, 2], [0, 1, 3], [0, 2, 1]])
    STL_GEO = td.TriangleMesh.from_trimesh(trimesh.Trimesh(VERTICES, FACES))

    custom_medium = td.Structure(
        geometry=td.Box(size=(1, 1, 1)),
        medium=CUSTOM_MEDIUM,
    )

    stl_struct = td.Structure(geometry=STL_GEO, medium=td.Medium())

    mnt = td.ModeMonitor(size=(1, 1, 0), freqs=[1e14], name="test", mode_spec=td.ModeSpec())

    def f(x):
        jb = JaxBox(size=(x, x, x), center=(0, 0, 0))
        js = JaxStructure(geometry=jb, medium=JaxMedium(permittivity=2.0))

        sim = JaxSimulation(
            size=(2.0, 2.0, 2.0),
            structures=[ps, gg, ggg, gggg, stl_struct, custom_medium],
            input_structures=[js],
            run_time=SIM_RUN_TIME,
            output_monitors=[mnt],
            monitors=[flux_mnt],
            grid_spec=td.GridSpec.uniform(dl=0.1),
            boundary_spec=td.BoundarySpec.pml(x=False, y=False, z=False),
        )

        sd = run(sim, task_name="test")

        return jnp.sum(jnp.abs(jnp.array(sd["test"].amps.values)))

    jax.grad(f)(0.5)


fwidth_run_time_expected = [
    (FREQ0 / 10, 1e-11, 1e-11),  # run time supplied explicitly, use that
    (
        FREQ0 / 10,
        None,
        SIM_RUN_TIME + RUN_TIME_FACTOR / (FREQ0 / 10),
    ),  # no run_time, use fwidth supplied
    (
        FREQ0 / 20,
        None,
        SIM_RUN_TIME + RUN_TIME_FACTOR / (FREQ0 / 20),
    ),  # no run_time, use fwidth supplied
]


@pytest.mark.parametrize("fwidth, run_time, run_time_expected", fwidth_run_time_expected)
def test_adjoint_run_time(use_emulated_run, tmp_path, fwidth, run_time, run_time_expected):
    sim = make_sim(permittivity=EPS, size=SIZE, vertices=VERTICES, base_eps_val=BASE_EPS_VAL)

    sim = sim.updated_copy(run_time_adjoint=run_time, fwidth_adjoint=fwidth)

    sim_data = run(sim, task_name="test", path=str(tmp_path / RUN_FILE))

    run_time_adj = sim._run_time_adjoint
    fwidth_adj = sim._fwidth_adjoint

    # number of adjoint time steps approximately scaled by the adjoint run_time compared to sim
    num_time_steps_adjoint = sim.num_time_steps_adjoint
    num_time_steps_scaled = sim.num_time_steps * (sim._run_time_adjoint / sim.run_time)
    assert np.isclose(num_time_steps_adjoint, num_time_steps_scaled, rtol=1e-2)

    sim_adj = sim_data.make_adjoint_simulation(fwidth=fwidth_adj, run_time=run_time_adj)

    assert sim_adj.run_time == run_time_expected


@pytest.mark.parametrize("has_adj_src, log_level_expected", [(True, None), (False, "WARNING")])
def test_no_adjoint_sources(
    monkeypatch, use_emulated_run, tmp_path, log_capture, has_adj_src, log_level_expected
):
    """Make sure warning (not error) if no adjoint sources."""

    def make_sim(eps):
        """Make a sim with given sources and fwidth_adjoint specified."""
        freq0 = 2e14
        mnt = td.ModeMonitor(
            size=(10, 10, 0),
            mode_spec=td.ModeSpec(num_modes=3),
            freqs=[freq0],
            name="mnt",
        )

        return JaxSimulation(
            size=(10, 10, 10),
            run_time=SIM_RUN_TIME,
            grid_spec=td.GridSpec(wavelength=1.0),
            monitors=(),
            structures=(),
            output_monitors=(mnt,),
            input_structures=(),
            sources=[src],
        )

    if not has_adj_src:
        monkeypatch.setattr(JaxModeData, "to_adjoint_sources", lambda *args, **kwargs: [])

    x = 2.0
    sim = make_sim(eps=x)
    data = run(sim, task_name="test", path=str(tmp_path / RUN_FILE))

    # check whether we got a warning for no sources?
    with AssertLogLevel(log_capture, log_level_expected, contains_str="No adjoint sources"):
        data.make_adjoint_simulation(fwidth=src.source_time.fwidth, run_time=sim.run_time)

    jnp.sum(jnp.abs(jnp.array(data["mnt"].amps.values)) ** 2)


def test_nonlinear_warn(log_capture):
    """Test that simulations warn if nonlinearity is used."""

    struct = JaxStructure(
        geometry=JaxBox(center=(0, 0, 0), size=(1, 1, 1)),
        medium=JaxMedium(permittivity=2.0),
    )

    struct_static = td.Structure(
        geometry=td.Box(center=(0, 3, 0), size=(1, 1, 1)),
        medium=td.Medium(permittivity=2.0),
    )

    sim_base = JaxSimulation(
        size=(10, 10, 0),
        run_time=SIM_RUN_TIME,
        grid_spec=td.GridSpec(wavelength=1.0),
        monitors=(),
        structures=(struct_static,),
        output_monitors=(),
        input_structures=(struct,),
        sources=[src],
        boundary_spec=td.BoundarySpec.pml(x=True, y=True, z=False),
    )

    # make the nonlinear objects to add to the JaxSimulation one by one
    nl_model = td.NonlinearSusceptibility(chi3=1)
    nl_medium = td.Medium(nonlinear_spec=td.NonlinearSpec(models=[nl_model]))
    struct_static_nl = struct_static.updated_copy(medium=nl_medium)
    input_struct_nl = JaxStructureStaticMedium(geometry=struct.geometry, medium=nl_medium)

    # no nonlinearity (no warning)
    assert_log_level(log_capture, None)

    # nonlinear simulation.medium (error)
    with AssertLogLevel(log_capture, "WARNING"):
        sim_base.updated_copy(medium=nl_medium)

    # nonlinear structure (warn)
    with AssertLogLevel(log_capture, "WARNING"):
        sim_base.updated_copy(structures=[struct_static_nl])

    # nonlinear input_structure (warn)
    with AssertLogLevel(log_capture, "WARNING"):
        sim_base.updated_copy(input_structures=[input_struct_nl])


@pytest.fixture
def hide_jax(monkeypatch, request):
    import_orig = builtins.__import__

    def mocked_import(name, *args, **kwargs):
        if name in ["jax", "jax.interpreters.ad", "jax.interpreters.ad.JVPTracer"]:
            raise ImportError()
        return import_orig(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", mocked_import)


def try_tracer_import() -> None:
    """Try importing `tidy3d.plugins.adjoint.components.types`."""
    from importlib import reload

    import tidy3d

    reload(tidy3d.plugins.adjoint.components.types)


@pytest.mark.usefixtures("hide_jax")
def test_jax_tracer_import_fail(tmp_path, log_capture):
    """Make sure if import error with JVPTracer, a warning is logged and module still imports."""
    try_tracer_import()
    assert_log_level(log_capture, "WARNING")


def test_jax_tracer_import_pass(tmp_path, log_capture):
    """Make sure if no import error with JVPTracer, nothing is logged and module imports."""
    try_tracer_import()
    assert_log_level(log_capture, None)


def test_inf_IO(tmp_path):
    """test that components can save and load "Infinity" properly in jax fields."""
    fname = str(tmp_path / "box.json")

    box = JaxBox(size=(td.inf, td.inf, td.inf), center=(0, 0, 0))
    box.to_file(fname)
    box2 = JaxBox.from_file(fname)
    assert box == box2


@pytest.mark.parametrize("sidewall_angle, log_expected", ([0.0, None], [0.1, "WARNING"]))
def test_sidewall_angle_validator(log_capture, sidewall_angle, log_expected):
    """Test that the sidewall angle warning works as expected."""

    jax_polyslab1 = JaxPolySlab(axis=POLYSLAB_AXIS, vertices=VERTICES, slab_bounds=(-1, 1))

    msg = "'JaxPolySlab' does not yet perform the full adjoint gradient treatment "
    for entry in td.log._static_cache:
        if msg in entry:
            return
    with AssertLogLevel(log_capture, log_expected, contains_str="sidewall"):
        jax_polyslab1.updated_copy(sidewall_angle=sidewall_angle)


def test_package_flux():
    """Test handling of packaging flux data for single and multi-freq."""

    value = 1.0
    da_single = JaxDataArray(values=[value], coords=dict(f=[1.0]))
    res_single = JaxFieldData.package_flux_results(None, da_single)
    assert res_single == value

    da_multi = JaxDataArray(values=[1.0, 2.0], coords=dict(f=[1.0, 2.0]))
    res_multi = JaxFieldData.package_flux_results(None, da_multi)
    assert res_multi == da_multi


def test_vertices_warning(log_capture):
    sim = make_sim(permittivity=EPS, size=SIZE, vertices=VERTICES, base_eps_val=BASE_EPS_VAL)

    polyslab = sim.input_structures[3].geometry

    radius_penalty = RadiusPenalty(min_radius=0.2, wrap=True)

    with AssertLogLevel(log_capture, "WARNING"):
        radius_penalty.evaluate(polyslab.vertices)

    with AssertLogLevel(log_capture, "WARNING"):
        radius_penalty.evaluate(np.array(jax.lax.stop_gradient(polyslab.vertices)))

    def f(vertices):
        return radius_penalty.evaluate(vertices)

    with AssertLogLevel(log_capture, None):
        jax.grad(f)(np.random.random((5, 2)))

    with AssertLogLevel(log_capture, None):
        jax.grad(f)(np.random.random((5, 2)).tolist())


def test_no_poynting(use_emulated_run):
    """Test that poynting vector fails with custom error."""

    sim = make_sim(permittivity=EPS, size=SIZE, vertices=VERTICES, base_eps_val=BASE_EPS_VAL)
    sim_data = run(sim, task_name="test", path=str(TMP_PATH / RUN_FILE))

    mnt_name_static = "field"
    mnt_name_differentiable = MNT_NAME + "3"

    sim_data.get_poynting_vector(mnt_name_static)

    with pytest.raises(NotImplementedError):
        sim_data.get_poynting_vector(mnt_name_differentiable)

    sim_data._get_scalar_field(mnt_name_static, "S", "abs")

    # with pytest.raises(NotImplementedError):
    #    sim_data._get_scalar_field(mnt_name_differentiable, "S", "abs")


def test_to_gds(tmp_path):
    """Test that JaxSimulation can be converted to GDS."""
    sim = make_sim(permittivity=EPS, size=SIZE, vertices=VERTICES, base_eps_val=BASE_EPS_VAL)

    fname = str(tmp_path / "simulation_z.gds")
    sim.to_gds_file(fname, z=0, permittivity_threshold=6, frequency=200e14)
    cell = gdstk.read_gds(fname).cells[0]
    assert len(cell.get_polygons()) > 0

    fname = str(tmp_path / "simulation_y.gds")
    sim.to_gds_file(fname, y=0, permittivity_threshold=6, frequency=200e14)
    cell = gdstk.read_gds(fname).cells[0]
    assert len(cell.get_polygons()) > 4  # 4 polys from extraneous_structure

    polys = sim.to_gdstk(y=0, permittivity_threshold=6, frequency=200e14)
    assert len(polys) > 4
    polys = sim.to_gdstk(z=0, permittivity_threshold=6, frequency=200e14)
    assert len(polys) > 0

    # to_gdspy() does not support custom medium
    sim = make_sim(
        permittivity=EPS,
        size=SIZE,
        vertices=VERTICES,
        base_eps_val=BASE_EPS_VAL,
        custom_medium=False,
    )
    polys = sim.to_gdspy(z=0)
    assert len(polys) > 0

    polys = sim.to_gdspy(y=0)
    assert len(polys) > 4


@pytest.mark.parametrize(
    "base_vertices",
    [
        [(0, 0), (0.5, 1), (0, 1)],  # triangle
        [(0, 0), (1, 0), (1, 1), (0, 1), (0, 0.9), (0, 0.11)],  # notched rectangle
    ],
)
@pytest.mark.parametrize("subdivide", [0, 1, 3])
@pytest.mark.parametrize("sidewall_angle_deg", [0, 10])
@pytest.mark.parametrize("dilation", [-0.02, 0.0, 0.02])
class TestJaxComplexPolySlab:
    slab_bounds = (-0.25, 0.25)
    EPS = 1e-12
    RTOL = 1e-2

    @staticmethod
    def objfun(vertices, slab_bounds, sidewall_angle, dilation):
        p = JaxComplexPolySlab(
            vertices=vertices,
            slab_bounds=slab_bounds,
            sidewall_angle=sidewall_angle,
            dilation=dilation,
        )
        obj = 0.0
        for s in p.sub_polyslabs:
            obj += jnp.sum(jnp.asarray(s.vertices_jax) ** 2)
            obj += jnp.sum(jnp.asarray(s.slab_bounds_jax) ** 2)
            obj += jnp.sum(jnp.asarray(s.sidewall_angle_jax) ** 2)
        return obj

    @pytest.fixture
    def vertices(self, base_vertices, subdivide):
        if subdivide == 0:
            return tuple(map(tuple, np.asarray(base_vertices)))
        num_verts = 2 + subdivide
        vertices_out = []
        for v1, v2 in zip(base_vertices, base_vertices[1:] + [base_vertices[0]]):
            x, y = np.meshgrid(
                np.linspace(v1[0], v2[0], num_verts)[:-1],
                np.linspace(v1[1], v2[1], num_verts)[:-1],
                sparse=True,
            )
            vertices_out.extend(list(zip(x.ravel(), y.ravel())))
        return tuple(map(tuple, vertices_out[:-1]))

    @pytest.fixture
    def sidewall_angle(self, sidewall_angle_deg):
        return np.deg2rad(sidewall_angle_deg)

    def test_matches_complexpolyslab(self, vertices, sidewall_angle, dilation):
        kwargs = dict(
            vertices=vertices,
            sidewall_angle=sidewall_angle,
            slab_bounds=self.slab_bounds,
            dilation=dilation,
            axis=POLYSLAB_AXIS,
        )
        cp = ComplexPolySlab(**kwargs)
        jcp = JaxComplexPolySlab(**kwargs)

        assert len(cp.sub_polyslabs) == len(jcp.sub_polyslabs)

        for cps, jcps in zip(cp.sub_polyslabs, jcp.sub_polyslabs):
            assert_allclose(cps.vertices, jcps.vertices)

    def test_vertices_grads(self, vertices, sidewall_angle, dilation):
        check_grads(
            lambda x: self.objfun(x, self.slab_bounds, sidewall_angle, dilation),
            (vertices,),
            order=1,
            rtol=self.RTOL,
            eps=self.EPS,
        )

    def test_dilation_grads(self, vertices, sidewall_angle, dilation):
        if sidewall_angle != 0:
            pytest.xfail("Dilation gradients only work if no sidewall angle.")
        check_grads(
            lambda x: self.objfun(vertices, self.slab_bounds, sidewall_angle, x),
            (dilation,),
            order=1,
            rtol=self.RTOL,
            eps=self.EPS,
        )

    def test_slab_bounds_grads(self, vertices, sidewall_angle, dilation):
        if sidewall_angle != 0:
            pytest.xfail("Slab bound gradients only work if no sidewall angle.")
        check_grads(
            lambda x: self.objfun(vertices, x, sidewall_angle, dilation),
            (self.slab_bounds,),
            order=1,
            rtol=self.RTOL,
            eps=self.EPS,
        )

    def test_sidewall_angle_grads(self, vertices, sidewall_angle, dilation):
        if sidewall_angle != 0:
            pytest.xfail("Sidewall gradients only work for small angles.")
        check_grads(
            lambda x: self.objfun(vertices, self.slab_bounds, x, dilation),
            (sidewall_angle,),
            order=1,
            rtol=self.RTOL,
            eps=self.EPS,
        )
