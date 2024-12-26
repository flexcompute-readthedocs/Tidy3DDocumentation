"""
This class defines standard SPICE electrical_analysis types (electrical simulations configurations).
"""

from typing import Optional, Tuple, Union

import pydantic.v1 as pd

from tidy3d.components.base import Tidy3dBaseModel
from tidy3d.components.spice.sources.types import VoltageSourceType
from tidy3d.components.tcad.types import HeatChargeMonitorTypes
from tidy3d.components.types import annotate_type


class ChargeToleranceSpec(Tidy3dBaseModel):
    """
    This class sets some Charge tolerance parameters.

    Example
    -------
    >>> import tidy3d as td
    >>> charge_settings = td.ChargeToleranceSpec(abs_tol=1e8, rel_tol=1e-10, max_iters=30)"""

    abs_tol: pd.PositiveFloat = pd.Field(
        default=1e10,
        title="Absolute tolerance.",
        description="Absolute tolerance used as stop criteria when converging towards a solution. Should be "
        "equivalent to the"
        "SPICE ABSTOL DC transfer parameter. TODO MARC units, TODO check equivalence. TODO what does this mean?",
    )

    rel_tol: pd.PositiveFloat = pd.Field(
        default=1e-10,
        title="Relative tolerance.",
        description="Relative tolerance used as stop criteria when converging towards a solution.  Should be equivalent to the"
        "SPICE RELTOL DC transfer parameter. TODO MARC units, TODO check equivalence. TODO what does this "
        "mean?",
    )

    max_iters: pd.PositiveInt = pd.Field(
        default=30,
        title="Maximum number of iterations.",
        description="Indicates the maximum number of iterations to be run. "
        "The solver will stop either when this maximum of iterations is met "
        "or when the tolerance criteria has been met. Should be equivalent to the ngspice ITL1 parameter. TODO units, "
        "TODO devsim ngspice equivalence",
    )


class SteadyDCAnalysis(Tidy3dBaseModel):
    """This class sets parameters used in DC simulations.

    Ultimately, equivalent to Section 11.3.2 in the ngspice manual.
    """

    input: Optional[Union[VoltageSourceType]] = pd.Field(
        default=None, title="Inputs"
    )  # todo accept a single source
    output: Optional[Tuple[annotate_type(HeatChargeMonitorTypes), ...]] = pd.Field(
        default=None,
        title="Outputs",
    )  # TODO this should be more generic, # TODO this should be a separate generic monitor class.

    tolerance_settings: ChargeToleranceSpec = pd.Field(
        default=ChargeToleranceSpec(), title="Tolerance settings"
    )

    dv: pd.PositiveFloat = pd.Field(
        default=1.0,
        title="Bias step.",
        description="By default, a solution is computed at 0 bias. If a bias different than "
        "0 is requested through a voltage source, DEVSIM will start at 0 and increase bias "
        "at 'dv' intervals until the required bias is reached. This is, therefore, a "
        "convergence parameter in DC computations.",
    )
