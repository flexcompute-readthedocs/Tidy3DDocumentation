"""
Our DC sources ultimately need to follow this standard form if we want to enable full electrical integration.

```
11.3.2 .DC: DC Transfer Function

General form:

    .dc srcnam vstart vstop vincr [src2 start2 stop2 incr2]

Examples:

    .dc VIN 0.25 5.0 0.25
    .dc VDS 0 10 .5 VGS 0 5 1
    .dc VCE 0 10 .25 IB 0 10u 1u
    .dc RLoad 1k 2k 100
    .dc TEMP -15 75 5
```

"""

from typing import Union

from tidy3d.components.base import Tidy3dBaseModel
from tidy3d.constants import AMP, VOLT


class DCTransferSource(Tidy3dBaseModel):
    name: str
    values: list = []
    units: Union[VOLT, AMP] = VOLT


MultiDCTransferSource = list[DCTransferSource]
