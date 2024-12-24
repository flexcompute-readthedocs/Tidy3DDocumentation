"""Test suite for heat-charge simulation objects and data using pytest fixtures."""

import numpy as np
import pydantic.v1 as pd
import pytest
import tidy3d as td
from matplotlib import pyplot as plt
from tidy3d.exceptions import DataError

from ..utils import assert_log_level


class CHARGE_SIMULATION:
    """This class contains all elements to be tested."""

    # Dimensions of semiconductors
    width = 0.2  # um
    height = 0.2  # um
    z_dim = width / 2

    # Simulation size
    sim_size = (3 * width, 2 * height, z_dim)

    # Doping concentrations
    acceptors = 1e17
    donors = 5e17


# --------------------------
# Pytest Fixtures
# --------------------------


@pytest.fixture(scope="module")
def mediums():
    """Creates mediums with different specifications."""
    fluid_medium = td.Medium(
        permittivity=3,
        heat_spec=td.FluidSpec(),
        name="fluid_medium",
    )
    solid_medium = td.MultiPhysicsMedium(
        optical=td.Medium(
            permittivity=5,
            conductivity=0.01,
            heat_spec=td.SolidSpec(
                capacity=2,
                conductivity=3,
            ),
        ),
        charge=td.ChargeConductorMedium(
            conductivity=1,
        ),
        name="solid_medium",
    )

    solid_no_heat = td.MultiPhysicsMedium(
        optical=td.Medium(
            permittivity=5,
            conductivity=0.01,
        ),
        charge=td.ChargeConductorMedium(
            conductivity=1,
        ),
        name="solid_no_heat",
    )

    solid_no_elect = td.Medium(
        permittivity=5,
        conductivity=0.01,
        heat_spec=td.SolidSpec(
            capacity=2,
            conductivity=3,
        ),
        name="solid_no_elect",
    )

    insulator_medium = td.MultiPhysicsMedium(
        optical=td.Medium(
            permittivity=3,
        ),
        charge=td.ChargeInsulatorMedium(),
        name="insulator_medium",
    )

    return {
        "fluid_medium": fluid_medium,
        "solid_medium": solid_medium,
        "solid_no_heat": solid_no_heat,
        "solid_no_elect": solid_no_elect,
        "insulator_medium": insulator_medium,
    }


@pytest.fixture(scope="module")
def structures(mediums):
    """Creates structures with different mediums and sizes."""
    box = td.Box(center=(0, 0, 0), size=(1, 1, 1))  # Adjusted size for consistency

    fluid_structure = td.Structure(
        geometry=box,
        medium=mediums["fluid_medium"],
        name="fluid_structure",
    )

    solid_structure = td.Structure(
        geometry=box.updated_copy(center=(1, 1, 1)),
        medium=mediums["solid_medium"],
        name="solid_structure",
    )

    solid_struct_no_heat = td.Structure(
        geometry=box.updated_copy(center=(1, 1, 1)),
        medium=mediums["solid_no_heat"],
        name="solid_struct_no_heat",
    )

    solid_struct_no_elect = td.Structure(
        geometry=box.updated_copy(center=(1, 1, 1)),
        medium=mediums["solid_no_elect"],
        name="solid_struct_no_elect",
    )

    insulator_structure = td.Structure(
        geometry=box,
        medium=mediums["insulator_medium"],
        name="insulator_structure",
    )

    return {
        "fluid_structure": fluid_structure,
        "solid_structure": solid_structure,
        "solid_struct_no_heat": solid_struct_no_heat,
        "solid_struct_no_elect": solid_struct_no_elect,
        "insulator_structure": insulator_structure,
    }


@pytest.fixture(scope="module")
def boundary_conditions():
    """Creates a list of boundary conditions."""
    bc_temp = td.TemperatureBC(temperature=300)
    bc_flux = td.HeatFluxBC(flux=20)
    bc_conv = td.ConvectionBC(ambient_temperature=400, transfer_coeff=0.2)
    bc_volt = td.VoltageBC(source=td.DCVoltageSource(voltage=[1]))
    bc_current = td.CurrentBC(current_density=3e-1)

    return [bc_temp, bc_flux, bc_conv, bc_volt, bc_current]


@pytest.fixture(scope="module")
def monitors():
    """Creates monitors of different types and sizes."""
    temp_mnt1 = td.TemperatureMonitor(size=(1.6, 2, 3), name="test")
    temp_mnt2 = td.TemperatureMonitor(size=(1.6, 2, 3), name="tet", unstructured=True)
    temp_mnt3 = td.TemperatureMonitor(
        center=(0, 0.9, 0), size=(1.6, 0, 3), name="tri", unstructured=True, conformal=True
    )
    temp_mnt4 = td.TemperatureMonitor(
        center=(0, 0.9, 0), size=(1.6, 0, 3), name="empty", unstructured=True, conformal=False
    )

    volt_mnt1 = td.SteadyPotentialMonitor(size=(1.6, 2, 3), name="v_test")
    volt_mnt2 = td.SteadyPotentialMonitor(size=(1.6, 2, 3), name="v_tet", unstructured=True)
    volt_mnt3 = td.SteadyPotentialMonitor(
        center=(0, 0.9, 0), size=(1.6, 0, 3), name="v_tri", unstructured=True, conformal=True
    )
    volt_mnt4 = td.SteadyPotentialMonitor(
        center=(0, 0.9, 0), size=(1.6, 0, 3), name="v_empty", unstructured=True, conformal=False
    )

    return [temp_mnt1, temp_mnt2, temp_mnt3, temp_mnt4, volt_mnt1, volt_mnt2, volt_mnt3, volt_mnt4]


@pytest.fixture(scope="module")
def grid_specs():
    """Creates grid specifications."""
    uniform_grid = td.UniformUnstructuredGrid(
        dl=0.1, min_edges_per_circumference=5, min_edges_per_side=3
    )
    distance_grid = td.DistanceUnstructuredGrid(
        dl_interface=0.1, dl_bulk=1, distance_interface=1, distance_bulk=2
    )
    return {
        "uniform": uniform_grid,
        "distance": distance_grid,
    }


@pytest.fixture(scope="module")
def heat_simulation(mediums, structures, boundary_conditions, monitors, grid_specs):
    """Generates a heat-charge heat simulation."""
    heat_source = td.HeatSource(structures=["solid_structure"], rate=100)

    pl1 = td.HeatChargeBoundarySpec(
        condition=boundary_conditions[2],  # bc_conv
        placement=td.MediumMediumInterface(mediums=["fluid_medium", "solid_medium"]),
    )
    pl2 = td.HeatChargeBoundarySpec(
        condition=boundary_conditions[1],  # bc_flux
        placement=td.StructureBoundary(structure="solid_structure"),
    )
    pl3 = td.HeatChargeBoundarySpec(
        condition=boundary_conditions[0],  # bc_temp
        placement=td.StructureStructureInterface(structures=["fluid_structure", "solid_structure"]),
    )

    heat_sim = td.HeatChargeSimulation(
        medium=mediums["fluid_medium"],
        structures=[structures["fluid_structure"], structures["solid_structure"]],
        center=(0, 0, 0),
        size=(2, 2, 2),
        boundary_spec=[pl1, pl2, pl3],
        grid_spec=grid_specs["uniform"],
        sources=[heat_source],
        monitors=monitors[0:4],
    )

    return heat_sim


@pytest.fixture(scope="module")
def conduction_simulation(mediums, structures, boundary_conditions, monitors, grid_specs):
    """Creates a heat-charge conduction simulation."""
    pl4 = td.HeatChargeBoundarySpec(
        condition=boundary_conditions[3],  # bc_volt
        placement=td.SimulationBoundary(),
    )
    pl5 = td.HeatChargeBoundarySpec(
        condition=boundary_conditions[4],  # bc_current
        placement=td.StructureSimulationBoundary(structure="insulator_structure"),
    )

    cond_sim = td.HeatChargeSimulation(
        medium=mediums["insulator_medium"],
        structures=[structures["insulator_structure"], structures["solid_structure"]],
        center=(0, 0, 0),
        size=(2, 2, 2),
        boundary_spec=[pl4, pl5],
        grid_spec=grid_specs["uniform"],
        sources=[],
        monitors=monitors[4:8],
    )

    return cond_sim


@pytest.fixture(scope="module")
def temperature_monitor_data(monitors):
    """Creates different temperature monitor data."""
    temp_mnt1, temp_mnt2, temp_mnt3, temp_mnt4, *_ = monitors

    # SpatialDataArray
    nx, ny, nz = 9, 6, 5
    x = np.linspace(0, 1, nx)
    y = np.linspace(0, 2, ny)
    z = np.linspace(0, 3, nz)
    T = np.random.default_rng().uniform(300, 350, (nx, ny, nz))
    coords = dict(x=x, y=y, z=z)
    temperature_field = td.SpatialDataArray(T, coords=coords)

    mnt_data1 = td.TemperatureData(monitor=temp_mnt1, temperature=temperature_field)

    # TetrahedralGridDataset
    tet_grid_points = td.PointDataArray(
        [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [1.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
        dims=("index", "axis"),
    )

    tet_grid_cells = td.CellDataArray(
        [[0, 1, 2, 4], [1, 2, 3, 4]],
        dims=("cell_index", "vertex_index"),
    )

    tet_grid_values = td.IndexedDataArray(
        [1.0, 2.0, 3.0, 4.0, 5.0],
        dims=("index",),
        name="T",
    )

    tet_grid = td.TetrahedralGridDataset(
        points=tet_grid_points,
        cells=tet_grid_cells,
        values=tet_grid_values,
    )

    mnt_data2 = td.TemperatureData(monitor=temp_mnt2, temperature=tet_grid)

    # TriangularGridDataset
    tri_grid_points = td.PointDataArray(
        [[0.0, 0.0], [1.0, 0.0], [0.0, 1.0], [1.0, 1.0]],
        dims=("index", "axis"),
    )

    tri_grid_cells = td.CellDataArray(
        [[0, 1, 2], [1, 2, 3]],
        dims=("cell_index", "vertex_index"),
    )

    tri_grid_values = td.IndexedDataArray(
        [1.0, 2.0, 3.0, 4.0],
        dims=("index",),
        name="T",
    )

    tri_grid = td.TriangularGridDataset(
        normal_axis=1,
        normal_pos=0,
        points=tri_grid_points,
        cells=tri_grid_cells,
        values=tri_grid_values,
    )

    mnt_data3 = td.TemperatureData(monitor=temp_mnt3, temperature=tri_grid)

    mnt_data4 = td.TemperatureData(monitor=temp_mnt4, temperature=None)

    return (mnt_data1, mnt_data2, mnt_data3, mnt_data4)


@pytest.fixture(scope="module")
def voltage_monitor_data(monitors):
    """Creates different voltage monitor data."""
    _, _, _, _, volt_mnt1, volt_mnt2, volt_mnt3, volt_mnt4 = monitors

    # SpatialDataArray
    nx, ny, nz = 9, 6, 5
    x = np.linspace(0, 1, nx)
    y = np.linspace(0, 2, ny)
    z = np.linspace(0, 3, nz)
    T = np.random.default_rng().uniform(-5, 5, (nx, ny, nz))
    coords = dict(x=x, y=y, z=z)
    voltage_field = td.SpatialDataArray(T, coords=coords)

    mnt_data1 = td.SteadyPotentialData(monitor=volt_mnt1, potential=voltage_field)

    # TetrahedralGridDataset
    tet_grid_points = td.PointDataArray(
        [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [1.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
        dims=("index", "axis"),
    )

    tet_grid_cells = td.CellDataArray(
        [[0, 1, 2, 4], [1, 2, 3, 4]],
        dims=("cell_index", "vertex_index"),
    )

    tet_grid_values = td.IndexedDataArray(
        [1.0, 2.0, 3.0, 4.0, 5.0],
        dims=("index",),
        name="T",
    )

    tet_grid = td.TetrahedralGridDataset(
        points=tet_grid_points,
        cells=tet_grid_cells,
        values=tet_grid_values,
    )

    mnt_data2 = td.SteadyPotentialData(monitor=volt_mnt2, potential=tet_grid)

    # TriangularGridDataset
    tri_grid_points = td.PointDataArray(
        [[0.0, 0.0], [1.0, 0.0], [0.0, 1.0], [1.0, 1.0]],
        dims=("index", "axis"),
    )

    tri_grid_cells = td.CellDataArray(
        [[0, 1, 2], [1, 2, 3]],
        dims=("cell_index", "vertex_index"),
    )

    tri_grid_values = td.IndexedDataArray(
        [1.0, 2.0, 3.0, 4.0],
        dims=("index",),
        name="T",
    )

    tri_grid = td.TriangularGridDataset(
        normal_axis=1,
        normal_pos=0,
        points=tri_grid_points,
        cells=tri_grid_cells,
        values=tri_grid_values,
    )

    mnt_data3 = td.SteadyPotentialData(monitor=volt_mnt3, potential=tri_grid)

    mnt_data4 = td.SteadyPotentialData(monitor=volt_mnt4, potential=None)

    return (mnt_data1, mnt_data2, mnt_data3, mnt_data4)


@pytest.fixture(scope="module")
def simulation_data(
    heat_simulation, conduction_simulation, temperature_monitor_data, voltage_monitor_data
):
    """Creates 'HeatChargeSimulationData' for both HEAT and CONDUCTION simulations."""
    heat_sim_data = td.HeatChargeSimulationData(
        simulation=heat_simulation,
        data=temperature_monitor_data,
    )

    cond_sim_data = td.HeatChargeSimulationData(
        simulation=conduction_simulation,
        data=voltage_monitor_data,
    )

    return [heat_sim_data, cond_sim_data]


# --------------------------
# Test Functions
# --------------------------


def test_heat_charge_medium_validation(mediums):
    """Tests validation errors for mediums."""
    solid_medium = mediums["solid_medium"]

    # Test invalid capacity
    with pytest.raises(pd.ValidationError):
        solid_medium.heat_spec.updated_copy(capacity=-1)

    # Test invalid conductivity
    with pytest.raises(pd.ValidationError):
        solid_medium.heat_spec.updated_copy(conductivity=-1)

    # Test invalid charge conductivity
    with pytest.raises(pd.ValidationError):
        solid_medium.charge.updated_copy(conductivity=-1)


def test_heat_charge_structures_creation(structures):
    """Tests that different structures with different mediums can be created."""
    fluid_structure = structures["fluid_structure"]
    solid_structure = structures["solid_structure"]
    solid_struct_no_heat = structures["solid_struct_no_heat"]
    solid_struct_no_elect = structures["solid_struct_no_elect"]
    insulator_structure = structures["insulator_structure"]

    assert fluid_structure.medium.name == "fluid_medium"
    assert solid_structure.medium.name == "solid_medium"
    assert solid_struct_no_heat.medium.name == "solid_no_heat"
    assert solid_struct_no_elect.medium.name == "solid_no_elect"
    assert insulator_structure.medium.name == "insulator_medium"


def test_heat_charge_bcs_validation(boundary_conditions):
    """Tests the validators for boundary conditions."""
    bc_temp, bc_flux, bc_conv, bc_volt, bc_current = boundary_conditions

    # Invalid TemperatureBC
    with pytest.raises(pd.ValidationError):
        td.TemperatureBC(temperature=-10)

    # Invalid ConvectionBC: negative ambient temperature
    with pytest.raises(pd.ValidationError):
        td.ConvectionBC(ambient_temperature=-400, transfer_coeff=0.2)

    # Invalid ConvectionBC: negative transfer coefficient
    with pytest.raises(pd.ValidationError):
        td.ConvectionBC(ambient_temperature=400, transfer_coeff=-0.2)

    # Invalid VoltageBC: infinite voltage
    with pytest.raises(pd.ValidationError):
        td.VoltageBC(source=td.DCVoltageSource(voltage=[td.inf]))

    # Invalid CurrentBC: infinite current density
    with pytest.raises(pd.ValidationError):
        td.CurrentBC(current_density=td.inf)


def test_heat_charge_monitors_validation(monitors):
    """Checks for no name and negative size in monitors."""
    temp_mnt = monitors[0]

    # Invalid monitor name
    with pytest.raises(pd.ValidationError):
        temp_mnt.updated_copy(name=None)

    # Invalid monitor size (negative dimension)
    with pytest.raises(pd.ValidationError):
        temp_mnt.updated_copy(size=(-1, 2, 3))


def test_monitor_crosses_medium(mediums, structures, heat_simulation, conduction_simulation):
    """Tests whether monitor crosses structures with relevant material specifications."""
    solid_no_heat = mediums["solid_no_heat"]
    solid_no_elect = mediums["solid_no_elect"]
    solid_struct_no_heat = structures["solid_struct_no_heat"]
    solid_struct_no_elect = structures["solid_struct_no_elect"]

    # Voltage monitor
    volt_monitor = td.SteadyPotentialMonitor(
        center=(0, 0, 0), size=(td.inf, td.inf, td.inf), name="voltage"
    )
    # A voltage monitor in a heat simulation should throw error if no ChargeConductorMedium is present
    with pytest.raises(pd.ValidationError):
        heat_simulation.updated_copy(
            medium=solid_no_elect, structures=[solid_struct_no_elect], monitors=[volt_monitor]
        )

    # Temperature monitor
    temp_monitor = td.TemperatureMonitor(
        center=(0, 0, 0), size=(td.inf, td.inf, td.inf), name="temperature"
    )
    # A temperature monitor should throw error in a conduction simulation if no SolidSpec is present
    with pytest.raises(pd.ValidationError):
        conduction_simulation.updated_copy(
            medium=solid_no_heat, structures=[solid_struct_no_heat], monitors=[temp_monitor]
        )


def test_heat_charge_mnt_data(temperature_monitor_data, voltage_monitor_data):
    """Tests whether different heat-charge monitor data can be created."""
    assert len(temperature_monitor_data) == 4, "Expected 4 temperature monitor data entries."
    assert len(voltage_monitor_data) == 4, "Expected 4 voltage monitor data entries."
    # Additional assertions can be added here if necessary


def test_grid_spec_validation(grid_specs):
    """Tests whether unstructured grids can be created and different validators for them."""
    # Test UniformUnstructuredGrid
    uniform_grid = grid_specs["uniform"]
    with pytest.raises(pd.ValidationError):
        uniform_grid.updated_copy(dl=0)
    with pytest.raises(pd.ValidationError):
        uniform_grid.updated_copy(min_edges_per_circumference=-1)
    with pytest.raises(pd.ValidationError):
        uniform_grid.updated_copy(min_edges_per_side=-1)

    # Test DistanceUnstructuredGrid
    distance_grid = grid_specs["distance"]
    with pytest.raises(pd.ValidationError):
        distance_grid.updated_copy(dl_interface=-1)
    with pytest.raises(pd.ValidationError):
        distance_grid.updated_copy(distance_interface=2, distance_bulk=1)


def test_heat_charge_sources(log_capture, structures):
    """Tests whether heat-charge sources can be created and associated warnings."""
    # this shouldn't issue warning
    _ = td.HeatSource(structures=["solid_structure"], rate=100)
    assert len(log_capture) == 0, "Expected no warnings for HeatSource."

    # this should issue warning
    _ = td.UniformHeatSource(structures=["solid_structure"], rate=100)
    assert_log_level(log_capture, "WARNING")

    # this shouldn't issue warning but rate is a string, assuming it's allowed
    _ = td.HeatSource(structures=["solid_structure"], rate="100")
    assert len(log_capture) == 1, "Expected one warning for HeatSource with string rate."


def test_heat_charge_simulation(simulation_data):
    """Tests 'HeatChargeSimulation' and 'ConductionSimulation' objects."""
    heat_sim_data, cond_sim_data = simulation_data

    # Test Heat Simulation
    heat_sim = heat_sim_data.simulation
    assert heat_sim is not None, "Heat simulation should be created successfully."

    # Test Conduction Simulation
    cond_sim = cond_sim_data.simulation
    assert cond_sim is not None, "Conduction simulation should be created successfully."


def test_sim_data_plotting(simulation_data):
    """Tests whether simulation data can be plotted and appropriate errors are raised."""
    heat_sim_data, cond_sim_data = simulation_data

    # Plotting temperature data
    heat_sim_data.plot_field("test", z=0)
    heat_sim_data.plot_field("tri")
    heat_sim_data.plot_field("tet", y=0.5)

    # Plotting voltage data
    cond_sim_data.plot_field("v_test", z=0)
    cond_sim_data.plot_field("v_tri")
    cond_sim_data.plot_field("v_tet", y=0.5)
    plt.close()

    # Test plotting with no data
    with pytest.raises(DataError):
        heat_sim_data.plot_field("empty")

    # Test plotting with invalid data
    with pytest.raises(DataError):
        heat_sim_data.plot_field("test")

    # Test plotting with invalid key
    with pytest.raises(KeyError):
        heat_sim_data.plot_field("test3", x=0)

    # Test updating simulation data with duplicate data
    with pytest.raises(pd.ValidationError):
        heat_sim_data.updated_copy(data=[heat_sim_data.data[0]] * 2)

    # Test updating simulation data with invalid simulation
    temp_mnt = td.TemperatureMonitor(size=(1, 2, 3), name="test")
    temp_mnt = temp_mnt.updated_copy(name="test2")

    sim = heat_sim_data.simulation.updated_copy(monitors=[temp_mnt])

    with pytest.raises(pd.ValidationError):
        heat_sim_data.updated_copy(simulation=sim)


# --------------------------
# Test Classes with Fixtures
# --------------------------


class TestCharge:
    """Group of tests related to charge simulations."""

    # Define semiconductor materials as fixtures within the class
    @pytest.fixture(scope="class")
    def Si_p(self):
        return td.MultiPhysicsMedium(
            charge=td.SemiconductorMedium(
                conductivity=1,
                permittivity=11.7,
                donors=0,
                acceptors=CHARGE_SIMULATION.acceptors,
            ),
            name="Si_p",
        )

    @pytest.fixture(scope="class")
    def Si_n(self):
        return td.MultiPhysicsMedium(
            charge=td.SemiconductorMedium(
                conductivity=1,
                permittivity=11.7,
                donors=CHARGE_SIMULATION.donors,
                acceptors=0,
            ),
            name="Si_n",
        )

    @pytest.fixture(scope="class")
    def SiO2(self):
        return td.MultiPhysicsMedium(
            charge=td.ChargeInsulatorMedium(permittivity=3.9),
            name="SiO2",
        )

    # Define structures as fixtures within the class
    @pytest.fixture(scope="class")
    def oxide(self, SiO2):
        return td.Structure(
            geometry=td.Box(center=(0, 0, 0), size=CHARGE_SIMULATION.sim_size),
            medium=SiO2,
            name="oxide",
        )

    @pytest.fixture(scope="class")
    def p_side(self, Si_p):
        return td.Structure(
            geometry=td.Box(
                center=(-CHARGE_SIMULATION.width / 2, 0, 0),
                size=(CHARGE_SIMULATION.width, CHARGE_SIMULATION.height, CHARGE_SIMULATION.z_dim),
            ),
            medium=Si_p,
            name="p_side",
        )

    @pytest.fixture(scope="class")
    def n_side(self, Si_n):
        return td.Structure(
            geometry=td.Box(
                center=(CHARGE_SIMULATION.width / 2, 0, 0),
                size=(CHARGE_SIMULATION.width, CHARGE_SIMULATION.height, CHARGE_SIMULATION.z_dim),
            ),
            medium=Si_n,
            name="n_side",
        )

    # Define boundary conditions as fixtures within the class
    @pytest.fixture(scope="class")
    def bc_p(self, SiO2, Si_p):
        return td.HeatChargeBoundarySpec(
            condition=td.VoltageBC(source=td.DCVoltageSource(voltage=[0])),
            placement=td.MediumMediumInterface(mediums=[SiO2.name, Si_p.name]),
        )

    @pytest.fixture(scope="class")
    def bc_n(self, SiO2, Si_n):
        return td.HeatChargeBoundarySpec(
            condition=td.VoltageBC(source=td.DCVoltageSource(voltage=[0])),
            placement=td.MediumMediumInterface(mediums=[SiO2.name, Si_n.name]),
        )

    # Define monitors as fixtures within the class
    @pytest.fixture(scope="class")
    def charge_global_mnt(self):
        return td.SteadyFreeChargeCarrierMonitor(
            center=(0, 0, 0),
            size=(td.inf, td.inf, td.inf),
            name="charge_global_mnt",
            unstructured=True,
        )

    @pytest.fixture(scope="class")
    def potential_global_mnt(self):
        return td.SteadyPotentialMonitor(
            center=(0, 0, 0),
            size=(td.inf, td.inf, td.inf),
            name="potential_global_mnt",
            unstructured=True,
        )

    @pytest.fixture(scope="class")
    def capacitance_global_mnt(self):
        return td.SteadyCapacitanceMonitor(
            center=(0, 0, 0),
            size=(td.inf, td.inf, td.inf),
            name="capacitance_global_mnt",
            unstructured=True,
        )

    # Define charge settings as fixtures within the class
    @pytest.fixture(scope="class")
    def charge_tolerance(self):
        return td.TransferFunctionDC(
            tolerance_settings=td.ChargeToleranceSpec(rel_tol=1e5, abs_tol=1e3, max_iters=400)
        )

    @pytest.fixture(scope="class")
    def charge_dc_regime(self):
        return td.DCVoltageSource(voltage=[1])

    def test_charge_simulation(
        self,
        oxide,
        p_side,
        n_side,
        charge_global_mnt,
        potential_global_mnt,
        capacitance_global_mnt,
        bc_n,
        bc_p,
        charge_tolerance,
        charge_dc_regime,
    ):
        """Ensure charge simulation produces the correct errors when needed."""
        sim = td.HeatChargeSimulation(
            structures=[oxide, p_side, n_side],
            medium=td.MultiPhysicsMedium(
                heat=td.FluidSpec(), charge=td.ChargeConductorMedium(), name="air"
            ),
            monitors=[charge_global_mnt, potential_global_mnt, capacitance_global_mnt],
            center=(0, 0, 0),
            size=CHARGE_SIMULATION.sim_size,
            grid_spec=td.UniformUnstructuredGrid(dl=0.05),
            boundary_spec=[bc_n, bc_p],
            analysis_spec=charge_tolerance,
        )

        # At least one ChargeSimulationMonitor should be added
        with pytest.raises(pd.ValidationError):
            sim.updated_copy(monitors=[])

        # At least 2 VoltageBCs should be defined
        with pytest.raises(pd.ValidationError):
            sim.updated_copy(boundary_spec=[bc_n])

        # Define ChargeSimulation with no Semiconductor materials
        medium = td.MultiPhysicsMedium(
            charge=td.ChargeConductorMedium(permittivity=1, conductivity=1),
            name="medium",
        )
        new_structures = [struct.updated_copy(medium=medium) for struct in sim.structures]

        with pytest.raises(pd.ValidationError):
            sim.updated_copy(structures=new_structures)

    def test_doping_distributions(self):
        """Test doping distributions."""
        # Implementation needed
        # This test was empty in the original code.
        pass


# --------------------------
# Additional Tests
# --------------------------


@pytest.mark.parametrize("shift_amount, log_level", [(1, None), (2, "WARNING")])
def test_heat_charge_sim_bounds(shift_amount, log_level, log_capture):
    """Ensure bounds are working correctly."""
    # Make sure all things are shifted to this central location
    CENTER_SHIFT = (-1.0, 1.0, 100.0)

    def place_box(center_offset):
        shifted_center = tuple(c + s for (c, s) in zip(center_offset, CENTER_SHIFT))

        _ = td.HeatChargeSimulation(
            size=(1.5, 1.5, 1.5),
            center=CENTER_SHIFT,
            medium=td.MultiPhysicsMedium(charge=td.ChargeConductorMedium(conductivity=1)),
            structures=[
                td.Structure(
                    geometry=td.Box(size=(1, 1, 1), center=shifted_center),
                    medium=td.Medium(),
                )
            ],
            boundary_spec=[
                td.HeatChargeBoundarySpec(
                    condition=td.VoltageBC(source=td.DCVoltageSource(voltage=[1])),
                    placement=td.SimulationBoundary(),
                )
            ],
            grid_spec=td.UniformUnstructuredGrid(dl=0.1),
        )

    # Create all permutations of squares being shifted 1, -1, or zero in all three directions
    bin_strings = [format(i, "03b") for i in range(8)]
    bin_ints = [[int(b) for b in bin_string] for bin_string in bin_strings]
    bin_ints = np.array(bin_ints)
    bin_signs = 2 * (bin_ints - 0.5)

    # Test all cases where box is shifted +/- 1 in x,y,z and still intersects
    for amp in bin_ints:
        for sign in bin_signs:
            center = tuple(shift_amount * a * s for a, s in zip(amp, sign))
            if np.sum(np.abs(center)) < 1e-12:
                continue
            place_box(center)
    assert_log_level(log_capture, log_level)


@pytest.mark.parametrize(
    "box_size, log_level",
    [
        ((1, 0.1, 0.1), "WARNING"),
        ((0.1, 1, 0.1), "WARNING"),
        ((0.1, 0.1, 1), "WARNING"),
    ],
)
def test_sim_structure_extent(box_size, log_level, log_capture):
    """Ensure we warn if structure extends exactly to simulation edges."""
    box = td.Structure(geometry=td.Box(size=box_size), medium=td.Medium(permittivity=2))
    _ = td.HeatChargeSimulation(
        size=(1, 1, 1),
        structures=[box],
        medium=td.MultiPhysicsMedium(charge=td.ChargeConductorMedium(conductivity=1)),
        boundary_spec=[
            td.HeatChargeBoundarySpec(
                placement=td.SimulationBoundary(),
                condition=td.VoltageBC(source=td.DCVoltageSource(voltage=[1])),
            )
        ],
        grid_spec=td.UniformUnstructuredGrid(dl=0.1),
    )

    assert_log_level(log_capture, log_level)
