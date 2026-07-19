"""The WorkflowSpec contract: it round-trips through JSON and defaults order to unknown."""

from morrow.schemas import Evidence, OrderRelation, Step, WorkflowSpec


def _minimal_spec() -> WorkflowSpec:
    ev = [Evidence(source="video", start_s=1.0, end_s=2.0, note="bag enters carton")]
    return WorkflowSpec(
        task_summary="pack a bag into a carton",
        entities=[],
        initial_state=[],
        steps=[Step(id="s1", action="place", description="place bag in carton",
                    entity_ids=[], start_s=1.0, end_s=2.0, evidence=ev, confidence=0.8)],
        final_goals=[],
        ordering=[],
        hard_constraints=[],
        soft_preferences=[],
        unknowns=[],
        confidence=0.7,
        status="needs_confirmation",
    )


def test_round_trips_through_json():
    spec = _minimal_spec()
    restored = WorkflowSpec.model_validate_json(spec.model_dump_json())
    assert restored == spec


def test_order_necessity_defaults_to_unknown():
    # The core distinction: observing an order must not imply requiring it.
    rel = OrderRelation(before="s1", after="s2", observed=True, rationale="seen in demo", evidence=[])
    assert rel.necessity == "unknown"
