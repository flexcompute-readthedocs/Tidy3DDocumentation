from typing import Union

from .multi_physics import MultiPhysicsMedium
from .solver_types import (
    ChargeMediumTypes,
    ElectricalMediumTypes,
    HeatMediumTypes,
    OpticalMediumTypes,
)

StructureMediumTypes = Union[
    MultiPhysicsMedium,
    OpticalMediumTypes,
    ElectricalMediumTypes,
    HeatMediumTypes,
    ChargeMediumTypes,
]
