import pytest

from tribunal.models import CitedLaw, Draft, Ruling
from tribunal.stats import Stats, StatsUnavailable


def ruling(kind: str = "verdict", law_id: str = "hammurabi-8", **meta: str) -> Ruling:
    if kind == "declined":
        return Ruling(kind="declined", message="No.", meta=meta)
    draft = Draft(
        case_title="The Plaintiff v. the Pizza Bandit",
        charge="Theft of pizza",
        law_id=law_id,
        sentence="The Accused shall repay it thirtyfold.",
        remarks="The crusts were the final insult.",
        historical_note="Babylon took theft seriously.",
    )
    law = CitedLaw(
        law_id=law_id,
        theme="ancient",
        jurisdiction="babylon",
        jurisdiction_name="Babylon",
        source="Code of Hammurabi",
        source_url="https://avalon.law.yale.edu/ancient/hamcode.asp",
        citation="Law 8",
        text="If any one steal cattle or sheep, he shall pay thirtyfold.",
        verbatim=True,
        tier=4,
    )
    return Ruling(kind=kind, verdict=draft, law=law, meta=meta)


@pytest.fixture
def stats(tmp_path):
    ledger = Stats(f"sqlite:///{tmp_path}/stats.db")
    ledger.setup()
    return ledger


def test_the_ledger_counts_cases_kinds_laws_and_providers(stats):
    stats.add_case(ruling(tokens="2000", provider="groq"))
    stats.add_case(ruling(tokens="1000", provider="groq"))
    stats.add_case(ruling("contempt", "wonderland-rule-42", provider="groq-spare", fallback="1"))
    stats.add_case(ruling("declined"))
    stats.add_refusal()
    ledger = stats.ledger()
    assert (ledger.all_time, ledger.today, ledger.refused) == (4, 4, 1)
    assert ledger.kinds == {"verdict": 2, "contempt": 1, "declined": 1}
    assert [(law.law_id, law.times) for law in ledger.laws] == [
        ("hammurabi-8", 2),
        ("wonderland-rule-42", 1),
    ]
    assert ledger.providers_today == {"groq": 2, "groq-spare": 1}
    assert ledger.fallbacks_today == 1
    assert ledger.tokens_per_case == 1500  # measured cases only
    assert (ledger.tokens_today, ledger.tokens_all_time) == (3000, 3000)


def test_the_last_30_days_are_all_there_with_today_last(stats):
    stats.add_case(ruling("contempt"))
    days = stats.ledger().days
    assert len(days) == 30
    assert (days[-1].cases, days[-1].contempt) == (1, 1)
    assert all(day.cases == 0 for day in days[:-1])


def test_a_missing_database_closes_the_ledger_without_crashing(tmp_path):
    with pytest.raises(StatsUnavailable):
        Stats(f"sqlite:///{tmp_path}/no/such/folder/stats.db").setup()
