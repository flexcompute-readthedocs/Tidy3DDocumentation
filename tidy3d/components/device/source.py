"""Defines device material specifications"""
from __future__ import annotations

from abc import ABC
from typing import Union, Tuple

import pydantic.v1 as pd

from .viz import plot_params_heat_source

from ..base import cached_property
from ..base_sim.source import AbstractSource
from ..data.data_array import TimeDataArray
from ..viz import PlotParams

from ...constants import VOLUMETRIC_HEAT_RATE
from ...exceptions import SetupError
from ...log import log


class DeviceSource(AbstractSource, ABC):
    """Abstract source for device simulations. All source types
    for 'DeviceSimulation' derive from this class."""

    structures: Tuple[str, ...] = pd.Field(
        title="Target Structures",
        description="Names of structures where to apply heat source.",
    )

    @cached_property
    def plot_params(self) -> PlotParams:
        """Default parameters for plotting a Source object."""
        return plot_params_heat_source

    @pd.validator("structures", always=True)
    def check_non_empty_structures(cls, val):
        """Error if source doesn't point at any structures."""
        if len(val) == 0:
            raise SetupError("List of structures for heat source is empty.")

        return val


class HeatSource(DeviceSource):
    """Adds a volumetric heat source (heat sink if negative values
    are provided) to specific structures in the scene.

    Example
    -------
    >>> heat_source = HeatSource(rate=1, structures=["box"])
    """

    rate: Union[float, TimeDataArray] = pd.Field(
        title="Volumetric Heat Rate",
        description="Volumetric rate of heating or cooling (if negative) in units of "
        f"{VOLUMETRIC_HEAT_RATE}.",
        units=VOLUMETRIC_HEAT_RATE,
    )


class HeatFromElectricSource(DeviceSource):
    """Volumetric heat source generated from an electric simulation.
    If a `HeatFromElectricSource` is specified as a source, appropriate boundary
    conditions for an electric simulation must be provided, since such a simulation
    will be executed before the heat simulation can run.

    Example
    -------
    >>> heat_source = HeatFromElectricSource(structures=["box"])
    """


class UniformHeatSource(HeatSource):
    """Volumetric heat source. This class is deprecated. You can use
    'HeatSource' instead.

    Example
    -------
    >>> heat_source = UniformHeatSource(rate=1, structures=["box"])
    """

    # NOTE: this is basically a wrapper for backwards compatibility.

    @pd.root_validator(skip_on_failure=True)
    def issue_warning_deprecated(cls, values):
        """Issue warning for 'UniformHeatSource'."""
        log.warning(
            "'UniformHeatSource' is deprecated and will be discontinued. You can use "
            "'HeatSource' instead."
        )
        return values


DeviceSourceType = Union[HeatSource, HeatFromElectricSource, UniformHeatSource]