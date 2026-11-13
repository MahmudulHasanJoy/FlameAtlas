# FlameAtlas

**Know what burns before you fly.**

FlameAtlas is a microgravity fire-safety explorer — your entry for the **NASA Space Apps Challenge 2026**, challenge *"Flame in Freefall"*, theme *"The Next Frontier"*, Dhaka local event.

It answers one question for spacecraft and habitat designers: **"Will this material burn up there?"**

Set oxygen concentration, pressure, flow velocity, and material, and a gradient-boosting model trained on published NASA microgravity combustion results predicts the flame-spread regime (`no_spread` / `marginal_spread` / `spread`), with class probabilities, an out-of-range guard, and an explanation layer that cites the nearest real experiments by report ID and NTRS URL.

## What's in the repo

| Part | State |
|---|---|
| `src/api/app.py` | FastAPI app: dashboard at `/`, `POST /predict`, `GET /boundary`, `GET /health` — gradient-boosting classifier, honest cross-validation, training-range guard, nearest-experiment retrieval |
| `src/compute/model.py` | Training pipeline: gradient-boosting on `cache/experiments.parquet`, stratified CV, model artifact + metadata |
| `cache/experiments.parquet` | 620 rows parsed (54 with oxygen, flow and outcome are used for training; 38 are SIBAL) from PSI experimental tables + BASS-II (O₂, pressure, flow, material, outcome, report_id, source_url) |
| `scripts/build_experiments_parquet.py` | Column-mapping parser for all 22 PSI experimental-table CSVs (BASS-II, SAFFIRE-1/2, FLEX, FLEX-2, CFI, CFI-G, ACME BRE, Flame Design) |
| `scripts/fetch_ntrs.py` | Downloads all 43 NTRS papers (PDF + citation JSON) |
| `frontend/dashboard.html` | Served at `/`; self-contained dark/light-mode slider UI with Plotly decision-boundary plot, probability bar, nearest-experiment citations |
| `docs/` | 12 spec documents: PRD, TRD, SDD, DRD, data spec, AI/RAG spec, test plan, project plan, risk register, decision log, glossary, Glenn resources |
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

- **Flame-spread prediction** — gradient-boosting classifier with honest stratified cross-validation (CV accuracy reported, not invented)
- **Research-gap response** — materials NASA tested but whose outcomes are not in the dataset yet (PMMA, Nomex) return no prediction and say why
- **Out-of-range guard** — if requested conditions fall outside the training envelope, returns no prediction and an explanation; never extrapolates silently
- **Nearest experiments** — each prediction links to the 3 closest real NASA tests by feature distance, with report IDs and clickable NTRS citations
- **Decision-boundary plot** — P(spread) heatmap over O₂ × airflow with the P = 0.5 contour and real experiment points overlaid
- **Light/dark mode** — toggle in the header, persists in localStorage, respects OS preference
- **Mobile responsive** — single-column stack on phones, two-column on tablets, three-column on desktop
- **Offline demo** — `demo_fixtures/` contains sample predictions so the UI can run without live data

## Data sources

| Source | Role | Status |
|---|---|---|
| NASA PSI (Physical Sciences Informatics) | Combustion experiment tables (BASS, BASS-II, SAFFIRE, FLEX, CFI, ACME, …) | 22 experimental-table CSVs downloaded, parsed into `experiments.parquet` |
| NASA NTRS (Technical Reports Server) | Research papers and reports | 43 papers downloaded (PDF + citation JSON), 0 failures |
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
| [10 Decision log](docs/10-decisions.md) | Architecture decision records (ADR-0001 to 0014) |
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
