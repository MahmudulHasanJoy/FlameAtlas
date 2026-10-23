# FlameAtlas

**Know what burns before you fly.**

FlameAtlas turns NASA's microgravity fire research into an interactive flammability map, one evidence card per study, and an assistant that answers only from cited NASA sources. It is our entry for the **NASA Space Apps Challenge 2026** challenge *Flame in Freefall*, Dhaka local event.

In microgravity, hot gas does not rise, so cabin airflow decides whether a flame survives. NASA's BASS-II experiment on the ISS found that some materials keep burning at **lower oxygen levels in gentle spacecraft-like airflow than they do on Earth**. FlameAtlas lets a habitat designer pick a material, set oxygen and airflow, and see what NASA's tests say, with every point traceable to its source and a clear `UNTESTED` label where NASA's data runs out.

## Status

| Part | State |
|---|---|
| Documentation (`docs/`) | Baseline v1.0, 2026-10-24 |
| NASA data download (`scripts/`, `data/`) | Done: 24 PSI combustion investigations, 43 NTRS papers |
| Practice prototype (`prototype/`) | Flammability map on 48 BASS-II test results; 22 passing tests |
| Hackathon build (`flameatlas/`) | Built during the hackathon, 14 to 15 November 2026 |

## Documentation

Start with [`docs/README.md`](docs/README.md). The set:

| Document | Contents |
|---|---|
| [01 PRD](docs/01-PRD.md) | Problem, users, user stories, functional and non-functional requirements |
| [02 TRD](docs/02-TRD.md) | Stack, constraints, interfaces, quality targets, cost model |
| [03 SDD](docs/03-SDD.md) | Architecture, UML class, sequence, state, ER and deployment diagrams |
| [04 DRD](docs/04-DRD.md) | Wireframes, chart and status design, accessibility, demo path |
| [05 Data spec](docs/05-data-spec.md) | Sources, schemas, outcome rules, verification workflow |
| [06 AI/RAG spec](docs/06-ai-rag-spec.md) | Extraction, retrieval, boundary model, confidence rule, evaluation |
| [07 Test plan](docs/07-test-plan.md) | 53 test cases and the traceability matrix |
| [08 Project plan](docs/08-project-plan.md) | Timeline, RACI, hackathon run sheet |
| [09 Risk register](docs/09-risk-register.md) | Risks and mitigations |
| [10 Decision log](docs/10-decisions.md) | Architecture decision records |
| [11 Glossary](docs/11-glossary.md) | Fire science, NASA and AI terms |

## Quick start

Try the prototype:

```bash
cd prototype
pip install -r requirements.txt
streamlit run app.py        # opens http://localhost:8501
pytest -q                   # 22 tests
```

Fetch the NASA source data (about 440 MB, not stored in git):

```bash
python scripts/fetch_psi.py
python scripts/fetch_ntrs.py
```

## Repository layout

```text
docs/        documentation set
scripts/     reproducible NASA data download
data/        source lists and manifests (raw downloads are git-ignored); see data/README.md
prototype/   pre-hackathon practice prototype of the flammability map
```

## Team

| Member | Role |
|---|---|
| Md. Mahmudul Hasan | Team Lead, AI and RAG |
| Opi Mojumdar | Dashboard Developer |
| Aurin Subah | Data and Science Developer |
| Syed Mehedi Hussain | Integration and QA Developer |
| Farhan Alam Chowdhury | Story and Presentation Lead |

## Data and credits

- **NASA Physical Sciences Informatics (PSI)**, https://psi.nasa.gov: experiment data from BASS, BASS-II, Saffire and other combustion investigations, released under CC0-1.0.
- **NASA Technical Reports Server (NTRS)**, https://ntrs.nasa.gov: research papers and reports. PDFs are downloaded locally and not redistributed here.
- **NASA Space Apps Challenge 2026**, theme "The Next Frontier".

FlameAtlas summarizes published NASA research for exploration and education. It does not certify materials and does not replace NASA-STD-6001 testing.
