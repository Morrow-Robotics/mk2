"""Cheap general grasping: grasp any object without hardcoding it, by predicting how it
will respond to contact and adapting online. See DESIGN.md for the plan.

Public surface is the contracts plus episode IO. Everything else (proposer adapters,
the world model, the controller) gets written on contact with real hardware, not before.
"""

from .episode import load_episode, load_episodes, save_episode
from .schemas import (
    Estimate,
    GraspAttempt,
    GraspCandidate,
    GraspEpisode,
    GripperDescriptor,
    InteractionObservation,
    OutcomePrediction,
    PhysicalBelief,
    Probe,
)

__all__ = [
    "Estimate",
    "GraspAttempt",
    "GraspCandidate",
    "GraspEpisode",
    "GripperDescriptor",
    "InteractionObservation",
    "OutcomePrediction",
    "PhysicalBelief",
    "Probe",
    "load_episode",
    "load_episodes",
    "save_episode",
]
