# Scorecard

Every number about this project, with how it was measured and when. The tutorial says when
to measure each one: look for the Measure it box at the end of a step. Fill a row only with
a number you measured yourself, keep the method beside it, and leave a row empty rather than
guess. An interviewer will ask how you got it.

## Data

| Metric | Value | How it's measured | Step | Date |
|---|---|---|---|---|
| Laws in the corpus | 552: 247 from Hammurabi, 91 from the Salic Law, 214 from law files | the report `tribunal curate` prints | 7 | 2026-11-02 |
| Sources | 72 books with laws (78 in data/laws/; 6 await their texts in Step 7) | the books in data/laws/, also in the curate report | 7 | 2026-11-02 |
| Themes and jurisdictions | 4 themes, 72 jurisdictions (ancient 5, history 11, mythology 7, fiction 49) | the curate report, or data/processed/catalog.json | 7 | 2026-11-02 |
| Laws reviewed by hand | [fill: rows you checked in data/review.csv] + 1 entry in overrides.json | rows you checked in data/review.csv, plus entries in data/overrides.json | 7 | 2026-11-02 |

## Retrieval quality

| Metric | Value | How it's measured | Step | Date |
|---|---|---|---|---|
| Eval queries | 46 (41 scored; 5 wait for Step 7's placeholders) | lines in data/eval/retrieval.jsonl | 9 | 2026-11-02 |
| Hit@5, dense only | 0.756 (31 of 41) | `tribunal eval`, before adding BM25; copy it from EXPERIMENTS.md | 9 | 2026-11-02 |
| Hit@5, hybrid | 0.805 (33 of 41) | `tribunal eval`, with dense and BM25 fused | 9 | 2026-11-02 |
| Hit@5, hybrid + rerank | 0.805 (33 of 41) | `tribunal eval`, with the cross-encoder | 9 | 2026-11-02 |
| MRR, dense only | 0.664 | the same runs as Hit@5 | 9 | 2026-11-02 |
| MRR, hybrid | 0.715 | the same runs as Hit@5 | 9 | 2026-11-02 |
| MRR, hybrid + rerank | 0.755 | the same runs as Hit@5 | 9 | 2026-11-02 |

## Speed

| Metric | Value | How it's measured | Step | Date |
|---|---|---|---|---|
| Search p95, hybrid + rerank | | `tribunal bench`; write your CPU beside it | 9 | |
| Verdict p95, end to end | | `tribunal bench --verdicts 10` | 10 | |
| Tokens per verdict | | Langfuse: the two generations of one trace, added up | 13 | |
| Docker image size | 2.16 GB on disk, 649 MB compressed | `docker image ls` | 15 | 2026-11-02 |
| Cold start of the container | at least 4.9 s (the timer started after the restart returned) | seconds from restarting the API until /readyz answers | 15 | 2026-11-02 |

## Judge quality

| Metric | Value | How it's measured | Step | Date |
|---|---|---|---|---|
| Verdict eval pass rate | 0.857 (12 of 14) | `tribunal eval --verdicts` | 10 | 2026-11-02 |
| Real-harm cases declined | 2 of 2 | the cases in data/eval/verdicts.jsonl that expect a decline | 10 | 2026-11-02 |
| Citations that name a real law | 100%, by construction | 100% by construction once the verdict eval passes: invented IDs are rejected | 10 | 2026-11-02 |

## Capacity

| Metric | Value | How it's measured | Step | Date |
|---|---|---|---|---|
| Sustained requests per second, 0 errors | 194 (500 users, on 2 CPUs: remeasure on 1) | Locust against the local stack, with the API on 1 CPU like production | 15 | 2026-11-02 |
| p95 under that load | 380 ms | the same Locust run | 15 | 2026-11-02 |
| Monthly visits the API can serve | about 25 million (194 × 129,600), not counting verdicts | the formula under Capacity, honestly, in this file | 15 | 2026-11-02 |
| Verdicts per day on free tiers | | the smaller of DAILY_BUDGET and what the provider limits allow | 16 | |

## Website

| Metric | Value | How it's measured | Step | Date |
|---|---|---|---|---|
| Page weight | | Chrome DevTools, Network tab: transferred on a fresh load | 14 | |
| Lighthouse performance | | Chrome DevTools, Lighthouse tab, mobile | 14 | |
| Lighthouse accessibility | | the same Lighthouse run | 14 | |
| Lighthouse best practices | | the same Lighthouse run | 14 | |

## Engineering

| Metric | Value | How it's measured | Step | Date |
|---|---|---|---|---|
| Automated tests | | the summary line of `uv run pytest` | 17 | |
| Test coverage | | `uv run pytest --cov=tribunal` | 17 | |
| Source files type-checked | | the summary line of `uv run mypy` | 17 | |
| CI time per push | | the test job's duration on GitHub | 17 | |
| Checks per push | | the steps in ci.yml's test job that can fail it | 17 | |

## Running it

| Metric | Value | How it's measured | Step | Date |
|---|---|---|---|---|
| Hosting cost per month | | Azure's cost analysis for the resource group; the other services are $0 on free tiers | 16 | |
| Uptime | | the System page's uptime card: checks passed out of all, over 90 days, every 30 minutes | 18 | |
| Time to recover | | how long each outage issue stayed open | 18 | |
| Visitors per month | | PostHog's web analytics | 18 | |
| Verdicts served | | PostHog: the count of verdict_shown | 18 | |
| Decrees exported | | PostHog: the count of decree_exported | 18 | |
| Thumbs-up rate | | Langfuse: the average user_feedback score | 18 | |
| Cases in the public record | | the Neon console, or a count of rows in the records table | 18 | |
| Free cases per day | | the day's case count when the court first goes into recess | 18 | |
| Worst-case cost per month | | daily budget × tokens per case × price × 30 | 18 | |

## Capacity, honestly

Two numbers describe capacity, and a resume should give both. The website is static on
GitHub Pages' CDN, so the API is the limit on everything that doesn't need an LLM:

    monthly visits ≈ R × 2,592,000 ÷ (2 requests per visit × 10 for the busiest hour)

where R is your sustained requests per second with no errors. With R = 50, that's about
6.5 million visits a month. Verdicts are limited by LLM quotas, not by the server: at most
your verdicts per day on free tiers, after which the court is in recess and the Hall of Fame
answers. So never write "serves a million users" on its own. Write, for example: "API
headroom for about 6 million visits a month (load-tested); verdicts capped at 300 a day on
free LLM tiers, degrading to an archive". A paid LLM plan lifts the second number: multiply
your tokens per verdict by the provider's price to show what a million verdicts would cost.

## From numbers to resume lines

Fill the brackets from the rows above, and cut any line you can't back with a measured number.

- Built and deployed a RAG service over 552 laws from 72 sources, with hybrid
  search (dense + BM25) and cross-encoder reranking that raised Hit@5 from 0.76 to
  0.80 (MRR 0.66 to 0.75) on a 41-query eval set that gates CI.
- Made invented citations impossible by construction: the model picks a law by ID and code
  inserts its text; 12 of 14 verdict evals pass, and 2 of 2 real-harm cases are
  declined.
- Load-tested the FastAPI service at 194 requests a second with p95 380 ms and no
  errors on 2 vCPUs, headroom for about 25 million visits a month; verdicts capped at
  [per day] a day on free LLM tiers with graceful fallback.
- Shipped with [tests] tests ([coverage] coverage), mypy-checked code, a [minutes]-minute
  CI/CD pipeline, and uptime checks every 30 minutes ([uptime] over 90 days, public history), at
  $0 a month out of pocket.
- Published every verdict to a public record with a notice, removal keys and report-to-hide
  moderation, while traces keep no content and decrees are drawn in the browser; Lighthouse
  accessibility [score].
- Live: [visitors] visitors and [verdicts] verdicts in [period], [thumbs-up] thumbs-up.
  Only include this line with real traffic.
