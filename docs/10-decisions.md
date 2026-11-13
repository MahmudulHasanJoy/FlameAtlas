# 10 Decision Log

Architecture decision records (ADRs) for FlameAtlas. Each record states the context, the decision, the options considered and the consequences. Records are never rewritten; a changed decision gets a new record that supersedes the old one.

| Version | Date | Change |
|---|---|---|
| 1.0 | 2026-10-24 | ADR-0001 to ADR-0014 recorded |
| 1.1 | 2026-11-13 | ADR-0015 to ADR-0022 recorded from the build; superseded records marked in the index |

## Index

| ADR | Decision | Status | Date |
|---|---|---|---|
| [0001](#adr-0001-python-and-streamlit-for-the-whole-app) | Python and Streamlit for the whole app | Superseded by 0015 | 2026-10-24 |
| [0002](#adr-0002-plotly-for-the-flammability-map) | Plotly for the flammability map | Accepted | 2026-10-24 |
| [0003](#adr-0003-rag-with-a-local-chromadb-index-no-mcp) | RAG with a local ChromaDB index, no MCP | Deferred (0017) | 2026-10-24 |
| [0004](#adr-0004-claude-as-the-language-model) | Claude as the language model | Deferred (0017) | 2026-10-24 |
| [0005](#adr-0005-a-person-verifies-every-map-record) | A person verifies every map record | Accepted | 2026-10-24 |
| [0006](#adr-0006-logistic-regression-boundary-with-a-tested-envelope) | Logistic regression boundary with a tested envelope | Superseded by 0016 | 2026-10-24 |
| [0007](#adr-0007-four-habitat-states-and-no-safe-label) | Four habitat states and no "Safe" label | Accepted | 2026-10-24 |
| [0008](#adr-0008-confidence-is-computed-by-a-rule-not-by-the-model) | Confidence is computed by a rule, not by the model | Accepted | 2026-10-24 |
| [0009](#adr-0009-send-page-tagged-text-not-pdfs-for-extraction) | Send page-tagged text, not PDFs, for extraction | Accepted | 2026-10-24 |
| [0010](#adr-0010-flow-sweeps-become-one-record-per-stated-flow) | Flow sweeps become one record per stated flow | Accepted | 2026-10-24 |
| [0011](#adr-0011-no-ignition-counts-as-not-burning) | "No ignition" counts as not burning | Accepted | 2026-10-24 |
| [0012](#adr-0012-raw-data-out-of-git-processed-data-in-git) | Raw data out of git, processed data in git | Accepted | 2026-10-24 |
| [0013](#adr-0013-local-embeddings) | Local embeddings | Deferred (0017) | 2026-10-24 |
| [0014](#adr-0014-light-theme-only) | Light theme only | Superseded by 0019 | 2026-10-24 |
| [0015](#adr-0015-fastapi-service-with-a-static-dashboard) | FastAPI service with a static dashboard | Accepted | 2026-11-13 |
| [0016](#adr-0016-gradient-boosting-classifier-for-the-boundary) | Gradient-boosting classifier for the boundary | Superseded by 0022 | 2026-11-13 |
| [0017](#adr-0017-defer-ask-flameatlas) | Defer Ask FlameAtlas | Accepted | 2026-11-13 |
| [0018](#adr-0018-machine-checked-quotes-for-cards-and-profiles) | Machine-checked quotes for cards and profiles | Accepted | 2026-11-13 |
| [0019](#adr-0019-dark-and-light-themes) | Dark and light themes | Accepted | 2026-11-13 |
| [0020](#adr-0020-render-single-service-deployment) | Render single-service deployment | Accepted | 2026-11-13 |
| [0021](#adr-0021-evidence-only-materials) | Evidence-only materials | Accepted | 2026-11-13 |
| [0022](#adr-0022-u-shaped-logistic-boundary-on-measured-tests-only) | U-shaped logistic boundary on measured tests only | Accepted | 2026-11-13 |

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

## ADR-0015: FastAPI service with a static dashboard

**Context.** The team built the map as a FastAPI prediction API and a self-contained HTML dashboard rather than in Streamlit (ADR-0001). The first version served the page from `file://`, called `http://127.0.0.1:8000` and embedded the API key in the page, so it could not be deployed and the key was visible to anyone.

**Decision.** One FastAPI app serves the dashboard at `/` and the JSON API on the same origin. Direct API calls need `X-API-Key`; requests from the served dashboard are recognized by the browser-set `Sec-Fetch-Site: same-origin` header and need no key.

**Consequences.** One deployable service and no secret in the browser. Because the dashboard is public by design, the key only stops scripted and cross-site use; rate limiting (300 requests per minute per IP) protects the service. Supersedes ADR-0001.

## ADR-0016: Gradient-boosting classifier for the boundary

**Context.** ADR-0006 chose logistic regression per material. The build trained one scikit-learn gradient-boosting classifier on oxygen, pressure, flow and material over 54 rows with outcomes, reporting stratified 5-fold cross-validation accuracy (0.796).

**Decision.** Keep the gradient-boosting model, with a training-range guard (no prediction outside 16.4 to 22.1% O2, 50.7 to 101.3 kPa, 0.1 to 53 cm/s) and no prediction for materials with fewer than 10 outcome rows.

**Consequences.** Only SIBAL has enough data. The boundary is the P(spread) = 0.5 contour of the model rather than a published-style curve, so it can look irregular. scikit-learn is pinned to 1.9.0 because the saved model is a pickle. Supersedes ADR-0006.

## ADR-0017: Defer Ask FlameAtlas

**Context.** Ask needs a language-model API with credit (ADR-0003, ADR-0004, ADR-0013). The team has no API key for this release, and the deadline is 2026-11-13.

**Decision.** Do not ship Ask. Put the effort into evidence cards and material profiles, which use the same sources without a runtime model.

**Consequences.** FR-ASK requirements are deferred, not withdrawn. Research gaps are communicated by the map, profiles and cards instead of answer-level gap flags.

## ADR-0018: Machine-checked quotes for cards and profiles

**Context.** ADR-0005 requires a person to verify every record. On the deadline day no reviewer was available, and the team asked for the cards to be built without a human in the loop.

**Decision.** Every card, evidence point and profile fact carries the exact source quotes it is based on, with the PDF page or PSI row. `scripts/verify_cards.py` checks every quote word for word against the source and stores the result and the source file hashes. Interpretive takeaways are labeled as such in the app.

**Consequences.** Any reader can confirm the evidence in seconds, and a single changed digit fails the check. The check proves the quotes, not the wording around them: summaries still need expert review (risk R-20). Amends ADR-0005 for cards and profiles; map records from Table 7.1 keep their original status.

## ADR-0019: Dark and light themes

**Context.** ADR-0014 locked a light theme because some marker colors failed contrast on Streamlit's dark background. The as-built dashboard has its own palette.

**Decision.** Default to the viewer's system preference with a manual toggle; outcomes are encoded by marker shape as well as color.

**Consequences.** Contrast must be checked in both themes before release. Supersedes ADR-0014.

## ADR-0020: Render single-service deployment

**Context.** Streamlit Community Cloud fits Streamlit apps, not a FastAPI service.

**Decision.** Deploy to a Render free web service defined in `render.yaml`, auto-deploying from `main`, with `FLAMEATLAS_API_KEY` set in Render and uvicorn run with proxy headers so rate limits see real client IPs.

**Consequences.** One public URL for page and API. The free tier sleeps when idle, so the first request can take about a minute (risk R-23).

## ADR-0021: Evidence-only materials

**Context.** NASA has tested PMMA, Nomex and silicone, but the results cannot support a model: all 20 BASS-II PMMA slabs burned (one class only), the PMMA rod boundary is reported against stretch rate rather than flow, and Nomex and silicone each have about four results from different setups that sometimes disagree.

**Decision.** Mark these materials *evidence only*. The map plots their individual NASA results (oxygen as a range where it drifted during the test) with no boundary and no prediction, and `/predict` returns a research-gap message.

**Consequences.** The app shows real NASA data for four materials without inventing predictions, which supports PRD goal G-4. Adding a material to the model needs at least 10 rows with both burning and non-burning outcomes.

## ADR-0022: U-shaped logistic boundary on measured tests only

**Context.** Re-evaluating ADR-0016 on held-out SIBAL tests only (5-fold, repeated 20 times) showed the gradient-boosting model scored 63%, below the 72% of always guessing "burns". Its reported 79.6% cross-validation accuracy was inflated by 13 rows whose `marginal_spread` label is the parser's default for a missing outcome. It also trained on 6 Table 7.1 rows the table itself flags as unreliable, and its step-shaped boundary did not resemble NASA's published boundaries.

**Decision.** Fit the logistic form of ADR-0006 (O2, log flow, log flow²) to measured SIBAL microgravity outcomes only: 42 usable rows of Table 7.1 plus 5 concurrent-flow Saffire tests (NTRS 20210011521, Table 2, quote-checked), 47 in total. Report held-out accuracy next to the always-burns baseline and a gradient-boosting comparison, in the API and on the dashboard.

**Consequences.** Held-out accuracy is 81.5% against a 78.7% baseline (gradient boosting on the same data: 78.7%); the model rarely predicts extinction correctly (2 of 10 held out), because extinctions are scarce. The fitted peak is near 1,050 cm/s, far above the tested 2 to 53 cm/s, so within the tested range the plot shows only the quenching side of the U, and says so. The boundary is smooth and drawn only inside the tested range. Pressure is not a model input (every SIBAL test ran near 1 atm); predictions are accepted within 15 kPa of the tested pressure. Supersedes ADR-0016.

