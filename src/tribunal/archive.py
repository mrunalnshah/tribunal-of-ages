"""The Hall of Fame: past verdicts the website shows when the court can't sit.

`tribunal hall-of-fame` judges the cases in data/hall_of_fame.jsonl and saves the verdicts to
frontend/hall-of-fame.json, which GitHub Pages serves with the site. So a visitor still gets a
verdict when today's budget is spent, or when the API is asleep or down. With `--check`, it
compares the archive with the corpus instead, so an archived verdict never quotes a law that
has changed since. CI runs that check; it needs no LLM calls.
"""

from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import BaseModel

from tribunal.models import Case, Law, Ruling

if TYPE_CHECKING:  # type hints only, so the check runs without loading any models
    from tribunal.court import Tribunal

CASES = Path("data/hall_of_fame.jsonl")
ARCHIVE = Path("frontend/hall-of-fame.json")


class Famous(BaseModel):
    """One archived case and the ruling it got."""

    case: Case
    ruling: Ruling


class Archive(BaseModel):
    cases: list[Famous] = []


def read_cases(path: Path = CASES) -> list[Case]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return [Case.model_validate_json(line) for line in lines if line.strip()]


def build(tribunal: "Tribunal", cases: list[Case]) -> Archive:
    """Judge each case and keep the verdicts, not the declines.

    Trace IDs are dropped: nobody can give feedback on an archived verdict.
    """
    archive = Archive()
    for case in cases:
        ruling = tribunal.judge(case)
        if ruling.kind == "verdict":
            archive.cases.append(Famous(case=case, ruling=ruling.model_copy(update={"meta": {}})))
        print(f"{ruling.kind}: {case.crime[:60]}")
    return archive


def save(archive: Archive, path: Path = ARCHIVE) -> int:
    path.write_text(archive.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return len(archive.cases)


def problems(corpus: dict[str, Law], path: Path = ARCHIVE) -> list[str]:
    """Archived verdicts whose law has changed or left the corpus. Empty means fine."""
    if not path.exists():
        return []
    found = []
    for famous in Archive.model_validate_json(path.read_text(encoding="utf-8")).cases:
        cited = famous.ruling.law
        current = corpus.get(cited.law_id) if cited else None
        if cited is None or current is None:
            found.append(f"{path}: {famous.case.crime[:40]!r} cites a law no longer in the corpus")
        elif current.text != cited.text:
            found.append(f"{path}: {cited.law_id} has changed since it was judged")
    if found:
        found.append("Run `uv run tribunal hall-of-fame` again (about two LLM calls per case).")
    return found
