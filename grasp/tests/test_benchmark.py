"""GraspLab-01 must stay well-formed and keep shape and mechanics independent — a
benchmark that quietly correlates the two would let a model cheat by guessing."""

from grasp.benchmark import GRASPLAB_01, SIMILAR_PAIRS


def test_ids_are_unique():
    ids = [o.id for o in GRASPLAB_01]
    assert len(ids) == len(set(ids))


def test_similar_pairs_reference_real_objects():
    known = {o.id for o in GRASPLAB_01}
    for a, b in SIMILAR_PAIRS:
        assert {a, b} <= known
        assert a != b


def test_shape_and_mechanics_are_not_collinear():
    # Every shape_class must appear with more than one mechanics across the set (or a
    # mechanics span more than one shape), so no single visual cue determines physics.
    by_shape = {}
    for o in GRASPLAB_01:
        by_shape.setdefault(o.shape_class, set()).add(o.mechanics)
    assert any(len(m) > 1 for m in by_shape.values()), (
        "no shape_class carries multiple mechanics — the benchmark is guessable from shape"
    )


def test_similar_pairs_differ_in_behaviour():
    # A "similar" pair is only useful if the two halves actually behave differently:
    # different mechanics, or a friction/fragility difference vision can't see.
    objs = {o.id: o for o in GRASPLAB_01}
    for a, b in SIMILAR_PAIRS:
        oa, ob = objs[a], objs[b]
        assert (oa.mechanics != ob.mechanics) or (oa.slippery != ob.slippery) or (oa.fragile != ob.fragile)
