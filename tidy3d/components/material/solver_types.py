"""
Note in the future we might want to implement interpolation models here.
"""

from typing import Union

from tidy3d.components.material.tcad.charge import (
    ChargeConductorMedium,
    ChargeInsulatorMedium,
    SemiconductorMedium,
)
from tidy3d.components.material.tcad.heat import ThermalSpecType
from tidy3d.components.medium import MediumType

OpticalMediumTypes = MediumType
ElectricalMediumTypes = MediumType
HeatMediumTypes = ThermalSpecType
ChargeMediumTypes = Union[ChargeConductorMedium, ChargeInsulatorMedium, SemiconductorMedium]
