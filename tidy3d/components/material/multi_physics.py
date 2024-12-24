from typing import Optional

from tidy3d.components.base import Tidy3dBaseModel
from tidy3d.components.material.solver_types import (
    ChargeMediumTypes,
    ElectricalMediumTypes,
    HeatMediumTypes,
    OpticalMediumTypes,
)


class MultiPhysicsMedium(Tidy3dBaseModel):
    """
    A multi-physics medium may contain multiple multi-physical properties, defined for each solver medium.
    """

    # TODO requires backwards compatibility.
    name: Optional[str] = None
    optical: Optional[OpticalMediumTypes] = None
    electrical: Optional[ElectricalMediumTypes] = None
    heat: Optional[HeatMediumTypes] = None
    charge: Optional[ChargeMediumTypes] = None

    @property
    def heat_spec(self):
        if self.heat is not None:
            return self.heat
        elif self.optical is not None:
            return self.optical.heat_spec
        else:
            return None
