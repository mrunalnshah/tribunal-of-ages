from tribunal.evals import hit_at_k, reciprocal_rank


def test_hit_at_k():
    assert hit_at_k(["a", "b", "c"], {"c"}, k=3) == 1.0
    assert hit_at_k(["a", "b", "c"], {"c"}, k=2) == 0.0


def test_reciprocal_rank():
    assert reciprocal_rank(["x", "y", "z"], {"y"}) == 0.5
    assert reciprocal_rank(["x"], {"missing"}) == 0.0
