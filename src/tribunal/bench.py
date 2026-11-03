"""Speed measurements for docs/SCORECARD.md: how fast search is, and whole verdicts.

`tribunal bench` times every query in the retrieval eval set, so the speed numbers describe
the same searches as the quality numbers. With --verdicts N it also times N real verdicts,
which uses LLM quota.
"""

import statistics
import time
from collections.abc import Callable, Sequence


def percentiles(samples: Sequence[float]) -> dict[str, float]:
    """The median, p95 and p99 of `samples`: the slow tail matters more than the average."""
    if len(samples) < 2:
        only = samples[0] if samples else 0.0
        return {"p50": only, "p95": only, "p99": only}
    cuts = statistics.quantiles(samples, n=100, method="inclusive")
    return {"p50": cuts[49], "p95": cuts[94], "p99": cuts[98]}


def timed[T](call: Callable[[T], object], inputs: Sequence[T], repeat: int = 1) -> list[float]:
    """Milliseconds taken by `call` on each input, `repeat` times over."""
    samples = []
    for _ in range(repeat):
        for item in inputs:
            start = time.perf_counter()
            call(item)
            samples.append((time.perf_counter() - start) * 1000)
    return samples


def summary(name: str, samples: Sequence[float]) -> str:
    p = percentiles(samples)
    rate = 1000 / statistics.fmean(samples) if samples else 0.0
    return (
        f"{name}: {len(samples)} runs, p50 {p['p50']:.0f} ms, p95 {p['p95']:.0f} ms, "
        f"p99 {p['p99']:.0f} ms, {rate:.1f} a second one at a time"
    )
