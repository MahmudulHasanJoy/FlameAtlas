# 10 Decision Log

Architecture decision records (ADRs) for FlameAtlas. Each record states the context, the decision, the options considered and the consequences. Records are never rewritten; a changed decision gets a new record that supersedes the old one.

| Version | Date | Change |
|---|---|---|
| 1.0 | 2026-10-24 | ADR-0001 to ADR-0014 recorded |

## Index

| ADR | Decision | Status | Date |
|---|---|---|---|
| [0001](#adr-0001-python-and-streamlit-for-the-whole-app) | Python and Streamlit for the whole app | Accepted | 2026-10-24 |
| [0002](#adr-0002-plotly-for-the-flammability-map) | Plotly for the flammability map | Accepted | 2026-10-24 |
| [0003](#adr-0003-rag-with-a-local-chromadb-index-no-mcp) | RAG with a local ChromaDB index, no MCP | Accepted | 2026-10-24 |
| [0004](#adr-0004-claude-as-the-language-model) | Claude as the language model | Accepted | 2026-10-24 |
| [0005](#adr-0005-a-person-verifies-every-map-record) | A person verifies every map record | Accepted | 2026-10-24 |
| [0006](#adr-0006-logistic-regression-boundary-with-a-tested-envelope) | Logistic regression boundary with a tested envelope | Accepted | 2026-10-24 |
| [0007](#adr-0007-four-habitat-states-and-no-safe-label) | Four habitat states and no "Safe" label | Accepted | 2026-10-24 |
| [0008](#adr-0008-confidence-is-computed-by-a-rule-not-by-the-model) | Confidence is computed by a rule, not by the model | Accepted | 2026-10-24 |
| [0009](#adr-0009-send-page-tagged-text-not-pdfs-for-extraction) | Send page-tagged text, not PDFs, for extraction | Accepted | 2026-10-24 |
| [0010](#adr-0010-flow-sweeps-become-one-record-per-stated-flow) | Flow sweeps become one record per stated flow | Accepted | 2026-10-24 |
| [0011](#adr-0011-no-ignition-counts-as-not-burning) | "No ignition" counts as not burning | Accepted | 2026-10-24 |
| [0012](#adr-0012-raw-data-out-of-git-processed-data-in-git) | Raw data out of git, processed data in git | Accepted | 2026-10-24 |
| [0013](#adr-0013-local-embeddings) | Local embeddings | Accepted | 2026-10-24 |
| [0014](#adr-0014-light-theme-only) | Light theme only | Accepted | 2026-10-24 |

---

## ADR-0001: Python and Streamlit for the whole app

**Context.** Four developers have 48 hours. All know Python; not all know JavaScript. The app needs a few widgets, one interactive chart and a chat box.

**Decision.** Build the whole app in Python with Streamlit.

**Options considered.**

| Option | For | Against |
|---|---|---|
| Streamlit | One language; widgets, chat input, dialogs built in; free hosting | Reruns the script on each interaction; limited layout control |
| React frontend and FastAPI backend | Full control | Two codebases and an API contract to maintain in 48 hours |
| Dash | Python, strong Plotly integration | Callback model has a steeper learning curve for the team |

**Consequences.** Any developer can work on any part. Slow work must be cached (`st.cache_resource`) because of reruns. Layout stays simple, which also suits design goal 5 ("nothing fancy").

## ADR-0002: Plotly for the flammability map

**Context.** The map needs a log-scale axis, markers with shapes, a filled region, a contour line, hatch fills, hover text and click selection.

**Decision.** Use Plotly through `st.plotly_chart` with `on_select="rerun"`.

**Options considered.** Altair (good, but contour and hatch fills are awkward); Matplotlib (static, no click events).

**Consequences.** Click events return the selected point index, which maps to a `record_id`. Plotly `fillpattern` gives the hatched untested area without custom code.

## ADR-0003: RAG with a local ChromaDB index, no MCP

**Context.** Judges score Validity. Answers must come from NASA sources and show them. The corpus is small (43 papers, about 2,000 to 3,000 chunks).

**Decision.** Retrieval-augmented generation over a local, file-based ChromaDB collection bundled with the app. Do not build an MCP server for the hackathon.

**Options considered.**

| Option | For | Against |
|---|---|---|
| Local ChromaDB | No server, no account, works offline, small | SQLite version requirement on some hosts (R-07) |
| Hosted vector database | Scales | Account, network dependency, nothing to gain at this size |
| No retrieval (model knowledge) | Simple | Unverifiable; fails the Validity criterion |
| MCP server exposing the evidence base | Lets other AI tools query FlameAtlas | Setup time with no visible benefit in a 48-hour demo |

**Consequences.** Every answer can show the exact passages used. An MCP server remains a P2 stretch idea and is listed under future work.

## ADR-0004: Claude as the language model

**Context.** The model must (a) produce schema-valid extraction output, (b) cite exact passages, and (c) be cheap enough for a USD 25 budget.

**Decision.** Use the Anthropic Claude API with `claude-opus-5-5`: structured outputs for extraction and question parsing, native document citations for answers, and the Message Batches API (50% price) for extraction. `claude-sonnet-5-5` (half the price per token) is the fallback, switched by one setting.

**Options considered.** Other providers were considered for free tiers. They were rejected because native citation spans (exact quoted text with page) are central to the Validity story and would otherwise have to be built and checked by hand.

**Consequences.** Cost is estimated at about USD 21 for the whole project (TRD Section 8). The app depends on one external API, so the map and cards are designed to work without it (NFR-REL-01). Citations cannot be combined with structured outputs in the same call, so answers use citations and parsing uses structured outputs, in separate calls.

## ADR-0005: A person verifies every map record

**Context.** Wrong data on a fire-safety map is the worst failure this product can have (R-01). Models make extraction errors, especially with tables and units.

**Decision.** The model only proposes records. A record is drawn only after the Data and Science Lead has checked it against its locator and set `status = verified`. A second person re-checks a random 10%.

**Consequences.** Verification is the throughput bottleneck. That is why sources with outcome tables are processed first and figure-only data is optional. The About panel can truthfully say every point was hand-checked.

## ADR-0006: Logistic regression boundary with a tested envelope

**Context.** NASA reports a U-shaped flammability boundary in oxygen versus flow (quenching at low flow, blowoff at high flow), with the U visible on a log flow axis (NTRS 20210011385, Figs. 6.9 and 6.10). We need a boundary that is reproducible, cheap to evaluate on each slider move, and honest where there are no tests.

**Decision.** Fit P(burn) with logistic regression on O2, log₂(flow) and log₂(flow)², per material, variant and flow direction, with an 8-point, 3-and-3 data-sufficiency rule and a positive-O2-coefficient check. Trust predictions only inside an expanded convex hull of the tests.

**Options considered.**

| Option | For | Against |
|---|---|---|
| Logistic regression with a quadratic flow term | Simple, fast, gives a probability, produces a U shape | Smooth curve; may not capture sharp limits |
| Hand-drawn curve | Matches the paper exactly | Not reproducible; cannot classify a new point |
| NASA's published equation per material | Authoritative | Exists for PMMA rods only, in stretch rate rather than flow |
| Gaussian process or SVM | Flexible | Harder to explain; overfits small data |

**Consequences.** The fitted boundary is a summary of tests, not a physical model. The envelope prevents confident claims far from data. TC-14 compares the rod boundary with NASA's Eq. 6.1 as a plausibility check.

## ADR-0007: Four habitat states and no "Safe" label

**Context.** The original brief used "Safe" and "Danger". A tool built on a few dozen tests cannot certify safety, and a point far from any test would be labeled "Safe" by a two-state classifier.

**Decision.** Use `DANGER`, `MARGINAL`, `SELF-EXTINGUISHES` and `UNTESTED` (plus `NO BOUNDARY` when no boundary can be fitted). The interface never uses the word "safe" for a material.

**Consequences.** The 34% O2 exploration-atmosphere preset shows `UNTESTED` for most materials. This is an honest result and a strong demo moment: it shows exactly where NASA's data runs out.

## ADR-0008: Confidence is computed by a rule, not by the model

**Context.** Language models are not reliable judges of their own certainty, and a confidence level that changes between identical runs would undermine trust.

**Decision.** Confidence (`HIGH`, `MEDIUM`, `LOW`, `GAP`) is computed in Python from the number, closeness and agreement of verified records and retrieved passages, before any answer is written ([AI/RAG spec](06-ai-rag-spec.md#63-confidence-rule)).

**Consequences.** Confidence is repeatable and explainable in one line. A `GAP` result skips generation, which also saves cost.

## ADR-0009: Send page-tagged text, not PDFs, for extraction

**Context.** The 43 papers have extractable text. Sending PDFs as documents costs extra tokens per page for the page images, and the outcome tables we need are readable in text extracted with layout preserved.

**Decision.** Send page-tagged plain text to the extraction model. Values that exist only in figures are entered by hand (`manual_figure`).

**Consequences.** Lower cost and exact page numbers for locators. The model cannot read plotted points; this is acceptable because figure values need careful human digitizing anyway.

## ADR-0010: Flow sweeps become one record per stated flow

**Context.** Many BASS-II tests changed the flow during one burn (for example "10 to 2.2 cm/s, Quenched"). One row per test would lose the information that the flame survived at 10 cm/s and went out at 2.2 cm/s.

**Decision.** Create one record per flow value stated in the source, using the rules in the [data spec](05-data-spec.md#52-flow-sweeps). Never invent intermediate flows.

**Consequences.** BASS-II Table 7.1 (31 rows) yields 48 records. Records from the same test are not independent; the confidence rule therefore requires agreement across at least two distinct tests for `HIGH`.

## ADR-0011: "No ignition" counts as not burning

**Context.** Some tests report that a sample did not ignite (for example SIBAL at 16.4% O2, Table 7.1). Failure to ignite can reflect the igniter rather than the material.

**Decision.** `no_ignition` is labeled 0 (not burning) in the fit, shown with its own marker, and excluded from the fit only when the source gives a reason to doubt it (for example a reused sample).

**Consequences.** Low-oxygen non-ignition results help define the bottom of the boundary, which NASA notes is hard to measure by changing flow alone.

## ADR-0012: Raw data out of git, processed data in git

**Context.** Raw downloads are about 440 MB. The hosted app must start without running the pipeline.

**Decision.** `data/raw/` is git-ignored except its manifests, and fetch scripts recreate it. `data/curated/`, `data/extracted/` and `data/processed/` (including the Chroma index) are committed.

**Consequences.** The repository stays small, deploys are self-contained, and anyone can reproduce the raw data with two commands.

## ADR-0013: Local embeddings

**Context.** Claude does not provide an embeddings endpoint. The corpus is small and fixed.

**Decision.** Use ChromaDB's default `all-MiniLM-L6-v2` ONNX embedding model, run locally on CPU.

**Consequences.** No embedding cost or network calls. Retrieval quality is adequate for a small technical corpus, and the relevance threshold is tuned on the evaluation set.

## ADR-0014: Light theme only

**Context.** Several of the colorblind-safe marker and badge colors fall below 3:1 contrast on Streamlit's dark background (for example gray `#595959` measures 2.70:1 on `#0E1117`).

**Decision.** Lock the app to Streamlit's light theme in `.streamlit/config.toml`.

**Consequences.** All colors meet WCAG 2.1 AA in the only theme offered ([DRD](04-DRD.md#10-accessibility-checklist)).
