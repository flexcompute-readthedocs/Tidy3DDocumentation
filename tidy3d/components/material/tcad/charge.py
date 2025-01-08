"""Defines heat material specifications"""

from __future__ import annotations

from typing import Tuple

import pydantic.v1 as pd

from tidy3d.components.data.data_array import SpatialDataArray
from tidy3d.components.medium import AbstractMedium
from tidy3d.components.tcad.doping import DopingBoxType
from tidy3d.components.tcad.types import (
    AugerRecombination,
    BandGapNarrowingModelTypes,
    CaugheyThomasMobility,
    MobilityModelTypes,
    RadiativeRecombination,
    RecombinationModelTypes,
    ShockleyReedHallRecombination,
    SlotboomBandGapNarrowing,
)
from tidy3d.components.types import Union
from tidy3d.constants import (
    CONDUCTIVITY,
    ELECTRON_VOLT,
    PERMITTIVITY,
)


class AbstractChargeMedium(AbstractMedium):
    """Abstract class for Charge specifications"""

    conductivity: pd.PositiveFloat = pd.Field(
        1,
        title="TODO MARC DECIDE VALUE conductivity",
        description=f"Electric conductivity of material in units of {CONDUCTIVITY}.",
        units=CONDUCTIVITY,
    )

    permittivity: float = pd.Field(
        1.0, ge=1.0, title="Permittivity", description="Relative permittivity.", units=PERMITTIVITY
    )

    @property
    def charge(self):
        """
        This means that a charge medium has been defined inherently within this solver medium.
        This provides interconnection with the `MultiPhysicsMedium` higher-dimensional classes.
        """
        return self

    def eps_model(self, frequency: float) -> complex:
        # TODO just pass it directly for charge simulations
        return self.permittivity

    def n_cfl(self):
        return None


class ChargeInsulatorMedium(AbstractChargeMedium):
    """
    Insulating medium. Conduction simulations will not solve for electric
    potential in a structure that has a medium with this 'charge'.

    Example
    -------
    >>> import tidy3d as td
    >>> solid = td.ChargeInsulatorMedium()
    >>> solid2 = td.ChargeInsulatorMedium(permittivity=1.1)

    Note
    ----
        A relative permittivity :math:`\\varepsilon` will be assumed 1 if no value is specified.
    """


class ChargeConductorMedium(AbstractChargeMedium):
    """Conductor medium for conduction simulations.

    Example
    -------
    >>> import tidy3d as td
    >>> solid = td.ChargeConductorMedium(conductivity=3)

    Note
    ----
        A relative permittivity will be assumed 1 if no value is specified.
    """

    conductivity: pd.PositiveFloat = pd.Field(
        1,
        title="Electric conductivity",
        description=f"Electric conductivity of material in units of {CONDUCTIVITY}.",
        units=CONDUCTIVITY,
    )


class SemiconductorMedium(AbstractChargeMedium):
    """
    This class is used to define semiconductors.

    Notes
    -----
        The nonlinear electrostatic Poisson equation is:

        .. math::

            \\begin{equation}
                 - \\nabla \\cdot \\left( \\varepsilon_0 \\varepsilon_r \\nabla \\psi \\right) = q
                \\left( p - n + N_d^+ - N_a^- \\right)
            \\end{equation}


    Currently, only Boltzmann statistics are supported when solving the Drift-Diffusion equations for semiconductors.
    The electron and hole densities, :math:`n` and :math:`p`,
    can be calculated from the conduction/valence bands and quasi-Fermi energy levels. An isothermal system is at a
    constant temperature, and in our current implementation, the temperature is at :math:`T=300K`.

    Since we're considering Boltzmann statistics ( a good approximation in non-degenerate semiconductors) the
    following relations apply:

    .. math::

        \\begin{equation}
            n = N_c \\exp\\left( \\frac{E_{Fn} - E_C}{k_B T} \\right)
        \\end{equation}


    .. math::

        \\begin{equation}
            p = N_v \\exp\\left( \\frac{E_V - E_{Fp}}{k_B T} \\right)
        \\end{equation}


    Currently, an isothermal drift-diffusion model is supported:

    .. math::

        \\begin{equation}
            q \\frac{\\partial n}{\\partial t} = \\nabla \\cdot \\mathbf{J_n} - qR
        \\end{equation}


    In a non-degenerate case:

    .. math::

        \\begin{equation}
            q \\frac{\\partial p}{\\partial t} = -\\nabla \\cdot \\mathbf{J_p} - qR
        \\end{equation}


    The electron and hole current density :math:`\\mathbf{J_n}` & :math:`\\mathbf{J_p}` is solved for steady
    temperature conditions as formalised in [1]_.

    .. math::

        \\begin{equation}
             \\mathbf{J_n} = q \\mu_n \\mathbf{F_{n,e}} + q D_n \\nabla n
        \\end{equation}


    .. math::

        \\begin{equation}
             \\mathbf{J_p} = q \\mu_p \\mathbf{F_{p,e}} - q D_p \\nabla p
        \\end{equation}


    .. math::

        \\begin{equation}
            \\mathbf{F_{eff}} = \\nabla \\left( E_i - \\frac{\\Delta E_g}{2} \\right)
        \\end{equation}

    Let's explore how these material properties are defined as class parameters or other classes.

     .. list-table::
       :widths: 25 25 75
       :header-rows: 1

       * - Symbol
         - Parameter Name
         - Description
       * - :math:`N_a`
         - ``N_a``
         - Ionized acceptors density
       * - :math:`N_d`
         - ``N_d``
         - Ionized donors density
       * - :math:`N_c`
         - ``N_c``
         - Effective density of states in the conduction band.
       * - :math:`N_v`
         - ``N_v``
         - Effective density of states in valence band.
       * - :math:`R`
         - ``R``
         - Generation-Recombination term.
       * - :math:`E_g`
         - ``E_g``
         - Bandgap Energy.
       * - :math:`\\Delta E_g`
         - ``delta_E_g``
         - Bandgap Narrowing.
       * - :math:`\\sigma`
         - ``conductivity``
         - Electrical conductivity.
       * - :math:`\\varepsilon_r`
         - ``permittivity``
         - Relative permittivity.
       * - :math:`q`
         - ``tidy3d.constants.Q_e``
         - Fundamental electron charge.


    .. [1] Schroeder, D., T. Ostermann, and O. Kalz. "Comparison of transport models far the simulation of degenerate semiconductors." Semiconductor science and technology 9.4 (1994): 364.

    Note
    ----
        - Both :math:`N_a` and :math:`N_d` can be either a positive number or an ``xarray.DataArray``.
        - Default values for parameters and models are those appropriate for Silicon.
    """

    N_c: pd.PositiveFloat = pd.Field(
        2.86e19,
        title="Effective density of electron states",
        description=r"$N_c$ Effective density of states in the conduction band.",
        units="cm^(-3)",
    )

    N_v: pd.PositiveFloat = pd.Field(
        3.1e19,
        title="Effective density of hole states",
        description=r"$N_v$ Effective density of states in the valence band.",
        units="cm^(-3)",
    )

    E_g: pd.PositiveFloat = pd.Field(
        1.11,
        title="Band-gap energy",
        description="Band-gap energy",
        units=ELECTRON_VOLT,
    )

    mobility: MobilityModelTypes = pd.Field(
        CaugheyThomasMobility(),
        title="Mobility model",
        description="Mobility model",
    )

    R: Tuple[RecombinationModelTypes, ...] = pd.Field(
        (ShockleyReedHallRecombination(), AugerRecombination(), RadiativeRecombination()),
        title="Generation-Recombination models",
        description="Array containing the R models to be applied to the material.",
    )

    delta_E_g: BandGapNarrowingModelTypes = pd.Field(
        SlotboomBandGapNarrowing(),
        title=r"$\Delta E_g$ Bandgap narrowing model.",
        description="Bandgap narrowing model.",
    )

    N_a: Union[pd.NonNegativeFloat, SpatialDataArray, Tuple[DopingBoxType, ...]] = pd.Field(
        0,
        title="Doping: Acceptor concentration",
        description="Units of 1/cm^3",
        units="1/cm^3",
    )

    N_d: Union[pd.NonNegativeFloat, SpatialDataArray, Tuple[DopingBoxType, ...]] = pd.Field(
        0,
        title="Doping: Donor concentration",
        description="Units of 1/cm^3",
        units="1/cm^3",
    )
