from tribunal import archive
from tribunal.models import Case, CitedLaw, Draft, Law, Ruling

PIZZA = Case(crime="He ate my pizza from the fridge.", outrage=3)


def law(text: str = "If any one steal cattle or sheep, he shall pay thirtyfold.") -> Law:
    return Law(
        law_id="hammurabi-8",
        book="hammurabi",
        theme="ancient",
        jurisdiction="babylon",
        jurisdiction_name="Babylon",
        source="Code of Hammurabi",
        citation="Law 8",
        text=text,
        tier=4,
    )


def verdict(cited: Law) -> Ruling:
    draft = Draft(
        case_title="Plaintiff v. Roommate",
        charge="Theft of pizza",
        law_id=cited.law_id,
        sentence="Thirty pizzas.",
        remarks="The crusts were the final insult.",
        historical_note="Babylon took theft seriously.",
    )
    law_fields = CitedLaw(**cited.model_dump())
    return Ruling(kind="verdict", verdict=draft, law=law_fields, meta={"trace_id": "abc"})


class FakeTribunal:
    def __init__(self, rulings):
        self.rulings = list(rulings)

    def judge(self, case):
        return self.rulings.pop(0)


def test_keeps_verdicts_and_drops_their_trace_ids():
    declined = Ruling(kind="declined", message="No grievance.")
    built = archive.build(FakeTribunal([verdict(law()), declined]), [PIZZA, PIZZA])
    assert len(built.cases) == 1
    assert built.cases[0].ruling.meta == {}


def test_an_archive_that_matches_the_corpus_passes(tmp_path):
    path = tmp_path / "hall-of-fame.json"
    archive.save(archive.Archive(cases=[archive.Famous(case=PIZZA, ruling=verdict(law()))]), path)
    assert archive.problems({"hammurabi-8": law()}, path) == []


def test_a_changed_or_deleted_law_is_reported(tmp_path):
    path = tmp_path / "hall-of-fame.json"
    archive.save(archive.Archive(cases=[archive.Famous(case=PIZZA, ruling=verdict(law()))]), path)
    changed = archive.problems({"hammurabi-8": law("A new translation of law eight.")}, path)
    assert "has changed" in changed[0]
    assert "no longer in the corpus" in archive.problems({}, path)[0]


def test_no_archive_file_is_fine(tmp_path):
    assert archive.problems({}, tmp_path / "missing.json") == []
