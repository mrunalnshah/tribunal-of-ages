import json
from typing import Any, cast

from fastapi.testclient import TestClient

from tribunal.api import create_app
from tribunal.config import Settings
from tribunal.court import Tribunal
from tribunal.history import History
from tribunal.models import Catalog, CitedLaw, Draft, Jurisdiction, Ruling, Theme
from tribunal.records import Records

PIZZA = {"crime": "He ate my pizza from the fridge.", "outrage": 4, "consent": True}
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
    """Finds everyone guilty under Hammurabi's law 8."""

    calls = 0

    def judge(self, case):
        Judge.calls += 1
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
        return Ruling(kind="verdict", verdict=draft, law=law)


def court(tmp_path, **settings: Any) -> tuple[TestClient, History]:
    url = f"sqlite:///{tmp_path}/court.db"
    records, history = Records(url), History(url)
    records.setup()
    history.setup()
    app = create_app(Settings(**settings), cast(Tribunal, Judge()), CATALOG, records, None, history)
    return TestClient(app), history


def kept(history: History, tmp_path) -> list[dict]:
    path = tmp_path / "history.jsonl"
    history.export(path)
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_a_grievance_too_long_to_judge_is_kept_and_costs_no_case(tmp_path):
    api, history = court(tmp_path, visitor_daily_limit=1)
    Judge.calls = 0
    with api:
        long = api.post("/api/v1/verdicts", json={**PIZZA, "crime": "He ate it. " * 100})
        judged = api.post("/api/v1/verdicts", json=PIZZA)  # the visitor's one case is intact
    assert long.status_code == 422 and "It's been kept" in long.json()["detail"]
    assert judged.status_code == 200 and Judge.calls == 1  # the long one never reached a judge
    entries = kept(history, tmp_path)
    assert [entry["outcome"] for entry in entries] == ["too_long", "verdict"]
    assert entries[0]["length"] == 1100 and entries[1]["record_id"] == judged.json()["record"]["id"]


def test_removing_a_case_removes_its_entry_and_health_checks_are_never_kept(tmp_path):
    api, history = court(tmp_path)
    with api:
        published = api.post("/api/v1/verdicts", json=PIZZA).json()["record"]
        api.post("/api/v1/verdicts", json={**PIZZA, "record": False})  # a health check
        key = {"key": published["removal_key"]}
        assert api.post(f"/api/v1/records/{published['id']}/remove", json=key).status_code == 204
    assert kept(history, tmp_path) == []
