import json

import pytest

from tribunal.ingest import curate, sources
from tribunal.models import Catalog, Jurisdiction, Theme

THEMES = """
[fiction]
name = "Fiction"
description = "Made-up laws."
default = false
"""

SOURCE = """
jurisdiction = "wonderland"
jurisdiction_name = "Wonderland"
source = "A story written for this test"
license = "Written for this test"
"""

TEXT = "All persons taller than the door must leave the court at once."
RULE_1 = f"""+++
citation = "Rule 1"
+++
{TEXT}
"""


def make_library(tmp_path, monkeypatch):
    book = tmp_path / "laws" / "fiction" / "wonderland"
    book.mkdir(parents=True)
    (tmp_path / "laws" / "themes.toml").write_text(THEMES, encoding="utf-8")
    (book / "source.toml").write_text(SOURCE, encoding="utf-8")
    (book / "rule-1.md").write_text(RULE_1, encoding="utf-8")
    (book / "rule-2.md").write_text(
        '+++\ncitation = "Rule 2"\n+++\nPASTE the second rule here\n', encoding="utf-8"
    )
    monkeypatch.setattr(sources, "LIBRARY", tmp_path / "laws")
    monkeypatch.setattr(sources, "RAW", tmp_path / "raw")
    monkeypatch.setattr(curate, "LAWS", tmp_path / "laws.jsonl")
    monkeypatch.setattr(curate, "OVERRIDES", tmp_path / "no-overrides.json")
    monkeypatch.setattr(curate, "EVALS", tmp_path / "no-evals")
    return book


def save_corpus(laws):
    curate.LAWS.write_text("".join(law.model_dump_json() + "\n" for law in laws))


def test_a_new_theme_needs_only_files(tmp_path, monkeypatch):
    make_library(tmp_path, monkeypatch)
    laws = curate.collect()
    assert [(law.theme, law.book, law.law_id) for law in laws] == [
        ("fiction", "wonderland", "wonderland-rule-1")  # the PASTE file is skipped, not an error
    ]
    assert laws[0].citation == "Rule 1"
    assert laws[0].text == TEXT
    catalog = curate.build_catalog(laws)
    assert [theme.id for theme in catalog.themes] == ["fiction"]
    assert catalog.themes[0].jurisdictions[0].name == "Wonderland"


def test_law_files_saved_on_windows_read_the_same(tmp_path, monkeypatch):
    book = make_library(tmp_path, monkeypatch)
    (book / "rule-1.md").write_bytes(RULE_1.replace("\n", "\r\n").encode("utf-8-sig"))
    assert curate.collect()[0].text == TEXT


def test_a_law_file_without_its_header_is_rejected(tmp_path, monkeypatch):
    book = make_library(tmp_path, monkeypatch)
    (book / "rule-3.md").write_text("Just some text, with no +++ header.\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        curate.collect()


def test_a_folder_that_is_not_a_theme_is_rejected(tmp_path, monkeypatch):
    make_library(tmp_path, monkeypatch)
    (tmp_path / "laws" / "poetry" / "odes").mkdir(parents=True)
    with pytest.raises(SystemExit):
        sources.load_books()


def test_a_misspelled_key_is_rejected(tmp_path, monkeypatch):
    book = make_library(tmp_path, monkeypatch)
    (book / "source.toml").write_text(
        SOURCE.replace("jurisdiction_name", "jurisdiction_nmae"), encoding="utf-8"
    )
    with pytest.raises(SystemExit):
        sources.load_books()


def test_check_spots_laws_added_without_running_curate(tmp_path, monkeypatch):
    book = make_library(tmp_path, monkeypatch)
    save_corpus(curate.collect())
    assert curate.check_library() == []
    (book / "rule-3.md").write_text(
        '+++\ncitation = "Rule 3"\n+++\nNobody may shrink in court.\n', encoding="utf-8"
    )
    problems = curate.check_library()
    assert any("wonderland-rule-3" in problem for problem in problems)


def test_check_spots_eval_cases_that_name_missing_laws(tmp_path, monkeypatch):
    make_library(tmp_path, monkeypatch)
    save_corpus(curate.collect())
    curate.EVALS.mkdir()
    case = {"query": "too tall", "relevant": ["wonderland-rule-1", "wonderland-rule-9"]}
    (curate.EVALS / "retrieval.jsonl").write_text(json.dumps(case) + "\n", encoding="utf-8")
    expected = f"{curate.EVALS / 'retrieval.jsonl'}: no law wonderland-rule-9"
    assert curate.check_library() == [expected]


def test_the_catalog_checks_a_cases_choices():
    rome = Jurisdiction(id="rome", name="Rome", laws=5)
    ancient = Theme(id="ancient", name="Ancient", description="Real.", laws=5, jurisdictions=[rome])
    catalog = Catalog(themes=[ancient])
    catalog.check(["ancient"], "rome")  # fine
    with pytest.raises(ValueError):
        catalog.check(["fiction"], "any")
    with pytest.raises(ValueError):
        catalog.check(["ancient"], "atlantis")
