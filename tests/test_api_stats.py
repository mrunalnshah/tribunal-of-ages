from typing import Any, cast

from fastapi.testclient import TestClient

from tribunal.api import create_app
from tribunal.config import Settings
from tribunal.court import Tribunal
from tribunal.models import Catalog, CitedLaw, Draft, Jurisdiction, Ruling, Theme
from tribunal.stats import Stats

PIZZA = {"crime": "He ate my pizza from the fridge.", "outrage": 4, "record": False}
CATALOG = Catalog(
    themes=[
        Theme(
            id="ancient",
            name="Ancient laws",
            description="Real codes.",
            default=True,
            laws=3,
            jurisdictions=[Jurisdiction(id="babylon", name="Babylon", laws=3)],
        )
    ]
)


class Judge:
    """Finds everyone guilty under Hammurabi's law 8, for 1,500 tokens."""

    def judge(self, case):
        draft = Draft(
            case_title="The Plaintiff v. the Pizza Bandit",
            charge="Theft of pizza",
            law_id="hammurabi-8",
            sentence="The Accused shall repay it thirtyfold.",
            remarks="The crusts were the final insult.",
            historical_note="Babylon took theft seriously.",
        )
        law = CitedLaw(
            law_id="hammurabi-8",
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
        meta = {"tokens": "1500", "provider": "groq", "fallback": "0"}
        return Ruling(kind="verdict", verdict=draft, law=law, meta=meta)


def client(tmp_path, **settings: Any) -> TestClient:
    stats = Stats(f"sqlite:///{tmp_path}/stats.db")
    stats.setup()
    judge = cast(Tribunal, Judge())
    return TestClient(create_app(Settings(**settings), judge, CATALOG, None, stats))


def test_the_ledger_counts_cases_and_reports_the_capacity(tmp_path):
    with client(tmp_path, daily_budget=40) as api:
        api.get("/api/v1/stats")  # warms the cache: the next case must still show
        api.post("/api/v1/verdicts", json=PIZZA)
        board = api.get("/api/v1/stats").json()
    assert (board["ledger"]["all_time"], board["ledger"]["today"], board["per_day"]) == (1, 1, 40)
    assert board["ledger"]["laws"] == [{"law_id": "hammurabi-8", "times": 1}]
    assert board["ledger"]["tokens_per_case"] == 1500
    assert board["ledger"]["tokens_today"] == 1500
    assert board["tokens_per_day"] == 40 * 2_400  # the free plan: its cases, at 2,400 tokens each


def test_requests_stopped_at_the_door_are_counted(tmp_path):
    with client(tmp_path, visitor_daily_limit=1, max_body_bytes=200) as api:
        api.post("/api/v1/verdicts", json=PIZZA)
        assert api.post("/api/v1/verdicts", json=PIZZA).status_code == 429  # over the limit
        assert api.post("/api/v1/verdicts", json={"crime": "short"}).status_code == 422
        assert api.post("/api/v1/verdicts", content=b"x" * 500).status_code == 413
        board = api.get("/api/v1/stats").json()
    assert board["saved"]["refused"] == 3
    assert board["saved"]["refused_tokens"] == 3 * 1500  # at the measured cost of a case
