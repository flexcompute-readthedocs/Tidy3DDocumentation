"""Defines heat material specifications"""

from __future__ import annotations

import pydantic.v1 as pd

from tidy3d.components.spice.sources.types import CurrentSourceTypes, VoltageSourceTypes
from tidy3d.components.tcad.boundary.abstract import HeatChargeBC
from tidy3d.constants import CURRENT_DENSITY, VOLT


class VoltageBC(HeatChargeBC):
    """
    Constant electric potential (voltage) :math:`= \\text{V}` boundary condition.
    Sets a potential at the specified boundary.

    Notes
    -----

        In charge simulations it also accepts an array of voltages.
        In this case, a solution for each of these voltages will
        be computed. TODO DEPRECIATE?

    Example
    -------
    >>> import tidy3d as td
    >>> voltage_source = td.DCVoltageSource(voltage=[-1, 0, 1])
    >>> voltage_bc = td.VoltageBC(source=voltage_source)
    """

    source: VoltageSourceTypes = pd.Field(
        title="Voltage",
        description="Electric potential to be applied at the specified boundary.",
        units=VOLT,
    )


class CurrentBC(HeatChargeBC):
    """
    Current boundary conditions.

    Example
    -------
    >>> import tidy3d as td
    >>> current_source = td.DCCurrentSource(current=1)
    >>> current_bc = CurrentBC(source=current_source)
    """

    source: CurrentSourceTypes = pd.Field(
        title="Current Source",
        description="A current source",
        units=CURRENT_DENSITY,
    )
    # TODO translation between currentsource amps and currentdensity, why not amps here?


class InsulatingBC(HeatChargeBC):
    """Insulation boundary condition.
    Ensures electric fields :math:`\\mathbf{E} = - \\nabla \\psi  = 0` as well as the surface recombination current
    density :math:`J_s = 0` are set to zero.

    Example
    -------
    >>> bc = InsulatingBC()
    """
