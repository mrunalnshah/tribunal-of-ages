import pytest
from pydantic import BaseModel

from tribunal.court import Tribunal, TribunalUnavailable, pick_for_outrage
from tribunal.llm import LLMUnavailable
from tribunal.models import Analysis, Case, Draft, Law
from tribunal.search import Hit


def law(law_id: str, tier: int | None) -> Law:
    return Law(
        law_id=law_id,
        book="test-book",
        theme="ancient",
        jurisdiction="babylon",
        jurisdiction_name="Babylon",
        source="test",
        source_url="https://x.test",
        citation=law_id,
        text=f"If any one does {law_id}, a penalty follows.",
        tier=tier,
    )


class FakeLLM:
    """Returns a canned answer per schema and runs `check`, like the real client."""

    def __init__(self, analysis: dict, draft: dict | None = None):
        self.answers: dict[type[BaseModel], dict | None] = {Analysis: analysis, Draft: draft}
        self.seen: dict = {}  # what each schema's call was sent

    def complete_json(
        self, schema, system, user, *, tier="fast", temperature=0.0, check=None, usage=None
    ):
        self.seen[schema] = user
        answer = schema(**self.answers[schema])
        if check:
            check(answer)
        return answer


class FakeIndex:
    def __init__(self, hits: list[Hit]):
        self.hits = hits

    def search(self, query, themes=None, jurisdiction=None, limit=8):
        self.themes = themes  # remember what the tribunal asked for
        return self.hits


PETTY = {"scope": "petty", "summary": "The Accused ate the pizza.", "search_query": "If any one"}
CASE = Case(crime="He ate my pizza from the fridge.", outrage=5)


def draft(law_id: str) -> dict:
    return {
        "case_title": "P v. A",
        "charge": "Theft",
        "law_id": law_id,
        "sentence": "Death.",
        "remarks": "Harsh.",
        "historical_note": "Athens was strict.",
    }


def test_the_law_text_comes_from_the_corpus():
    hits = [Hit(law("fine", 1), 2.0), Hit(law("draco", 5), 1.0)]
    ruling = Tribunal(FakeLLM(PETTY, draft("draco")), FakeIndex(hits)).judge(CASE)
    assert ruling.kind == "verdict"
    assert ruling.law.text == law("draco", 5).text


def test_the_chosen_themes_reach_the_search():
    index = FakeIndex([Hit(law("draco", 5), 1.0)])
    case = Case(crime="He ate my pizza from the fridge.", outrage=5, themes=["ancient", "fiction"])
    Tribunal(FakeLLM(PETTY, draft("draco")), index).judge(case)
    assert index.themes == ["ancient", "fiction"]


def test_real_harm_is_declined_without_a_joke():
    llm = FakeLLM({"scope": "real_harm"})
    ruling = Tribunal(llm, FakeIndex([])).judge(CASE)
    assert ruling.kind == "declined"
    assert "emergency" in ruling.message


OFF_TOPIC = {"scope": "not_a_grievance", "offense": "demanding a Flutter app from a court of law"}


def test_off_topic_requests_are_held_in_contempt_without_reaching_the_judge():
    rule = law("rule-42", 4).model_copy(update={"categories": ["contempt"]})
    llm = FakeLLM(OFF_TOPIC, draft("rule-42"))
    hits = [Hit(law("theft", 4), 3.0), Hit(rule, 2.0)]
    petition = Case(crime="Build me a Flutter app now.", outrage=4)
    ruling = Tribunal(llm, FakeIndex(hits)).judge(petition)
    assert ruling.kind == "contempt" and ruling.law is not None
    assert ruling.law.law_id == "rule-42"  # only a contempt law may be cited
    assert "demanding a Flutter app" in llm.seen[Draft] and "Build me" not in llm.seen[Draft]


def test_without_a_contempt_law_the_court_just_declines():
    llm = FakeLLM(OFF_TOPIC)
    ruling = Tribunal(llm, FakeIndex([Hit(law("theft", 1), 3.0)])).judge(CASE)
    assert ruling.kind == "declined"


def test_an_invented_law_id_is_rejected():
    hits = [Hit(law("fine", 1), 2.0)]
    with pytest.raises(ValueError):
        Tribunal(FakeLLM(PETTY, draft("made-up-law")), FakeIndex(hits)).judge(CASE)


def test_the_dial_prefers_a_matching_tier():
    hits = [Hit(law("fine", 1), 4.0), Hit(law("death", 5), 3.0), Hit(law("none", None), 3.5)]
    assert pick_for_outrage(hits, outrage=5)[0].law.law_id == "death"
    assert pick_for_outrage(hits, outrage=1)[0].law.law_id == "fine"


def test_out_of_quota_providers_say_when_the_court_reopens():
    class OutOfQuota:
        def complete_json(self, *args, **kwargs):
            raise LLMUnavailable("every LLM provider failed", retry_after=120.0)

    pizza = Case(crime="He ate my pizza from the fridge.")
    with pytest.raises(TribunalUnavailable) as failure:
        Tribunal(OutOfQuota(), FakeIndex([])).judge(pizza)
    assert failure.value.retry_after == 120.0
