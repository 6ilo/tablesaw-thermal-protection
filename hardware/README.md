# Hardware

Physical build artifacts for the retrofit. Currently a stub — contents land here as the project moves from paper design to bench build.

## Intended structure

```
hardware/
├── schematic/     KiCad or hand-drawn schematic of the low-voltage side
│                  (ESP32, MAX31855, relay driver, NTC divider, isolated PSU)
├── enclosure/     3D-printable brackets, panel cutouts, or mounting fixtures
├── photos/        Annotated photos of the built system: A202C terminal
│                  block with retrofit taps marked, sensor mounting on
│                  the winding, enclosure interior
├── BOM.csv        Machine-readable BOM — verified purchases + not-yet-
│                  ordered items with recommended part numbers
└── datasheets/    PDF copies of datasheets for parts that get hard to
                   find later (Marathon motor plate, Gould A202C wiring
                   diagram, MAX31855, chosen thermostat, isolated PSU)
```

## Where the design currently lives

Until artifacts exist here, the design of record is:

- [`../ARCHITECTURE.md`](../ARCHITECTURE.md) — Coil circuit, Power supply, Wiring diagram, Pin assignments, Sensor mounting, Bill of materials
- [`../BUILD-TONIGHT.md`](../BUILD-TONIGHT.md) — § 3 Wiring, § 6 Sensor mounting for the same-day expedient build

When the schematic or photos land here, extract the BOM to `BOM.csv` and update the top-level `ARCHITECTURE.md` to link into this directory rather than duplicating the material.

## Safety

Every wiring section in the design docs applies to any work in this directory. See the DANGER block at the top of [`../ARCHITECTURE.md`](../ARCHITECTURE.md) and [`../BUILD-TONIGHT.md § 3`](../BUILD-TONIGHT.md).
