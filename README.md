# morrow (mk2)

Film a task demo, describe what you want, and get back an **evidence-backed
WorkflowSpec** — an abstract, checkable description of the task. No robot execution.
This repo exists to get the *beginning* right: demonstration + description → task
understanding. Execution stays in [mk1](https://github.com/Morrow-Robotics/mk1).

## Why this is a separate repo

mk1's core path never actually learned the task — it parsed the description with regex,
threw away the inferred belief, and rebuilt the steps from a known simulator scene. mk2
is not a refactor of that; it's the first real build of the one capability mk1 skipped.
So nothing is ported. See `STYLE_GUIDE.md` for how the code is meant to read.

## The one idea

A WorkflowSpec keeps three things most demonstration-learning code collapses into one:

- **what the worker did** — `OrderRelation.observed`
- **what the task requires** — `OrderRelation.necessity` (`required` / `not_required` / `unknown`)
- **what we don't know** — `unknowns`, and `necessity="unknown"` by default

Order is soft unless narration or physics makes it mandatory. Every inferred fact cites
`Evidence` (a video timespan or a quote). `validate.py` enforces that; the model can't be
trusted to.

## Usage

Needs `ffmpeg`/`ffprobe` on PATH and `ANTHROPIC_API_KEY` set.

```bash
pip install -e '.[dev]'
morrow analyze demo.mp4 --description "Pack the completed bags into the carton"
```

Writes the WorkflowSpec JSON to stdout (or `--out`) and prints an evidence timeline,
open questions, and any validation issues to stderr. Exit code is non-zero if the spec
fails a hard invariant.

## Layout

```
src/morrow/
  schemas.py    WorkflowSpec + friends — the public contract (the real IP)
  ingest.py     probe + sample_frames over ffmpeg
  model.py      two passes: observe (frames+words -> observations), synthesize (-> spec)
  validate.py   deterministic checks: references, evidence present, timestamps in range
  analyze.py    ingest -> observe -> synthesize -> validate
  cli.py        `morrow analyze`
eval/
  gold_workflows/  hand-authored specs; never fed to inference
  metrics.py       scores a prediction against gold
tests/
```

## Deliberately not here yet

- **Transcription** — pass `--transcript file.txt`; no STT vendor is baked in yet.
- **Entity grounding (SAM/TAPIR)** — added when we observe the model inventing entities,
  not before.
- **Any execution** — task graph, planning, simulator, deployment. That is mk1's job, and
  it should not reconnect until mk2 hits strong goal/step accuracy with zero invented
  hard constraints.
```
