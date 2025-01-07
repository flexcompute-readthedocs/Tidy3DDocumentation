"""Defines heat material specifications"""

from __future__ import annotations

import pydantic.v1 as pd

from tidy3d.components.spice.sources.types import VoltageSourceTypes
from tidy3d.components.tcad.boundary.abstract import HeatChargeBC
from tidy3d.constants import CURRENT_DENSITY, VOLT


class VoltageBC(HeatChargeBC):
    """Electric potential (voltage) boundary condition.
    Sets a potential at the specified boundary.
    In charge simulations it also accepts an array of voltages.
    In this case, a solution for each of these voltages will
    be computed.

    Example
    -------
    >>> bc1 = VoltageBC(source=2)
    >>> bc2 = VoltageBC(source=[-1, 0, 1])
    """

    source: VoltageSourceTypes = pd.Field(
        title="Voltage",
        description="Electric potential to be applied at the specified boundary.",
        units=VOLT,
    )


class CurrentBC(HeatChargeBC):
    """Current boundary conditions.

    Example
    -------
    >>> bc = CurrentBC(current_density=1)
    # TODO Marc how can we make this a current source spice?
    """

    current_density: pd.FiniteFloat = pd.Field(
        title="Current density",
        description="Current density.",
        units=CURRENT_DENSITY,
    )


class InsulatingBC(HeatChargeBC):
    """Insulation boundary condition.
    Ensures electric fields as well as the surface R current density
    are set to zero.

    Example
    -------
    >>> bc = InsulatingBC()
    """
