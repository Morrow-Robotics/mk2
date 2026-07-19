"""Contracts for the cheap general-grasping track: how Morrow describes an object it
has never seen, the gripper holding it, what it senses during contact, and what it
predicts will happen.

The bet mirrors the WorkflowSpec bet in `morrow`: keep *what we observed*, *what we
believe about the physics*, and *what we don't know* strictly apart. A grasp fails
when code collapses "this looks like rubber" into "grasp it like rubber". So there is
deliberately **no material label** here. An object is described only by a continuous,
uncertain `PhysicalBelief` — how it deforms, how much tangential load it holds, how
heavy it might be, how likely it is to break — each with a confidence.

These types carry no behaviour. IO lives in `episode.py`; the benchmark object set in
`benchmark.py`. Units are SI and named in the field: metres, newtons, kilograms,
amps, seconds.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Vec3 = tuple[float, float, float]
Quat = tuple[float, float, float, float]  # (x, y, z, w)


class Estimate(BaseModel):
    """A scalar we are unsure about: a mean and a standard deviation in the same unit.

    `std` is the model's own uncertainty, not sensor noise. A wide `std` is the signal
    that tells the controller to probe before it commits force. `std=0` means certain.
    """

    mean: float
    std: float = Field(ge=0.0)


class GripperDescriptor(BaseModel):
    """The embodiment. The point of naming it explicitly is that the cheap LeRobot
    gripper, a later industrial parallel jaw, and eventually a humanoid hand all share
    this one interface — a grasp proposer and the world model take a `GripperDescriptor`,
    never an `if gripper == ...`.

    `urdf_path` and the swept-volume mesh (referenced from the URDF) are what a
    geometry-based proposer like GraspGenX consumes. `has_tactile` gates whether
    `InteractionObservation.pressure` is meaningful for this body.
    """

    id: str
    name: str
    kind: Literal["parallel_jaw", "multi_finger"]
    urdf_path: str | None
    num_fingers: int = Field(ge=1)
    max_opening_m: float = Field(gt=0.0)
    max_force_n: float = Field(gt=0.0)
    has_tactile: bool
    notes: str | None = None


class GraspCandidate(BaseModel):
    """A 6-DoF pose to try, from a geometry proposer (GraspGenX / VGN / analytic
    baseline). This is *geometry only* — it says where the gripper goes and how wide it
    opens, not how hard to squeeze. Force is chosen later, by the controller, from the
    `PhysicalBelief`. `score` is the proposer's own confidence and is not comparable
    across proposers.
    """

    id: str
    gripper_id: str  # -> GripperDescriptor.id
    position_m: Vec3
    orientation_quat: Quat
    width_m: float = Field(ge=0.0)  # target jaw opening at the pose
    source: str  # "graspgenx" | "vgn" | "analytic"
    score: float


class InteractionObservation(BaseModel):
    """One timestamped snapshot of everything the arm senses mid-interaction.

    Deliberately cheap-first: on the starter arm the only reliable signals are servo
    load and the gap between commanded and actual jaw width — everything else is
    `None`. The world model must degrade gracefully as fields go missing, because the
    first real build has no fingertip sensors. `frame_ref` points into the episode's
    video (e.g. a frame index or timestamp), not pixels inline.
    """

    t_s: float
    gripper_width_m: float  # measured
    gripper_width_commanded_m: float
    servo_current_a: float | None = None
    joint_currents_a: list[float] | None = None
    pressure: list[float] | None = None  # per-pad, only if the gripper has_tactile
    slip_estimate: float | None = None  # tangential-motion signal, unitless 0..1
    frame_ref: str | None = None


class PhysicalBelief(BaseModel):
    """Morrow's continuous, uncertain physical model of one object — the thing that
    replaces a material lookup table. Every field is an `Estimate`, so the belief always
    carries its own confidence. It starts wide (vision only) and narrows as probes and
    the grasp itself return evidence.

    Ranges are conventions, not hard clamps:
      effective_compliance  metres of deformation per newton at the contact patch
      slip_margin           newtons of tangential load the contact tolerates before slip
      mass_kg               object mass
      com_offset_m          distance of centre-of-mass from the grasp point
      damage_risk           probability of permanent deformation/breakage at planned force (0..1)
      contents_shift        probability the interior moves independently of the shell (0..1)
    """

    effective_compliance: Estimate
    slip_margin: Estimate
    mass_kg: Estimate
    com_offset_m: Estimate
    damage_risk: Estimate
    contents_shift: Estimate


class OutcomePrediction(BaseModel):
    """What the world model expects for one `GraspCandidate` under one force schedule.
    This is the quantity the controller optimises over (see DESIGN.md for the objective).
    Each probability carries its own uncertainty so the controller can prefer a safe
    probe over a confident-but-blind commit.
    """

    candidate_id: str
    peak_force_n: float  # the force schedule this prediction is conditioned on
    success: Estimate  # P(lift holds), as an Estimate over [0,1]
    slip: Estimate
    deformation_m: Estimate
    damage_risk: Estimate


class Probe(BaseModel):
    """A cheap, safe information-gathering action taken before committing — gentle
    touch, low-force squeeze, small tangential nudge, or a few-millimetre test lift.
    Recorded with the belief before and after, so we can measure how much a probe
    actually bought us (a headline GraspLab metric).
    """

    kind: Literal["touch", "squeeze", "shear", "test_lift"]
    belief_before: PhysicalBelief
    belief_after: PhysicalBelief
    observations: list[InteractionObservation]
    duration_s: float = Field(ge=0.0)


class GraspAttempt(BaseModel):
    """The committed grasp: which candidate, the force schedule actually applied, the
    sensor timeline, and how it ended. `outcome` is measured ground truth (did it lift,
    did it slip, was it damaged) — the label the world model is trained against.
    """

    candidate: GraspCandidate
    peak_force_n: float
    observations: list[InteractionObservation]
    lifted: bool
    slipped: bool
    damaged: bool
    notes: str | None = None


class GraspEpisode(BaseModel):
    """One immutable attempt on one object — the unit of experience Morrow learns from.

    Every deployment writes exactly one of these per grasp: the object it faced (by
    benchmark id when known, else a free description), the gripper, the candidates it
    considered, any probes, the prediction it made for the chosen grasp, and what
    actually happened. `predicted` vs `attempt.outcome` is the calibration signal;
    `probes` vs the belief delta is the value-of-probing signal. `episode_id` and
    `recorded_at` are supplied by the caller — nothing here reads the wall clock, so
    episodes reproduce exactly.
    """

    episode_id: str
    recorded_at: str  # ISO-8601, caller-supplied
    object_id: str | None  # -> benchmark object, or None for an unlisted object
    object_description: str
    gripper: GripperDescriptor
    candidates: list[GraspCandidate]
    initial_belief: PhysicalBelief
    probes: list[Probe]
    predicted: OutcomePrediction
    attempt: GraspAttempt
