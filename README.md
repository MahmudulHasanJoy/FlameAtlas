# FlameAtlas

**Know what burns before you fly.**

FlameAtlas is a microgravity fire-safety explorer — your entry for the **NASA Space Apps Challenge 2026**, challenge *"Flame in Freefall"*, theme *"The Next Frontier"*, Dhaka local event.

It answers one question for spacecraft and habitat designers: **"Will this material burn up there?"**

Set oxygen concentration, pressure, flow velocity, and material, and a U-shaped logistic boundary (oxygen, log airflow, log airflow²) fitted to 47 measured SIBAL microgravity tests predicts the flame-spread regime (`no_spread` / `marginal_spread` / `spread`), with class probabilities, an out-of-range guard, and an explanation layer that cites the nearest real experiments by report ID and NTRS URL.

## What's in the repo

| Part | State |
|---|---|
| `src/api/app.py` | FastAPI app: dashboard at `/`, `POST /predict`, `GET /boundary`, `GET /health` — U-shaped logistic boundary, training-range guard, nearest-experiment retrieval, evidence cards, material profiles |
| `src/compute/model.py` | Training pipeline: U-shaped logistic regression on measured SIBAL tests (BASS-II Table 7.1 and Saffire I-IV), repeated cross-validation against an always-burns baseline and a gradient-boosting comparison, model artifact + metadata |
| `cache/experiments.parquet` | 620 rows parsed (54 with oxygen, flow and outcome are used for training; 38 are SIBAL) from PSI experimental tables + BASS-II (O₂, pressure, flow, material, outcome, report_id, source_url) |
| `scripts/build_experiments_parquet.py` | Column-mapping parser for all 22 PSI experimental-table CSVs (BASS-II, SAFFIRE-1/2, FLEX, FLEX-2, CFI, CFI-G, ACME BRE, Flame Design) |
| `scripts/fetch_ntrs.py` | Downloads all 44 NTRS papers (PDF + citation JSON) |
| `frontend/dashboard.html` | Served at `/`; self-contained dark/light-mode slider UI with Plotly decision-boundary plot, probability bar, nearest-experiment citations |
| `data/processed/` | Evidence cards (11), evidence points (51) and material profiles (4), each with source quotes; `cards_verification.json` holds the quote-check result |
| `scripts/verify_cards.py` | Checks every quote against its NASA source PDF page or PSI table row |
| `docs/` | 12 spec documents, updated to the as-built app on 2026-11-13: PRD, TRD, SDD, DRD, data spec, AI/RAG spec, test plan, project plan, risk register, decision log, glossary, Glenn resources |
| `demo_fixtures/` | Offline demo fixtures (sample predictions, Glenn imagery) |
| `LICENSE` | Apache-2.0 |

## Quick start

The FastAPI app serves both the dashboard and the API from one address.

```bash
pip install -r requirements.txt
cp .env.example .env            # then fill in FLAMEATLAS_API_KEY
uvicorn src.api.app:app --port 8000
```

Open http://127.0.0.1:8000. The dashboard needs no key; the server accepts
same-origin requests from it. Direct API calls need the `X-API-Key` header:

```bash
curl -X POST http://127.0.0.1:8000/predict \
  -H "Content-Type: application/json" -H "X-API-Key: $FLAMEATLAS_API_KEY" \
  -d '{"oxygen_pct": 21, "pressure_kpa": 101.3, "flow_cm_s": 10, "material": "sibal"}'
```

Run the tests with `pytest tests` (API) and `cd prototype && pytest` (prototype).

**Retrain the model** (optional):

```bash
python scripts/build_experiments_parquet.py
python src/compute/model.py
```

**Fetch raw NASA data** (optional, git-ignored, about 440 MB):

```bash
python scripts/fetch_psi.py
python scripts/fetch_ntrs.py
```

## Deploy (Render)

`render.yaml` defines one free web service. In Render choose **New > Blueprint**,
pick this repository, and set `FLAMEATLAS_API_KEY` when asked. Render installs
`requirements.txt`, starts uvicorn, and checks `/health`. Pushes to `main`
redeploy automatically. The free tier sleeps when idle, so the first visit can
take about a minute.

## Features

- **Flame-spread prediction** — U-shaped logistic boundary in the form NASA uses for low-gravity flammability; held-out accuracy 81.5% against a 78.7% always-burns baseline (gradient boosting scored 78.7% on the same data). Within NASA's tested airflows the data show the low-flow (quenching) side of the U, and the plot says so
- **Evidence cards** — 10 NASA studies (BASS, BASS-II, Saffire I/II/IV/V, FM2, exploration atmospheres) summarized as cards with conditions, key finding, safety takeaway and the exact source quotes; open one from the evidence section, a map point, or a nearest experiment
- **Material profiles** — SIBAL, PMMA, Nomex and silicone: what each is, Earth and microgravity limits, spacecraft use and data status, every fact linked to its NASA quote
- **Evidence-only maps** — for PMMA, Nomex and silicone the map plots the individual NASA test results instead of a prediction
- **Research-gap response** — materials NASA tested but whose outcomes are not in the dataset yet (PMMA, Nomex) return no prediction and say why
- **Out-of-range guard** — if requested conditions fall outside the training envelope, returns no prediction and an explanation; never extrapolates silently
- **Nearest experiments** — each prediction links to the 3 closest real NASA tests by feature distance, with report IDs and clickable NTRS citations
- **Habitat presets** — ISS cabin (21% O₂, 101.3 kPa) and the two exploration atmospheres from NASA/TM-20260003925 (26.5% O₂ at 70.3 kPa, 34% O₂ at 56.5 kPa)
- **Labeled test points** — the map shows only the selected material's tests with recorded outcomes; a toggle adds other materials' tests and tests with no recorded outcome in grey, each labeled
- **Decision-boundary plot** — P(spread) heatmap over O₂ × airflow with the P = 0.5 contour and real experiment points overlaid
- **Light/dark mode** — toggle in the header, persists in localStorage, respects OS preference
- **Mobile responsive** — single-column stack on phones, two-column on tablets, three-column on desktop
- **Offline demo** — `demo_fixtures/` contains sample predictions so the UI can run without live data

## Evidence cards

Cards live in `data/processed/cards.json`. Each card lists the exact quotes its
summary is based on, with the PDF page or PSI table row. Check every quote word
for word against the downloaded sources with:

```bash
python scripts/verify_cards.py   # needs pdftotext and the fetched NTRS/PSI files
```

The result (with source file SHA-256 hashes) is written to
`data/processed/cards_verification.json` and shown in the app. Takeaways marked
"FlameAtlas interpretation" are written from the quotes and have not yet been
reviewed by a domain expert.

## Data sources

| Source | Role | Status |
|---|---|---|
| NASA PSI (Physical Sciences Informatics) | Combustion experiment tables (BASS, BASS-II, SAFFIRE, FLEX, CFI, ACME, …) | 22 experimental-table CSVs downloaded, parsed into `experiments.parquet` |
| NASA NTRS (Technical Reports Server) | Research papers and reports | 44 papers downloaded (PDF + citation JSON), 0 failures |
| NASA Glenn Combustion Science | Experiment documentation, facility docs (CIR, MDCA), imagery | Documented in `docs/glenn-resources.md`, imagery cached in `demo_fixtures/glenn/` |

All PSI data is CC0-1.0. NTRS documents are mostly US Government works. Raw downloads (~440 MB) are git-ignored; only manifests and curated tables are committed.

## Documentation

Start with [`docs/README.md`](docs/README.md). The full set:

| Document | Contents |
|---|---|
| [01 PRD](docs/01-PRD.md) | Problem, users, user stories, functional and non-functional requirements |
| [02 TRD](docs/02-TRD.md) | Stack, constraints, interfaces, quality targets, cost model |
| [03 SDD](docs/03-SDD.md) | Architecture, UML diagrams, deployment |
| [04 DRD](docs/04-DRD.md) | Wireframes, chart and status design, accessibility, demo path |
| [05 Data spec](docs/05-data-spec.md) | Sources, schemas, outcome rules, verification workflow |
| [06 AI/RAG spec](docs/06-ai-rag-spec.md) | Boundary model, confidence rule, evaluation |
| [07 Test plan](docs/07-test-plan.md) | Test cases and traceability matrix |
| [08 Project plan](docs/08-project-plan.md) | Timeline, RACI, hackathon run sheet |
| [09 Risk register](docs/09-risk-register.md) | Risks and mitigations |
| [10 Decision log](docs/10-decisions.md) | Architecture decision records (ADR-0001 to 0021) |
| [11 Glossary](docs/11-glossary.md) | Fire science, NASA and AI terms |
| [Glenn resources](docs/glenn-resources.md) | NASA Glenn Combustion Science experiments and facilities |

## Team

| Member | Role | Affiliation |
|---|---|---|
| Md. Mahmudul Hasan | Researcher | CSE, Independent University, Bangladesh |
| Meharab Hossen Opi | DevOps | CSE, Independent University, Bangladesh |
| Aurin Subah | Data Analyst | CSE, Independent University, Bangladesh |
| Syed Mehedi Hussain | System Architect | CSE, Independent University, Bangladesh |
| Meem Arafat Hossain | QA & IoT Developer | EEE, Khulna University of Engineering & Technology |
| Farhan Alam Chowdhury | Creative Lead | BBA, Bangladesh University of Business and Technology |

## Caveats

- FlameAtlas summarizes published NASA research for exploration and education. It does **not** certify materials and does **not** replace NASA-STD-6001 testing.
- The boundary model is trained on BASS-II and related PSI results; extrapolation outside tested conditions returns `UNTESTED` / no prediction.
- Raw NASA data (~440 MB) is not stored in git; run the fetch scripts to obtain it.

## License

Apache-2.0. Public repository.
