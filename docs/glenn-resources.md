# NASA Glenn Combustion Science Resources

Source: https://www.nasa.gov/glenn/glenn-expertise-space-exploration/physical-sciences-program/combustion-science/
Accessed: 2026-11-07

## What this resource provides

NASA Glenn Research Center's Combustion Science Discipline runs idealized combustion experiments on the ISS where the removal of gravity enables study of combustion processes not readily studied on the ground, including spacecraft fire risk.

## Experiments documented (from this page)

| Experiment | Relevance to FlameAtlas | Status in repo |
|---|---|---|
| FM2 — Flammability of Materials on the Moon | First-ever combustion experiment on another planetary body (1/6 g); lunar/Mars habitat fire safety | Not yet in experiments.parquet |
| SoFIE — Solid Fuel Ignition and Extinction | Fire hazard for manned spacecraft; NASA-STD-6001 material screening | NTRS paper downloaded (20210022617); not yet in experiments.parquet |
| FLARE — Flammability Limits At Reduced-g Experiment | Correlate material flammability limits 1-g vs microgravity; international team (JAXA, NASA, ESA, CNES, DLR) | Not yet in experiments.parquet |
| BASS / BASS-II | Burning and suppression of solids in microgravity | ✅ In experiments.parquet (48 curated rows) |
| FLEX / FLEX-2 | Flame extinguishment, limiting oxygen index | NTRS papers downloaded |
| Saffire I–VI | Spacecraft fire safety demonstration | NTRS papers downloaded |
| SAME / SAME-R | Smoke and aerosol measurement | PSI/NTRS downloaded |
| ACME | Advanced Combustion via Microgravity Experiments | PSI/NTRS downloaded |
| SLICE / SPICE | Structure & liftoff / smoke point in co-flow | PSI/NTRS downloaded |

## Facilities documented

| Facility | Details |
|---|---|
| CIR — Combustion Integrated Rack | 100-liter combustion chamber in ISS Destiny module; only ISS rack dedicated to combustion experimentation. Developed by Glenn Research Center. Launched November 2008 (STS-126). |
| MDCA — Multi-user Droplet Combustion Apparatus | Multi-user facility for droplet combustion science, runs in CIR. Launched November 2008. |

## Imagery cached for offline demo

Stored in `demo_fixtures/glenn/`:
- `glenn-combustion-hero.jpg` — ISS CIR hardware (astronaut Jessica Meir)
- `flame-0g.jpg` — microgravity flame
- `acme-chamber.jpg` — ACME chamber insert
- `mdca-parmitano.jpg` / `mdca-rubins.jpg` — MDCA facility operations
- `hopkins-maintenance.jpg` — combustion hardware maintenance
- `bass-logo.png`, `flex-logo.png`, `saffire-logo.png`, `acme-logo.png` — experiment logos

## How these map to the challenge

The Glenn page directly names FM2 and SoFIE — experiments the pasted challenge architecture asks about (FM2 for lunar/Mars partial-gravity, SoFIE for solid-fuel ignition/extinction). Their detail pages are linked from this page and can be fetched next if experiment-level records are needed. The facility docs (CIR, MDCA) give the hardware context judges expect when you name NASA datasets.

## Notes for next steps

- FM2 / SoFIE / FLARE experiment detail pages are linked from this Glenn page and are candidates for extending `experiments.parquet` beyond the current 48 BASS-II rows.
- Imagery above is committed to `demo_fixtures/glenn/` so the frontend can render Glenn facility/experiment images offline (OFFLINE=1 safe).