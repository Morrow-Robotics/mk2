"""GraspLab-01: the first benchmark object set.

The whole design turns on one rule: **shape and mechanics vary independently**. If
every round object were rubber and every block were rigid, a model would pass by
learning "round -> squeeze gently" and learn nothing about physics. So the set pairs
objects that look and measure nearly the same to a camera but behave completely
differently under force — that is exactly where a fixed-force grasp fails and where a
probing, belief-updating grasp should win.

This module is pure data plus integrity checks. `SIMILAR_PAIRS` names the visually-
similar / mechanically-different pairs that make the headline demo: same proposer,
same fixed force, two different failures — and Morrow probes each once and handles both.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

ShapeClass = Literal["block", "cylinder", "sphere", "shell", "pouch", "bottle", "cup"]
Mechanics = Literal[
    "rigid",  # PLA, hard plastic — negligible deformation
    "elastic",  # rubber/silicone — deforms and springs back
    "foam",  # crushes, high compliance, low damage risk
    "hollow_thin",  # thin shell — buckles/crushes permanently under modest force
    "filled_shift",  # contents move independently of the exterior
    "granular",  # partially filled, mass redistributes
]


class BenchObject(BaseModel):
    """One physical test object. `shape_class` is what a camera sees; `mechanics` is how
    it responds to contact. The two are chosen independently on purpose."""

    id: str
    name: str
    shape_class: ShapeClass
    mechanics: Mechanics
    fragile: bool  # a wrong force permanently damages it
    slippery: bool  # low friction — vision cannot reveal the slip margin
    notes: str


GRASPLAB_01: list[BenchObject] = [
    BenchObject(id="pla_block", name="Rigid PLA block", shape_class="block",
                mechanics="rigid", fragile=False, slippery=False,
                notes="Reference rigid object. Any reasonable force works."),
    BenchObject(id="smooth_block", name="Smooth plastic block", shape_class="block",
                mechanics="rigid", fragile=False, slippery=True,
                notes="Same shape as pla_block, but low friction — needs more force or it slips."),
    BenchObject(id="rubber_block", name="Rubber-coated block", shape_class="block",
                mechanics="elastic", fragile=False, slippery=False,
                notes="Looks like pla_block; deforms under the same force. High friction."),
    BenchObject(id="foam_block", name="Foam block", shape_class="block",
                mechanics="foam", fragile=False, slippery=False,
                notes="Crushes at pla_block's force but recovers; low damage risk."),
    BenchObject(id="cardboard_shell", name="Thin hollow cardboard shell", shape_class="shell",
                mechanics="hollow_thin", fragile=True, slippery=False,
                notes="Block-shaped but crushes permanently — the fragility trap."),
    BenchObject(id="sponge_cylinder", name="Sponge cylinder", shape_class="cylinder",
                mechanics="foam", fragile=False, slippery=False,
                notes="High compliance; grip closes far past first contact before it holds."),
    BenchObject(id="pla_cylinder", name="Rigid PLA cylinder", shape_class="cylinder",
                mechanics="rigid", fragile=False, slippery=False,
                notes="Rigid counterpart to sponge_cylinder — same silhouette."),
    BenchObject(id="rubber_ball", name="Hollow rubber ball", shape_class="sphere",
                mechanics="elastic", fragile=False, slippery=False,
                notes="Deforms and rolls; contact patch moves as it squashes."),
    BenchObject(id="full_pouch", name="Filled pouch", shape_class="pouch",
                mechanics="filled_shift", fragile=False, slippery=False,
                notes="Contents shift; centre-of-mass moves during the lift."),
    BenchObject(id="half_pouch", name="Partially filled pouch", shape_class="pouch",
                mechanics="granular", fragile=False, slippery=False,
                notes="Same exterior as full_pouch; mass redistributes, lighter and less stable."),
    BenchObject(id="water_bottle", name="Slippery bottle", shape_class="bottle",
                mechanics="filled_shift", fragile=False, slippery=True,
                notes="Low friction + sloshing contents — needs force and slip monitoring."),
    BenchObject(id="paper_cup", name="Delicate cup", shape_class="cup",
                mechanics="hollow_thin", fragile=True, slippery=False,
                notes="Food-like proxy; buckles under modest force — damage risk is the whole point."),
]

# Visually similar, mechanically different. Same fixed-force grasp fails differently on
# each half; Morrow should probe once and handle both. These drive the headline demo.
SIMILAR_PAIRS: list[tuple[str, str]] = [
    ("pla_block", "rubber_block"),  # rigid vs elastic, identical silhouette
    ("pla_block", "cardboard_shell"),  # solid vs crush-fragile shell
    ("pla_cylinder", "sponge_cylinder"),  # rigid vs high-compliance
    ("full_pouch", "half_pouch"),  # full vs partial fill — mass and stability differ
    ("pla_block", "smooth_block"),  # same mechanics, friction differs — slip trap
]


def _check_integrity() -> None:
    """Fail loud at import if the set is malformed — a bad benchmark silently corrupts
    every number computed against it."""
    ids = [o.id for o in GRASPLAB_01]
    dupes = {i for i in ids if ids.count(i) > 1}
    if dupes:
        raise ValueError(f"GraspLab-01 has duplicate object ids: {sorted(dupes)}")
    known = set(ids)
    for a, b in SIMILAR_PAIRS:
        missing = {a, b} - known
        if missing:
            raise ValueError(f"SIMILAR_PAIRS references unknown object(s): {sorted(missing)}")
        if a == b:
            raise ValueError(f"SIMILAR_PAIRS contains a self-pair: {a}")


_check_integrity()
