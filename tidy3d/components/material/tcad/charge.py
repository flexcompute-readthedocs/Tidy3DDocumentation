"""Defines heat material specifications"""

from __future__ import annotations

from typing import Tuple

import pydantic.v1 as pd

from tidy3d.components.data.data_array import SpatialDataArray
from tidy3d.components.medium import AbstractMedium
from tidy3d.components.tcad.doping import DopingBoxType
from tidy3d.components.tcad.types import (
    AugerRecombination,
    BandGapModelTypes,
    CaugheyThomasMobility,
    MobilityModelTypes,
    RadiativeRecombination,
    RecombinationModelTypes,
    ShockleyReedHallRecombination,
    SlotboomNarrowingBandGap,
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
    >>> solid = ChargeInsulatorMedium()
    >>> solid2 = ChargeInsulatorMedium(permittivity=1.1)

    Note: relative permittivity will be assumed 1 if no value is specified.
    """


class ChargeConductorMedium(AbstractChargeMedium):
    """Conductor medium for conduction simulations.

    Example
    -------
    >>> solid = ChargeConductorMedium(conductivity=3)

    Note: relative permittivity will be assumed 1 if no value is specified.
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
        The drift-diffusion equations for semiconductor materials are defined as follows:

        .. math::

           \\begin{equation}
               -\\nabla \\cdot \\varepsilon \\nabla \\psi = q (p - n + C)
           \\end{equation}

        .. math::

           \\begin{equation}
               \\nabla \\cdot \\mathbf{J_n} - q R = q \\frac{\\partial n}{\\partial t}
           \\end{equation}

        .. math::

           \\begin{equation}
               -\\nabla \\cdot \\mathbf{J_p} - q R = q \\frac{\\partial p}{\\partial t}
           \\end{equation}

        .. math::

           \\begin{equation}
               \\mathbf{J_n} = -q \\mu_n n \\nabla \\psi + q D_n \\nabla n
           \\end{equation}

        .. math::

           \\begin{equation}
               \\mathbf{J_p} = -q \\mu_p p \\nabla \\psi - q D_p \\nabla p
           \\end{equation}

        .. math::

           \\begin{equation}
               C = N_d - N_a
           \\end{equation}

    Let's explore how these material properties are defined as class parameters or other classes.

         .. list-table::
           :widths: 25 25 75
           :header-rows: 1

           * - Symbol
             - Parameter Name
             - Description
           * - :math:`N_a`
             - ```acceptors``
             - TODO_NAME?
           * - :math:`N_d`
             - ```donors``
             - TODO_NAME?
           * - :math:`n`
             - ```nc``
             - Electron concentration TODO_NAME?
           * - :math:`p`
             - ```nv``
             - Hole concentration TODO_NAME?
           * - :math:`R`
             - ``recombination``
             - Generation-recombination term. TODO_NAME?
           * - :math:`E_g`
             - ``recombination``
             - Generation-recombination term. TODO_NAME?
           * - :math:`q`
             - ``tidy3d.constants.Q_e``
             - Fundamental electron charge.

        Both acceptors and donors can be either a positive number or an 'xarray.DataArray'.
        Default values for parameters and models are those appropriate for Silicon
    """

    nc: pd.PositiveFloat = pd.Field(
        2.86e19,
        title="Effective density of electron states",
        description="Effective density of electron states",
        units="cm^(-3)",
    )

    nv: pd.PositiveFloat = pd.Field(
        3.1e19,
        title="Effective density of hole states",
        description="Effective density of hole states",
        units="cm^(-3)",
    )

    eg: pd.PositiveFloat = pd.Field(
        1.11,
        title="Band-gap energy",
        description="Band-gap energy",
        units=ELECTRON_VOLT,
    )

    chi: float = pd.Field(
        4.05, title="Electron affinity", description="Electron affinity", units=ELECTRON_VOLT
    )

    mobility: MobilityModelTypes = pd.Field(
        CaugheyThomasMobility(),
        title="Mobility model",
        description="Mobility model",
    )

    recombination: Tuple[RecombinationModelTypes, ...] = pd.Field(
        (ShockleyReedHallRecombination(), AugerRecombination(), RadiativeRecombination()),
        title="Generation-Recombination models",
        description="Array containing the recombination models to be applied to the material.",
    )

    bandgap: BandGapModelTypes = pd.Field(
        SlotboomNarrowingBandGap(),
        title="Bandgap narrowing model.",
        description="Bandgap narrowing model.",
    )

    acceptors: Union[pd.NonNegativeFloat, SpatialDataArray, Tuple[DopingBoxType, ...]] = pd.Field(
        0,
        title="Doping: Acceptor concentration",
        description="Units of 1/cm^3",
        units="1/cm^3",
    )

    donors: Union[pd.NonNegativeFloat, SpatialDataArray, Tuple[DopingBoxType, ...]] = pd.Field(
        0,
        title="Doping: Donor concentration",
        description="Units of 1/cm^3",
        units="1/cm^3",
    )
