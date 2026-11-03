"""Build the corpus: collect every law in data/laws/, label, apply overrides, check, save.

Writes data/processed/laws.jsonl (the laws) and catalog.json (the themes and jurisdictions
the website offers). Every step can be rerun; LLM labels are cached per law, so a rerun
costs nothing unless a law's text or the labeling prompt changes. `check_library()` needs no
LLM at all: CI runs it to catch a broken law file, or laws added without running curate.
"""

import csv
import hashlib
import json
import random
from collections import Counter
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from tribunal import prompts
from tribunal.ingest.sources import load_books, load_themes
from tribunal.llm import LLMClient
from tribunal.models import Catalog, Jurisdiction, LabelBatch, Law, Theme

LAWS = Path("data/processed/laws.jsonl")
CATALOG = Path("data/processed/catalog.json")
CACHE = Path("data/cache/labels.jsonl")
OVERRIDES = Path("data/overrides.json")
REVIEW = Path("data/review.csv")
EVALS = Path("data/eval")
LABEL_PROMPT = "label_v1"
BATCH = 8


def curate(llm: LLMClient) -> list[Law]:
    laws = apply_overrides(label(collect(), llm))
    check(laws)
    catalog = build_catalog(laws)
    LAWS.parent.mkdir(parents=True, exist_ok=True)
    LAWS.write_text("".join(law.model_dump_json() + "\n" for law in laws), encoding="utf-8")
    CATALOG.write_text(catalog.model_dump_json(indent=2) + "\n", encoding="utf-8")
    write_review_sheet(laws)
    report(laws, catalog)
    return laws


def load_laws(path: Path | None = None) -> list[Law]:
    path = path or LAWS  # looked up at call time, so tests and scripts can point it elsewhere
    if not path.exists():
        raise SystemExit(f"{path} is missing: run `uv run tribunal curate` first")
    lines = path.read_text(encoding="utf-8").splitlines()
    return [Law.model_validate_json(line) for line in lines if line]


def collect() -> list[Law]:
    """Every finished law in the library, with its book's details. Labels are still empty."""
    laws: list[Law] = []
    for book in load_books():
        entries = book.laws()
        ready = [entry for entry in entries if entry.ready]
        if len(ready) < len(entries):
            print(f"{book.folder}: skipping {len(entries) - len(ready)} laws still marked PASTE")
        shared: dict[str, Any] = {
            "book": book.name,
            "theme": book.theme,
            "jurisdiction": book.jurisdiction,
            "jurisdiction_name": book.jurisdiction_name,
            "source": book.source,
            "source_url": book.source_url,
            "verbatim": book.verbatim,
        }
        try:
            laws += [Law(**shared, **entry.model_dump()) for entry in ready]
        except ValidationError as err:
            raise SystemExit(f"{book.folder}: {err}") from err
        print(f"{book.theme}/{book.name}: {len(ready)} laws")
    return laws


def check_library() -> list[str]:
    """Problems found without any LLM call, in the files you edit by hand. Empty means fine."""
    corpus = {law.law_id: law for law in load_laws()}
    books = load_books()  # a malformed file stops here, with its name
    problems: list[str] = []
    pending: set[str] = set()
    for book in books:
        if book.parser:
            continue  # parsed pages aren't fetched here; curate checks them
        on_disk = {entry.law_id: entry for entry in book.laws()}
        pending |= {law_id for law_id, entry in on_disk.items() if not entry.ready}
        for law_id, entry in on_disk.items():
            if entry.ready and (law_id not in corpus or corpus[law_id].text != entry.text):
                problems.append(f"{law_id}: added or edited since the last curate")
        for law_id, law in corpus.items():
            if law.book == book.name and law_id not in on_disk:
                problems.append(f"{law_id}: deleted from the library but still in the corpus")
    names = {book.name for book in books}
    problems += [
        f"{i}: its book is gone from the library"
        for i, law in corpus.items()
        if law.book not in names
    ]
    if problems:
        problems.append("Run `uv run tribunal curate`, then commit data/processed/.")
    fixes = json.loads(OVERRIDES.read_text(encoding="utf-8")) if OVERRIDES.exists() else {}
    problems += [f"{OVERRIDES}: no law {i}" for i in sorted(set(fixes) - set(corpus))]
    for path in sorted(EVALS.glob("*.jsonl")):
        cases = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
        wanted = {i for case in cases for i in case.get("relevant", [])}
        problems += [f"{path}: no law {i}" for i in sorted(wanted - set(corpus) - pending)]
    return problems


def label(laws: list[Law], llm: LLMClient) -> list[Law]:
    """Fill each law's label fields, asking the LLM only about laws not in the cache."""
    cache = _read_cache()
    todo = [law for law in laws if _key(law) not in cache]
    for start in range(0, len(todo), BATCH):
        batch = todo[start : start + BATCH]
        ids = [law.law_id for law in batch]

        def same_ids(answer: LabelBatch, ids: list[str] = ids) -> None:
            if [item.law_id for item in answer.labels] != ids:
                raise ValueError(f"return exactly one label per law, in this order: {ids}")

        rows = [{"law_id": law.law_id, "theme": law.theme, "text": law.text} for law in batch]
        payload = json.dumps(rows)
        answer = llm.complete_json(LabelBatch, prompts.load(LABEL_PROMPT), payload, check=same_ids)
        with CACHE.open("a", encoding="utf-8") as file:
            for law, item in zip(batch, answer.labels, strict=True):
                cache[_key(law)] = item.model_dump(exclude={"law_id"})
                file.write(json.dumps({"key": _key(law), "label": cache[_key(law)]}) + "\n")
        print(f"labeled {start + len(batch)}/{len(todo)}")
    return [law.model_copy(update=cache[_key(law)]) for law in laws]


def apply_overrides(laws: list[Law]) -> list[Law]:
    """Human corrections in data/overrides.json ({law_id: {field: value}}) always win."""
    if not OVERRIDES.exists():
        return laws
    fixes = json.loads(OVERRIDES.read_text(encoding="utf-8"))
    unknown = set(fixes) - {law.law_id for law in laws}
    if unknown:
        raise SystemExit(f"overrides.json names unknown laws: {sorted(unknown)}")
    return [Law(**{**law.model_dump(), **fixes.get(law.law_id, {})}) for law in laws]


def check(laws: list[Law]) -> None:
    counts = Counter(law.law_id for law in laws)
    duplicates = [law_id for law_id, n in counts.items() if n > 1]
    if duplicates:
        raise SystemExit(f"duplicate law_ids: {duplicates}")
    names: dict[str, set[str]] = {}
    for law in laws:
        names.setdefault(law.jurisdiction, set()).add(law.jurisdiction_name)
    clashes = {place: sorted(found) for place, found in names.items() if len(found) > 1}
    if clashes:
        raise SystemExit(f"one jurisdiction id, several names: {clashes}")


def build_catalog(laws: list[Law]) -> Catalog:
    """Themes in themes.toml order, each with its jurisdictions and searchable-law counts."""
    searchable = [law for law in laws if not law.sensitive]
    themes = []
    for theme_id, info in load_themes().items():
        members = [law for law in searchable if law.theme == theme_id]
        if not members:
            continue  # a theme appears on the website once it has a searchable law
        counts = Counter((law.jurisdiction, law.jurisdiction_name) for law in members)
        places = [
            Jurisdiction(id=place, name=name, laws=n)
            for (place, name), n in sorted(counts.items(), key=lambda item: item[0][1])
        ]
        themes.append(Theme(id=theme_id, laws=len(members), jurisdictions=places, **info))
    return Catalog(themes=themes)


def write_review_sheet(laws: list[Law]) -> None:
    """A CSV for human review: a random 15% sample plus every death-tier or sensitive law."""
    sample = random.Random(42).sample(laws, k=max(1, len(laws) * 15 // 100))
    chosen = {law.law_id: law for law in sample + [x for x in laws if x.tier == 5 or x.sensitive]}
    with REVIEW.open("w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(["law_id", "theme", "tier", "sensitive", "punishment", "summary", "text"])
        for law in chosen.values():
            row = [law.law_id, law.theme, law.tier, law.sensitive, law.punishment, law.summary]
            writer.writerow([*row, law.text])


def report(laws: list[Law], catalog: Catalog) -> None:
    searchable = [law for law in laws if not law.sensitive]
    hidden = len(laws) - len(searchable)
    print(f"\n{len(laws)} laws: {len(searchable)} searchable, {hidden} sensitive")
    for theme in catalog.themes:
        places = ", ".join(f"{place.name} {place.laws}" for place in theme.jurisdictions)
        print(f"{theme.name}: {theme.laws} ({places})")
    tiers = Counter(law.tier for law in searchable)
    print("by tier:", {tier: tiers[tier] for tier in [1, 2, 3, 4, 5, None]})
    print(f"review sheet: {REVIEW}")


def _key(law: Law) -> str:
    return hashlib.sha256(f"{LABEL_PROMPT}|{law.law_id}|{law.text}".encode()).hexdigest()[:16]


def _read_cache() -> dict[str, dict]:
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    if not CACHE.exists():
        return {}
    rows = [json.loads(line) for line in CACHE.read_text(encoding="utf-8").splitlines() if line]
    return {row["key"]: row["label"] for row in rows}
