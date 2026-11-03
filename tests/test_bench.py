from tribunal.bench import percentiles, summary, timed


def test_percentiles_describe_the_slow_tail():
    samples = [float(n) for n in range(1, 101)]  # 1 ms to 100 ms
    p = percentiles(samples)
    assert p["p50"] == 50.5
    assert 95 <= p["p95"] <= 96
    assert 99 <= p["p99"] <= 100


def test_one_sample_is_its_own_percentiles():
    assert percentiles([7.0]) == {"p50": 7.0, "p95": 7.0, "p99": 7.0}


def test_timed_measures_every_input_each_round():
    seen = []
    samples = timed(seen.append, ["a", "b"], repeat=3)
    assert seen == ["a", "b"] * 3
    assert len(samples) == 6 and all(ms >= 0 for ms in samples)
    assert summary("search", samples).startswith("search: 6 runs, p50")
