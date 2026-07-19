"""validate() catches the failures MK2 exists to prevent: dangling refs, missing
evidence, and out-of-range timestamps."""

from morrow.ingest import VideoMeta
from morrow.schemas import Entity, Evidence, Step, StateFact, WorkflowSpec
from morrow.validate import validate

META = VideoMeta(path="x.mp4", duration_s=10.0, width=1920, height=1080, fps=30.0)


def _spec(**overrides) -> WorkflowSpec:
    base = dict(
        task_summary="t",
        entities=[Entity(id="e1", name="bag", role="item",
                         evidence=[Evidence(source="video", start_s=1.0)])],
        initial_state=[],
        steps=[Step(id="s1", action="place", description="place bag", entity_ids=["e1"],
                    start_s=1.0, end_s=2.0,
                    evidence=[Evidence(source="video", start_s=1.0, end_s=2.0)], confidence=0.8)],
        final_goals=[],
        ordering=[],
        hard_constraints=[],
        soft_preferences=[],
        unknowns=[],
        confidence=0.7,
        status="accepted",
    )
    base.update(overrides)
    return WorkflowSpec(**base)


def test_clean_spec_has_no_issues():
    assert validate(_spec(), META) == []


def test_dangling_entity_reference_is_an_error():
    spec = _spec(steps=[Step(id="s1", action="place", description="d", entity_ids=["ghost"],
                             evidence=[Evidence(source="video", start_s=1.0)], confidence=0.5)])
    assert any(i.severity == "error" and "ghost" in i.message for i in validate(spec, META))


def test_missing_evidence_is_an_error():
    spec = _spec(final_goals=[StateFact(description="carton is closed", entity_ids=["e1"], evidence=[])])
    assert any(i.severity == "error" and "no evidence" in i.message for i in validate(spec, META))


def test_timestamp_past_duration_is_an_error():
    spec = _spec(steps=[Step(id="s1", action="place", description="d", entity_ids=["e1"],
                             evidence=[Evidence(source="video", start_s=999.0)], confidence=0.5)])
    assert any(i.severity == "error" and "outside" in i.message for i in validate(spec, META))
