from typing import Any, cast

from fastapi.testclient import TestClient

from tribunal.api import create_app
from tribunal.config import Settings
from tribunal.court import Tribunal
from tribunal.models import Catalog, CitedLaw, Draft, Jurisdiction, Ruling, Theme
from tribunal.records import Records

PIZZA = {"crime": "He ate my pizza from the fridge.", "outrage": 4, "consent": True}
BABYLON = Jurisdiction(id="babylon", name="Babylon", laws=3)
ANCIENT = Theme(
    id="ancient",
    name="Ancient laws",
    description="Real codes.",
    default=True,
    laws=3,
    jurisdictions=[BABYLON],
)
CATALOG = Catalog(themes=[ANCIENT])


class Judge:
    """Finds everyone guilty under Hammurabi's law 8."""

    index = None

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
        return Ruling(kind="verdict", verdict=draft, law=law)


def client(records: Records | None, **settings: Any) -> TestClient:
    judge = cast(Tribunal, Judge())
    return TestClient(create_app(Settings(**settings), judge, CATALOG, records))


def store(tmp_path) -> Records:
    records = Records(f"sqlite:///{tmp_path}/records.db", report_limit=2)
    records.setup()
    return records


def test_every_verdict_is_published_word_for_word_with_a_removal_key(tmp_path):
    with client(store(tmp_path)) as api:
        answer = api.post("/api/v1/verdicts", json=PIZZA).json()
        listed = api.get("/api/v1/records").json()
        one = api.get(f"/api/v1/records/{answer['record']['id']}").json()
    assert answer["kind"] == "verdict" and answer["record"]["removal_key"]
    assert listed[0]["crime"] == PIZZA["crime"]
    assert one["ruling"]["law"]["law_id"] == "hammurabi-8"


def test_the_record_takes_a_case_only_with_consent(tmp_path):
    with client(store(tmp_path)) as api:
        refused = api.post("/api/v1/verdicts", json={**PIZZA, "consent": False})
        assert api.get("/api/v1/records").json() == []
    assert refused.status_code == 422 and "Tick the box" in refused.json()["detail"]


def test_contact_details_are_judged_but_not_published(tmp_path):
    case = {**PIZZA, "crime": "He ate my pizza. Tell him at dave@example.com."}
    with client(store(tmp_path)) as api:
        answer = api.post("/api/v1/verdicts", json=case).json()
        listed = api.get("/api/v1/records").json()
    assert answer["record"] is None and "contact details" in answer["record_note"]
    assert listed == []


def test_health_checks_stay_out_of_the_record(tmp_path):
    with client(store(tmp_path)) as api:
        answer = api.post("/api/v1/verdicts", json={**PIZZA, "record": False}).json()
        assert api.get("/api/v1/records").json() == []
    assert answer["record"] is None and answer["record_note"] == ""


def test_reports_hide_a_case_and_only_its_key_removes_one(tmp_path):
    with client(store(tmp_path)) as api:
        hidden = api.post("/api/v1/verdicts", json=PIZZA).json()["record"]
        kept = api.post("/api/v1/verdicts", json=PIZZA).json()["record"]
        for _ in range(2):
            assert api.post(f"/api/v1/records/{hidden['id']}/report").status_code == 204
        assert api.get(f"/api/v1/records/{hidden['id']}").status_code == 404
        wrong = api.post(f"/api/v1/records/{kept['id']}/remove", json={"key": "not-the-key"})
        assert wrong.status_code == 404
        right = api.post(f"/api/v1/records/{kept['id']}/remove", json={"key": kept["removal_key"]})
        assert right.status_code == 204
        assert api.get("/api/v1/records").json() == []


def test_the_library_counts_verdicts_per_law(tmp_path):
    with client(store(tmp_path)) as api:
        api.post("/api/v1/verdicts", json=PIZZA)
        assert api.get("/api/v1/records/counts").json() == {"hammurabi-8": 1}


def test_a_closed_record_never_breaks_a_verdict(tmp_path):
    closed = Records(f"sqlite:///{tmp_path}/no/such/folder/records.db")
    with client(closed) as api:
        answer = api.post("/api/v1/verdicts", json=PIZZA)
        listed = api.get("/api/v1/records")
    assert answer.status_code == 200 and "closed" in answer.json()["record_note"]
    assert listed.status_code == 503
