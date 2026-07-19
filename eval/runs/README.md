# Runs

One immutable directory per model run, named `<clip>-<run_id>`. The `run_id` is a hash
of the exact inputs (video bytes, model, prompt version, description, transcript, frame
count), so identical inputs produce the same id and a run is never silently redone —
`eval/run.py` refuses to overwrite an existing directory.

Each directory holds the **inference** record only — no scoreboard:

| file | contents |
|---|---|
| `manifest.json` | inputs, video sha256, frame timestamps, backend provenance, prompt fingerprint, latency, token usage |
| `observation_raw.txt` | raw model response, pass 1 |
| `observations.json` | parsed observations |
| `synthesis_raw.txt` | raw model response, pass 2 |
| `workflowspec.json` | the inferred WorkflowSpec |
| `validation.json` | deterministic validation issues |

Scores are **not** stored here. Scoring is a separate, re-computable step written under
`eval/scores/`, keyed by `run_id + gold_sha256 + metrics_version` — so a run stays
immutable while a changed gold produces a fresh score instead of a stale one.

Runs and scores are committed — they are the evidence behind each baseline. The videos
themselves are not (see `.gitignore`).
