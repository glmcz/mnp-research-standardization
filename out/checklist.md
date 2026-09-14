# Minimum reporting checklist — micro/nanoplastic characterisation

Generated from `mnp.schema.models`. Do not edit by hand.

Tick every row, or state explicitly that it was not measured. A blank row is an unreported condition, not a default.

| ✓ | Report | Why it is not optional | Ontology |
|---|---|---|---|
| ☐ | **Polymer / material** | Sets ε, density and chemistry. | `—` |
| ☐ | **Surface functionalisation** | COOH, NH2 and bare latex are different particles at the same nominal size. | `—` |
| ☐ | **Measured hydrodynamic size (nm)** | Nominal size is the supplier's claim, not a measurement. | `NPO:1914` |
| ☐ | **Quantity measured** | Mobility is measured; zeta is a model-dependent conversion of it. | `zeta_potential = ENM:0000092, electrophoretic_mobility = NPO:1315` |
| ☐ | **Dispersion medium, as composed** | A zeta potential is a property of the particle *and* its medium. | `—` |
| ☐ | **Ionic strength (mM)** | Sets the Debye length; without it the mobility curve has no x-axis. | `— (no ontology term exists)` |
| ☐ | **pH** | Sets the dissociation of surface groups. | `—` |
| ☐ | **Temperature (°C)** | Enters ε, η and kT in every model. | `—` |
| ☐ | **Instrument and model** | Different instruments apply different mobility-to-zeta conversions. | `—` |
| ☐ | **Lower size limit (µm)** | The single largest driver of a reported concentration. | `—` |
| ☐ | **Sizing / identification method** | Each method has its own detection floor. | `—` |
| ☐ | **Environmental matrix** | Drinking water and fresh water are different exposure media. | `drinking_water = ENVO:00003064, fresh_water = ENVO:00002011` |
| ☐ | **Digestion chemistry** | KOH dissolves polymers below ~100 nm; proteinase K does not. | `—` |
| ☐ | **Spatial floor (µm)** | What the optics could not have seen. | `—` |
| ☐ | **Size-resolved limit of detection** | A single LOD hides the fact that it varies with size. | `—` |
| ☐ | **Spiked natural-material false-positive control** | The only control that catches pigment-as-polymer assignments. | `—` |
| ☐ | **Procedural blanks** | Reported, not silently subtracted. | `—` |

## One value is not a surface

A single zeta potential describes the particle *in that medium only*. Report at least two ionic strengths, or say plainly that the surface was characterised at one condition.

Ionic strength is unmapped on purpose: no ontology term exists for ionic strength in ENM/NPO/CHMO/ENVO.
