# Use of AI in this project

## Tools
- None at build time for the science layer. All statistics and the gradient-boosting
  classifier in `src/compute/` are written and unit-tested by the team.
- The explanation layer (planned) will use an LLM to write plain-language captions
  from the prediction object only; it will never predict or state a number absent
  from the object.

## What the AI did
- Nothing in `src/compute/model.py` or `cache/experiments.parquet`. These are
  deterministic, trained on published NASA data, and cross-validated honestly.

## What the AI did not do
- Did not train the model, choose features, or set the cross-validation splits.
- Did not select the NASA datasets; those come from the PSI / NTRS source lists.
- Did not write the prediction object contract or the out-of-range guard.

## Prompts
None yet. If an LLM is added for the explanation layer, full prompt texts will be
recorded in `docs/prompts_used.md`.
