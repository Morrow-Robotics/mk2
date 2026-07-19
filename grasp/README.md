# grasp — cheap general grasping

A research track, separate from the `morrow` WorkflowSpec pipeline. The question: grasp
and manipulate **any** object without its behaviour being hardcoded — figure out how an
unfamiliar object responds to contact and adapt the grasp online.

Two ideas, combined: take geometrically-valid grasp poses from an existing general model
(GraspGenX), and build Morrow's intelligence around *predicting how the object responds
to force* — a small, action-conditioned world model with an honest sense of its own
uncertainty. The proposer is commodity; the predict-and-adapt loop is the product.

Read [`DESIGN.md`](DESIGN.md) for the full plan: what we reuse vs. build (with licensing),
the grasping loop, cheap-first sensing, the small first model, and the GraspLab-01
experiment.

## What's here

| File | What |
|---|---|
| `schemas.py` | The contracts — gripper, candidate, observation, `PhysicalBelief`, prediction, episode. No material labels, by design. |
| `benchmark.py` | GraspLab-01 objects + visually-similar / mechanically-different pairs. |
| `episode.py` | Immutable per-attempt JSON recorder — the experience log we learn from. |

Deliberately not here yet: proposer adapters, the outcome model, the probe policy, the
controller. Written on contact with real hardware, per `../STYLE_GUIDE.md`.

```bash
python -m pytest grasp    # from repo root, dev venv
```
