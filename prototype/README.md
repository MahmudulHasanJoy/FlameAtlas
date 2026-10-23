# FlameAtlas practice prototype

A small, pre-hackathon practice build of the **Flammability Map**, the core feature described in [`docs/01-PRD.md`](../docs/01-PRD.md). It exists to try out the map design, the boundary model and the data rules on one real NASA data set before the hackathon. The hackathon build lives in the `flameatlas/` package (not started yet).

## What it does

- Plots 48 microgravity test results for SIBAL cotton-fiberglass fabric from **Table 7.1 of the BASS-II Summary Report** (NASA/TM-20210011385, printed page 96), by airflow (log scale) and oxygen.
- Fits the burn boundary with the logistic regression described in [`docs/06-ai-rag-spec.md`](../docs/06-ai-rag-spec.md#5-flammability-boundary-model), and shades the burn region and the untested area.
- Places your habitat on the map with sliders and presets (ISS cabin, and the 10.2 psia and 8.2 psia exploration atmospheres) and labels it `DANGER`, `MARGINAL`, `SELF-EXTINGUISHES` or `UNTESTED`.
- Lists the three nearest NASA tests and shows where each dot comes from when you click it.

Not included yet: Evidence Cards, Ask FlameAtlas, other materials, and the extraction pipeline.

## Data status

The 31 rows of Table 7.1 were turned into 48 records using the flow-sweep rules in [`docs/05-data-spec.md`](../docs/05-data-spec.md#52-flow-sweeps). Every record is marked `status = extracted`: **it has not yet been checked by the Data and Science Lead**, and the app says so. As a consistency check, the records contain exactly six quenching cases, four of them on 2.2 cm samples, which matches the report's own text on printed page 100.

## Run it

```bash
cd prototype
python -m venv .venv && source .venv/bin/activate   # or use the repository's .venv
pip install -r requirements.txt
streamlit run app.py
```

The app opens at http://localhost:8501. No API key or network access is needed.

## Test it

```bash
cd prototype
pytest -q
```

22 tests: 17 unit tests of the boundary, envelope, status and nearest-test rules (IDs match [`docs/07-test-plan.md`](../docs/07-test-plan.md)), and 5 headless app tests using Streamlit's `AppTest`.

## Files

| File | Purpose |
|---|---|
| `app.py` | Streamlit page: controls, status, map, nearest tests, evidence on click |
| `core.py` | Pure functions: `fit_boundary`, `classify_habitat`, `nearest_tests`, `pressure_mismatch`, `boundary_grid` |
| `data/sibal_bass_table71.csv` | The 48 records, in the `records.csv` schema from the data spec |
| `tests/` | Unit and app tests |
| `.streamlit/config.toml` | Locks the light theme (ADR-0014) |

## What we learned

- With real data the fitted boundary for 2.2 cm SIBAL shows the **quenching side** clearly (flames went out at 2.2 to 2.8 cm/s near 17 to 19% O2) but not the blowoff side, because Table 7.1 has only one blowoff case. The full U shape needs more sources.
- At 21% O2 the fabric kept burning down to about 2 to 2.5 cm/s in these tests, so the demo cannot show the status flipping to "self-extinguishes" just by lowering airflow at ISS oxygen levels. The DRD demo path must be adjusted to the verified data.
- All tests were at about 16 to 21% O2, so the 34% O2 exploration atmosphere is correctly shown as `UNTESTED`.
