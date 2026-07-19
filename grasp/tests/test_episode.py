"""Episode IO must round-trip losslessly and refuse to rewrite history."""

import pytest

from grasp import (
    Estimate,
    GraspAttempt,
    GraspCandidate,
    GraspEpisode,
    GripperDescriptor,
    InteractionObservation,
    OutcomePrediction,
    PhysicalBelief,
    load_episode,
    save_episode,
)


def _belief(scale: float = 1.0) -> PhysicalBelief:
    return PhysicalBelief(
        effective_compliance=Estimate(mean=1e-4 * scale, std=5e-5),
        slip_margin=Estimate(mean=2.0, std=1.0),
        mass_kg=Estimate(mean=0.2, std=0.15),
        com_offset_m=Estimate(mean=0.01, std=0.02),
        damage_risk=Estimate(mean=0.1, std=0.1),
        contents_shift=Estimate(mean=0.0, std=0.05),
    )


def _episode(episode_id: str = "ep-0001") -> GraspEpisode:
    gripper = GripperDescriptor(
        id="lerobot_jaw", name="LeRobot parallel jaw", kind="parallel_jaw",
        urdf_path=None, num_fingers=2, max_opening_m=0.08, max_force_n=15.0,
        has_tactile=False,
    )
    candidate = GraspCandidate(
        id="c0", gripper_id=gripper.id, position_m=(0.3, 0.0, 0.1),
        orientation_quat=(0.0, 0.0, 0.0, 1.0), width_m=0.04, source="graspgenx", score=0.82,
    )
    obs = InteractionObservation(
        t_s=0.0, gripper_width_m=0.04, gripper_width_commanded_m=0.035, servo_current_a=0.3,
    )
    return GraspEpisode(
        episode_id=episode_id, recorded_at="2026-07-19T18:00:00Z",
        object_id="rubber_block", object_description="Rubber-coated block",
        gripper=gripper, candidates=[candidate], initial_belief=_belief(),
        probes=[],
        predicted=OutcomePrediction(
            candidate_id="c0", peak_force_n=4.0,
            success=Estimate(mean=0.9, std=0.05), slip=Estimate(mean=0.1, std=0.05),
            deformation_m=Estimate(mean=0.002, std=0.001), damage_risk=Estimate(mean=0.02, std=0.02),
        ),
        attempt=GraspAttempt(
            candidate=candidate, peak_force_n=4.0, observations=[obs],
            lifted=True, slipped=False, damaged=False,
        ),
    )


def test_episode_round_trips(tmp_path):
    original = _episode()
    path = save_episode(original, tmp_path)
    assert load_episode(path) == original


def test_save_refuses_to_overwrite(tmp_path):
    save_episode(_episode(), tmp_path)
    with pytest.raises(FileExistsError):
        save_episode(_episode(), tmp_path)


def test_estimate_rejects_negative_std():
    with pytest.raises(ValueError):
        Estimate(mean=1.0, std=-0.1)
