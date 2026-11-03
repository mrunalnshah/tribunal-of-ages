import json

from tribunal.models import Law
from tribunal.shelf import shelve


def law(law_id: str, theme: str = "ancient", sensitive: bool = False) -> Law:
    return Law(
        law_id=law_id,
        book="book",
        theme=theme,
        jurisdiction="babylon",
        jurisdiction_name="Babylon",
        source="Code of Hammurabi",
        citation="Law 1",
        text="A law long enough to be a law.",
        sensitive=sensitive,
    )


def test_the_shelf_leaves_out_sensitive_laws_and_sorts_by_theme(tmp_path):
    path = tmp_path / "laws.json"
    count = shelve([law("b", "fiction"), law("a"), law("c", sensitive=True)], path)
    shelf = json.loads(path.read_text(encoding="utf-8"))["laws"]
    assert count == 2
    assert [entry["law_id"] for entry in shelf] == ["a", "b"]
    assert "sensitive" not in shelf[0] and "summary" not in shelf[0]
