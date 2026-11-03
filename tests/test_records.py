import pytest

from tribunal.models import Case, CitedLaw, Draft, Ruling
from tribunal.records import Records, RecordsUnavailable, unpublishable

PIZZA = Case(crime="My roommate ate my leftover pizza from the fridge.", outrage=3)


def verdict(law_id: str = "hammurabi-8") -> Ruling:
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
    return Ruling(kind="verdict", verdict=draft, law=law, meta={"trace_id": "secret-trace"})


@pytest.fixture
def records(tmp_path):
    store = Records(f"sqlite:///{tmp_path}/records.db", report_limit=2)
    store.setup()
    return store


def test_a_published_case_reads_back_word_for_word(records):
    published = records.add(PIZZA, verdict())
    found = records.get(published.id)
    assert found is not None and found.crime == PIZZA.crime
    assert found.ruling.law is not None and found.ruling.law.law_id == "hammurabi-8"
    assert found.ruling.meta == {}  # trace IDs never become public


def test_newest_first_with_filters_and_counts(records):
    first = records.add(PIZZA, verdict("hammurabi-8"))
    second = records.add(PIZZA, verdict("salic-xi-3"))
    newest = records.recent()
    assert [r.id for r in newest] == [second.id, first.id]
    assert [r.id for r in records.recent(law_id="hammurabi-8")] == [first.id]
    assert [r.id for r in records.recent(before=newest[0].created_at)] == [first.id]
    assert records.recent(theme="fiction") == []
    assert records.counts() == {"hammurabi-8": 1, "salic-xi-3": 1}


def test_enough_reports_hide_a_case_until_it_is_reviewed(records):
    published = records.add(PIZZA, verdict())
    records.report(published.id)
    assert records.get(published.id) is not None
    records.report(published.id)
    assert records.get(published.id) is None
    assert records.reported()[0][:3] == (published.id, 2, True)
    assert records.set_hidden(published.id, False) and records.get(published.id) is not None


def test_only_the_removal_key_removes_a_case(records):
    published = records.add(PIZZA, verdict())
    assert not records.remove(published.id, "a-guess")
    assert records.remove(published.id, published.removal_key)
    assert records.get(published.id) is None


def test_contact_details_and_links_are_not_published():
    assert unpublishable("Dave took my charger. Call me on +1 617 555 0199.")
    assert unpublishable("He emailed dave@example.com about it.")
    assert unpublishable("It's on www.example.com, see for yourself.")
    assert unpublishable("My roommate ate my leftover pizza from the fridge.") is None


def test_a_missing_database_closes_the_record_without_crashing(tmp_path):
    store = Records(f"sqlite:///{tmp_path}/no/such/folder/records.db")
    with pytest.raises(RecordsUnavailable):
        store.setup()
