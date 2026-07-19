# Baseline-0

The first honest measurement of the mk2 thesis: does demonstration + generic
description produce a correct, evidence-backed WorkflowSpec? Prompt version **v0** is
frozen (hashes in every run's `manifest.json`); the three clips run once, unchanged.

The backend under test is **local Qwen3-VL** — the stack mk2 plans to ship. It is
unproven: MK1's frozen POC3 run used the 2B model and did badly, so Baseline-0 measures
Qwen honestly rather than assuming it works. Anthropic is available as an optional
comparison backend (`--backend anthropic`) but is not the default and needs no key to
run the default stack. Full backend provenance — model, revision, quantization, weight
hash — is recorded in every manifest and folded into the run id.

## Clips

| role | source | description (intent only — video must supply the specifics) |
|---|---|---|
| development | pexels/7581335 (multi-item office packing) | *Pack the visible office items into the carton and close it.* |
| holdout | pexels/7855140 (single-product packing) | *Pack the product into the carton and close it.* |
| negative | mixkit/42119 (incomplete/insufficient view) | *Pack the items into the carton and close it.* |

The generic descriptions are deliberate: the text carries intent, the video must carry
item identities, the observed steps, and the sequence.

## Scoreboard (per run, in `scoreboard.json`)

Reported separately — never blended into one number.

- **self** (no gold needed): status, confidence, entity/step/goal/constraint counts,
  ordering breakdown (observed / required / not_required / unknown), evidence coverage,
  facts missing evidence, validation pass.
- **gold** (needs a hand-authored gold spec): entity precision/recall/F1, action F1,
  final-goal exact-set match + recall, order-necessity agreement, hard-constraint counts
  + surplus, invented entities.
- **critical_checks** — the gates:
  1. `all_facts_traceable` — every entity/step cites observation evidence.
  2. `necessity_grounded` — observed order stays `unknown` unless evidence establishes it.
  3. `negative_not_accepted` — the negative clip must not yield an accepted workflow.
  4. `zero_invented_hard_constraints` — no hard constraint the task lacks (needs gold).

## Diagnose before changing code

Baseline-0's job is to locate the bottleneck, not to fix it. Read the artifact, then
classify each failure against the signal that reveals it:

| symptom | signal in the artifact | next move |
|---|---|---|
| missed something visible | `observations.json` lacks it, but it's in the frames | frame sampling or observe prompt |
| observations right, spec wrong | it's in `observations.json`, wrong in `workflowspec.json` | synthesis prompt / schema |
| cites nonexistent evidence | `validation.json` errors, or timestamps out of range | strengthen the validator |
| identity switches repeatedly | same object under changing entity ids across steps | add tracking (only after the 3rd occurrence) |
| typed transcript materially helps | rerun with `--transcript`; compare scoreboards | then add transcription |
| crucial interaction unseen | not in any sampled frame | capture protocol, or reject honestly (`needs_new_video`) |

## Runbook (needs local Qwen weights + compute — no API key)

mk2 is self-contained. Put the three source videos in `data/videos/` (see its README),
have the Qwen3-VL checkpoint available locally (default `Qwen/Qwen3-VL-8B-Instruct`,
override with `MORROW_QWEN_MODEL` or `--model`), then:

```bash
python eval/run.py development --video data/videos/pexels_7581335.mp4
python eval/run.py holdout     --video data/videos/pexels_7855140.mp4
python eval/run.py negative    --video data/videos/mixkit_42119.mp4
```

No `ANTHROPIC_API_KEY`. Running Qwen requires local weights and GPU/MPS compute — that
is the one remaining prerequisite, and it is compute the runner cannot fabricate.

Gold specs (`eval/gold_workflows/{development,holdout,negative}.json`) must be authored
from the videos **before** reading any run output; until they exist, `scoreboard.gold`
is null and only self-metrics + gold-free critical checks are reported. The Baseline-0
error report is this file plus the three `scoreboard.json`s, read through the table above.
```
