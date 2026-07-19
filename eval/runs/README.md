# Runs

One immutable directory per model run, named `<clip>-<run_id>`. The `run_id` is a hash
of the exact inputs (video bytes, model, prompt version, description, transcript, frame
count), so identical inputs produce the same id and a run is never silently redone —
`eval/run.py` refuses to overwrite an existing directory.

Each directory holds the complete record:

| file | contents |
|---|---|
| `manifest.json` | inputs, video sha256, frame timestamps, model + prompt fingerprint, latency, token usage |
| `observation_raw.txt` | raw model response, pass 1 |
| `observations.json` | parsed observations |
| `synthesis_raw.txt` | raw model response, pass 2 |
| `workflowspec.json` | the inferred WorkflowSpec |
| `validation.json` | deterministic validation issues |
| `scoreboard.json` | self metrics, gold metrics (if a gold spec exists), critical checks |

Runs are committed — they are the evidence behind each baseline. The videos themselves
are not (see `.gitignore`).
