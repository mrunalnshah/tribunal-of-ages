from typing import Any, cast

from fastapi.testclient import TestClient

from tribunal.api import create_app
from tribunal.config import Settings
from tribunal.court import Tribunal, TribunalUnavailable
from tribunal.models import Catalog, Jurisdiction, Ruling, Theme

PIZZA = {"crime": "He ate my pizza from the fridge.", "outrage": 4}
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


class FakeTribunal:
    def __init__(self, down: bool = False, busy_for: float | None = None):
        self.down = down
        self.busy_for = busy_for  # seconds until the providers' quota comes back
        self.index = self  # the API also asks the tribunal's index for laws and counts

    def judge(self, case):
        if self.down:
            raise TribunalUnavailable("providers down")
        if self.busy_for is not None:
            raise TribunalUnavailable("out of quota", retry_after=self.busy_for)
        return Ruling(kind="declined", message=f"dial {case.outrage}")

    def get(self, law_id):
        return None

    def count(self):
        return 3


def client(tribunal: object = None, **settings: Any) -> TestClient:
    fake = cast(Tribunal, tribunal or FakeTribunal())  # the API only calls judge() and index
    return TestClient(create_app(Settings(**settings), fake, CATALOG))


def test_a_case_gets_a_ruling():
    with client() as api:
        response = api.post("/api/v1/verdicts", json=PIZZA)
    assert response.status_code == 200
    assert response.json()["message"] == "dial 4"


def test_invalid_input_is_rejected_before_any_llm_call():
    with client() as api:
        response = api.post("/api/v1/verdicts", json={"crime": "short", "outrage": 9})
    assert response.status_code == 422


def test_the_catalog_lists_the_themes():
    with client() as api:
        themes = api.get("/api/v1/catalog").json()["themes"]
    assert [theme["id"] for theme in themes] == ["ancient"]


def test_unknown_themes_and_jurisdictions_are_rejected():
    with client() as api:
        bad_theme = api.post("/api/v1/verdicts", json={**PIZZA, "themes": ["poetry"]})
        bad_place = api.post("/api/v1/verdicts", json={**PIZZA, "jurisdiction": "atlantis"})
    assert bad_theme.status_code == 422
    assert bad_place.status_code == 422


def test_an_outage_becomes_503():
    with client(FakeTribunal(down=True)) as api:
        response = api.post("/api/v1/verdicts", json=PIZZA)
    assert response.status_code == 503


def test_spent_provider_quota_says_when_the_court_reopens():
    with client(FakeTribunal(busy_for=725.2)) as api:
        response = api.post("/api/v1/verdicts", json=PIZZA)
    assert response.status_code == 429
    assert response.headers["retry-after"] == "726"
    assert "about 12 minutes" in response.json()["detail"]


def test_readiness_reports_the_index():
    with client() as api:
        assert api.get("/readyz").json() == {"ok": True, "laws": 3}


def test_rate_limit_answers_429_with_retry_after():
    with client(requests_per_minute=1) as api:
        api.post("/api/v1/verdicts", json=PIZZA)
        second = api.post("/api/v1/verdicts", json={**PIZZA, "crime": "He ate my fries too!"})
    assert second.status_code == 429
    assert int(second.headers["retry-after"]) > 0
