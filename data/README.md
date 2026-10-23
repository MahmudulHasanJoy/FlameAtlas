# Data

All FlameAtlas evidence comes from NASA. The full rules are in the [data specification](../docs/05-data-spec.md); this page is the quick reference.

## Folders

| Folder | Contents | In git? | Created by |
|---|---|---|---|
| `raw/psi/` | NASA PSI combustion investigations: experiment tables, documents, reports (145 files, 311 MB) | Only `manifest.csv` | `python scripts/fetch_psi.py` |
| `raw/ntrs/` | 43 NASA Technical Reports Server papers as PDF plus citation JSON (131 MB) | Only `manifest.csv` | `python scripts/fetch_ntrs.py` |
| `sources/` | Curated source lists, for example `ntrs_papers.csv` | Yes | By hand |
| `extracted/` | Cached model extraction output, one JSON per source | Yes | Extraction run (hackathon) |
| `curated/` | `materials.csv`, `sources.csv`, `records.csv`: the hand-checked evidence base | Yes | Data and Science Lead |
| `processed/` | `cards.jsonl` and the `chroma/` passage index used by the app | Yes | Build step |

## Get the raw data

```bash
python scripts/fetch_psi.py     # about 311 MB; 9 files are missing on NASA's side and are marked in the manifest
python scripts/fetch_ntrs.py    # about 131 MB
```

Both scripts use only the Python standard library, download in parallel and skip files you already have.

## Licenses and credit

- **PSI** data is released under CC0-1.0. Source: NASA Physical Sciences Informatics, https://psi.nasa.gov.
- **NTRS** documents are mostly US Government works; some conference papers carry publisher copyright. PDFs are not redistributed in this repository. Source: NASA Technical Reports Server, https://ntrs.nasa.gov.

## Important finding

PSI experiment tables record test **conditions** (material, oxygen, airflow settings) but rarely **outcomes**. Outcomes such as "Quenched", "No ignition" and "Blow-off" come from the papers, for example Table 7.1 of the BASS-II Summary Report (NTRS 20210011385). Every map record therefore cites a paper or PSI table locator and is checked by a person before it is used.
