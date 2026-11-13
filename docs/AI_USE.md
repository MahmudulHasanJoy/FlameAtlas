# Use of AI in this project

## Summary

FlameAtlas runs **no AI model at runtime**. Predictions come from a deterministic
gradient-boosting classifier trained on published NASA data. An AI coding
assistant was used during development, as described below.

## Science layer (team)

- `src/compute/model.py` and `cache/experiments.parquet` were built by the team.
  The classifier, its features, the cross-validation splits, the prediction
  object contract and the out-of-range guard were not chosen by an AI.
- The NASA datasets come from the PSI and NTRS source lists in `data/sources/`.

## Development assistant: Claude Code (Anthropic), 2026-11-13

Used by the team, with the team directing each step, to:

- Make the app deployable: serve the dashboard from the FastAPI service, remove
  the API key from the browser, add the Render configuration, pinned
  requirements and API tests.
- Add a research-gap response for materials without enough outcome data.
- Draft the evidence cards (`data/processed/cards.json`), evidence points
  (`evidence_points.json`) and material profiles (`materials.json`) from the
  downloaded NASA PDFs and PSI tables.
- Write `scripts/verify_cards.py` and update the documentation to the as-built app.

## Safeguards on AI-drafted content

- Every card, evidence point and profile fact lists the exact quotes it is based
  on, with the PDF page or table row. `scripts/verify_cards.py` checks every quote
  word for word against the source (164 of 164 pass); the result is stored in
  `data/processed/cards_verification.json` with SHA-256 hashes of the sources.
- Card takeaways that are interpretation rather than quotation are labeled
  "FlameAtlas interpretation" in the app.
- Card summaries and takeaways have not yet been reviewed by a combustion expert.

## Prompts

No language-model prompts are used by the app. If Ask FlameAtlas is built later,
its prompts will be recorded in `docs/prompts_used.md`.
