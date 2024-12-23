import tidy3d as td

solid_no_heat = td.MultiPhysicsMedium(
    optical=td.Medium(
        permittivity=5,
        conductivity=0.01,
    ),
    charge=td.ChargeConductorMedium(
        conductivity=1,
    ),
    name="solid_no_heat",
)
