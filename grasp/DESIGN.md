# Cheap general grasping — design

**Goal.** Grasp and manipulate any object without its behaviour being hardcoded — no
`if object == pouch`, no per-material force table, no lookup keyed on a label. The
machine should figure out how an *unfamiliar* object responds to contact and adapt the
grasp online.

**The two ideas, combined.** Use an existing general grasp model for geometrically
valid pose candidates; build Morrow's intelligence around *predicting how an unknown
object responds to contact* and adapting force from that. The SOTA proposer is the
starting point and is commodity. The action-conditioned world model — LeCun-style — is
the product and the moat.

"No hardcoding" means no object lookup and no per-material routine. It does **not** mean
no rules: joint limits, collision avoidance, a maximum permitted force, and emergency
stop stay hardcoded as universal safety constraints.

## What we take vs. what we build

| Project | Useful for | Commercial position | Decision |
|---|---|---|---|
| GraspGenX | 6-DoF grasps for novel objects *and* novel grippers from a point cloud + gripper URDF/swept-volume | Apache-2.0 code; NVIDIA Open Model License weights | **Primary proposal backend** |
| VGN | Lightweight TSDF→grasp baseline | BSD-3-Clause | Commercial fallback / benchmark |
| DINO-WM | Small action-conditioned predictor over frozen visual features; plans through latent futures | MIT | **Best starting architecture** for our world model |
| V-JEPA 2 / 2.1 | Strong pretrained video features; action-conditioned prediction | Mostly MIT/Apache; action model is 1B | Pretrained features / distillation ideas, not the full model initially |
| Dream-Tac | Joint visual+tactile+action future prediction | Apache code; 2B model, 8-GPU recipe | Copy the contact-gating idea, not the stack |
| FTP-1 | Cross-sensor tactile representation + policy | Apache code; 4B checkpoint card unclear | Research reference only |

**Avoid depending on commercially:** AnyGrasp (machine-licensed SDK), GraspVLA & Sparsh
(non-commercial), original GraspGen (research/eval only). RoboPack has the latent-physics
idea we want but its repo ships no explicit licence.

GraspGenX also solves the embodiment problem: cheap LeRobot gripper, later industrial
jaw, eventual humanoid hand all share one proposal interface — this is why
`GripperDescriptor` is a first-class contract. It does **not** solve force, material,
slip, or fragility. That is what we build.

## What the world model learns

Not a material class. "Rubber" doesn't determine a grasp — a rubber coating over steel,
a hollow rubber ball, and a soft silicone pouch behave completely differently. Instead a
continuous, uncertain object belief (`PhysicalBelief` in `schemas.py`): effective
compliance, slip margin, mass and centre-of-mass uncertainty, permanent-deformation
risk, whether contents move independently, each with a confidence.

The model's real question is action-conditioned, not classificatory:

> Given this object history `h`, this gripper, this grasp pose, and this force
> trajectory — what happens next?

## The grasping loop

1. Segment the target, build its partial point cloud.
2. GraspGenX proposes diverse `GraspCandidate` poses.
3. Collision / reachability / task constraints drop impossible candidates.
4. The model predicts success, slip, deformation, damage per candidate + force schedule.
5. If uncertainty is high, run a safe `Probe`: gentle touch → low-force squeeze → small
   tangential nudge → ~5 mm test lift. Update the belief.
6. Select the grasp; close only until sufficient force; lift slowly; monitor slip.
7. Add force / reposition / regrasp if the observed future diverges from the predicted.

Selection objective (`h` = full visual + tactile + proprioceptive history):

```
g* = argmax_g  P(success | h, g) − λ_d·P(damage) − λ_s·P(slip) − λ_u·U(g)
```

## Cheap-first sensing

No £1,000 fingertips at the start. Derive rough contact / compression / slip / mass from:
gripper servo current/load, commanded-vs-actual jaw width, joint current during a test
lift, a fixed RGB(-D) camera, an optional wrist cam, and soft replaceable finger pads.
Noisy but enough to build the pipeline — which is why `InteractionObservation` treats
every signal past servo load and jaw width as optional.

Touch is not optional long-term. FORTE reports 91.9% success across 31 fragile/slippery/
everyday objects with force/slip feedback vs 60% for a naive fully-closing grasp. Vision
alone can't reveal friction, hidden mass, or breaking force. Add two cheap pressure
sensors or a simple array next (FlexiTac: ~100 Hz, ~$2.50/pad, but CC BY-NC — don't copy
into a product). Off-the-shelf GelSight/DIGIT ($355–$560) is not for the first build.

## First model — small on purpose

Frozen DINOv2 or V-JEPA 2.1 ViT-B object features + point-cloud features from the
candidate + gripper geometry embedding from GraspGenX + a small temporal encoder over
position/current/pressure → a ~5–20M-param action-conditioned transformer or GRU, with
separate heads for contact, slip, deformation, lift success, damage, and an
ensemble/evidential head for uncertainty. Train to predict the next latent observation
and the automatically-observable outcomes — the JEPA objective without internet-scale
pretraining.

## First convincing experiment — GraspLab-01

See `benchmark.py`. Objects vary **shape and mechanics independently** so the model can't
pass by guessing "round → rubber". Compare three systems:

1. Analytic box/cylinder/pouch proposer, fixed force.
2. GraspGenX, fixed force.
3. GraspGenX + Morrow probing, belief, adaptive force.

Measure: first-attempt success on unseen objects; drop/slip rate; permanent-damage rate;
improvement after one probe; number/duration of probes; **calibration** (when it says
80%, does it succeed ~80%?); transfer to a second gripper with no full retrain.

**Headline demo:** two near-identical objects (a `SIMILAR_PAIRS` entry) where the same
fixed-force grasp fails *differently* on each, while Morrow probes each once and handles
both.

## Status

Built so far — the contracts and the experience log, nothing speculative:

- `schemas.py` — `GripperDescriptor`, `GraspCandidate`, `InteractionObservation`,
  `PhysicalBelief`, `OutcomePrediction`, `Probe`, `GraspAttempt`, `GraspEpisode`.
- `benchmark.py` — the GraspLab-01 object set + `SIMILAR_PAIRS` + integrity checks.
- `episode.py` — immutable per-attempt JSON recorder.

Not built yet (write on contact with hardware/GraspGenX, not before): proposer adapters
(GraspGenX / VGN), the `OutcomePrediction` model, the probe policy, the adaptive
controller. The defensible part is not "we have a grasp network" — GraspGenX gives that
to everyone. It's a cross-object, cross-material, cross-gripper interaction model that
knows when it's uncertain, probes safely, and improves from every deployment without an
engineer writing another object-specific routine.

## Run

```bash
python -m pytest grasp        # from repo root, in the dev venv
```
