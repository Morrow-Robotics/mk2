# Scores

One file per (run, gold, metrics version): `<run_id>__<gold_sha256[:12]|nogold>__<metrics_version>.json`.

Scoring is decoupled from inference. A run directory under `eval/runs/` is immutable and
holds only the model's output; scoring reads that output plus the current gold spec and
writes the result here. The filename key means:

- **re-scoring the same run against a changed gold** produces a *new* file — you never
  read back a scoreboard computed against a gold that has since changed;
- **bumping `metrics.METRICS_VERSION`** (when a metric's definition changes) produces a
  new file — old and new metric definitions never blur together.

Each file records `run_id`, `clip`, `gold_sha256`, `metrics_version`, and the `scoreboard`
(self / gold / critical_checks). Regenerate any score with
`run.score_run(run_dir, gold_path=...)`.
