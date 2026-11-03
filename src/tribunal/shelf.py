"""The library's shelves: every law the website lets visitors browse, as one static file.

`tribunal shelve` writes frontend/laws.json from the corpus, leaving out sensitive laws just
as search does. GitHub Pages serves it with the site, so the library opens even while the
API sleeps. CI writes it on every deploy, so it can't go stale; locally, run it after curate.
"""

import json
from pathlib import Path

from tribunal.models import Law

SHELF = Path("frontend/laws.json")
FIELDS = (
    "law_id",
    "theme",
    "jurisdiction",
    "jurisdiction_name",
    "source",
    "source_url",
    "citation",
    "text",
    "verbatim",
    "tier",
    "punishment",
    "categories",
)


def shelve(laws: list[Law], path: Path = SHELF) -> int:
    """Write the laws visitors may browse, grouped by theme and realm. Returns how many."""
    shelf = [{field: getattr(law, field) for field in FIELDS} for law in laws if not law.sensitive]
    shelf.sort(key=lambda law: (law["theme"], law["jurisdiction"], law["law_id"]))
    text = json.dumps({"laws": shelf}, ensure_ascii=False, indent=1) + "\n"
    path.write_text(text, encoding="utf-8")
    return len(shelf)
