"""The law library: data/laws/ holds every law the court knows, as plain files.

    data/laws/themes.toml                    the themes, in the order the website shows them
    data/laws/<theme>/<book>/source.toml     what a book's laws share: realm, source, license
    data/laws/<theme>/<book>/<law>.md        one law: a +++ header with its citation, then its text

A book either has law files or names a `parser` that splits its web page into laws. A law's ID
is "<book>-<file name>", so name files once and don't rename them. Adding laws, books or
themes needs no code: add files, then run `tribunal curate`.
"""

import re
import tomllib
from collections import Counter
from pathlib import Path

import httpx
from pydantic import BaseModel, ConfigDict

LIBRARY = Path("data/laws")
RAW = Path("data/raw")
NAME = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")  # book and file names, which become law IDs


class Entry(BaseModel):
    """One law as found in the library, before curation adds its labels."""

    law_id: str
    citation: str
    text: str

    @property
    def ready(self) -> bool:
        """False for a placeholder whose text hasn't been pasted in yet."""
        return not self.text.startswith("PASTE")


class LawHeader(BaseModel):
    """The +++ header at the top of a law file."""

    model_config = ConfigDict(extra="forbid")  # a misspelled key is an error, not ignored

    citation: str


class Book(BaseModel):
    """One book of laws: what its laws share, read from its source.toml."""

    model_config = ConfigDict(extra="forbid")

    folder: Path
    theme: str
    name: str
    jurisdiction: str
    jurisdiction_name: str
    source: str
    source_url: str = ""
    license: str
    verbatim: bool = True  # False: the texts are our own paraphrases of a copyrighted work
    parser: str | None = None  # split the page at source_url with this parser

    @property
    def raw_page(self) -> Path:
        return RAW / f"{self.name}.html"

    def laws(self) -> list[Entry]:
        """The book's laws: its .md files in name order, or the laws its parser finds."""
        files = sorted(self.folder.glob("*.md"))
        if not self.parser:
            return [self._read(path) for path in files]
        if files:
            raise SystemExit(f"{self.folder}: a book has a parser or law files, not both")
        from tribunal.ingest.parsers import PARSERS  # here, so downloading doesn't need them

        if self.parser not in PARSERS:
            raise SystemExit(f"{self.folder / 'source.toml'}: no parser called {self.parser!r}")
        found = PARSERS[self.parser](self.page())
        return [
            Entry(law_id=f"{self.name}-{law['id']}", citation=law["citation"], text=law["text"])
            for law in found
        ]

    def page(self, refresh: bool = False) -> bytes:
        """The book's web page: downloaded once into data/raw/, then read from disk."""
        if refresh or not self.raw_page.exists():
            headers = {"User-Agent": "tribunal-of-ages/1.0 (personal, educational)"}
            response = httpx.get(
                self.source_url, headers=headers, timeout=30, follow_redirects=True
            )
            response.raise_for_status()
            RAW.mkdir(parents=True, exist_ok=True)
            self.raw_page.write_bytes(response.content)  # raw bytes: the parser finds the encoding
            print(f"{self.name}: saved {len(response.content):,} bytes")
        return self.raw_page.read_bytes()

    def _read(self, path: Path) -> Entry:
        if not NAME.match(path.stem):
            raise SystemExit(f"{path}: name law files with lowercase letters, digits and hyphens")
        try:
            header, text = split_law_file(path.read_text(encoding="utf-8-sig"))
            citation = LawHeader(**tomllib.loads(header)).citation
        except ValueError as err:  # TOML and validation errors are ValueErrors too
            raise SystemExit(f"{path}: {err}") from err
        return Entry(law_id=f"{self.name}-{path.stem}", citation=citation, text=text)


def split_law_file(content: str) -> tuple[str, str]:
    """Split a law file into its header (between the two +++ lines) and its text."""
    lines = content.replace("\r\n", "\n").split("\n")  # files saved on Windows work too
    ends = [i for i, line in enumerate(lines) if line.strip() == "+++"]
    if len(ends) < 2 or ends[0] != 0:
        raise ValueError("a law file starts with a +++ line, its header, then another +++ line")
    return "\n".join(lines[1 : ends[1]]), "\n".join(lines[ends[1] + 1 :]).strip()


def load_themes() -> dict[str, dict]:
    """themes.toml as {theme_id: {"name": ..., "description": ..., "default": ...}}, in order."""
    return tomllib.loads((LIBRARY / "themes.toml").read_text(encoding="utf-8"))


def load_books() -> list[Book]:
    """Every book in the library, checked. A mistake stops here, naming the file to fix."""
    themes = load_themes()
    books = []
    for item in sorted(LIBRARY.glob("*/*")):
        theme, name = item.parent.name, item.name
        if theme not in themes:
            raise SystemExit(f"{item}: {theme!r} isn't a theme in {LIBRARY / 'themes.toml'}")
        if not item.is_dir():
            raise SystemExit(f"{item}: put law files in a book folder, {item.parent}/<book>/")
        if not NAME.match(name):
            raise SystemExit(f"{item}: book folder names use lowercase letters, digits, hyphens")
        try:
            data = tomllib.loads((item / "source.toml").read_text(encoding="utf-8"))
            books.append(Book(folder=item, theme=theme, name=name, **data))
        except (OSError, TypeError, ValueError) as err:
            raise SystemExit(f"{item / 'source.toml'}: {err}") from err
    repeated = [name for name, n in Counter(book.name for book in books).items() if n > 1]
    if repeated:
        raise SystemExit(f"book names must be unique across themes: {repeated}")
    return books


def download(refresh: bool = False) -> None:
    """Fetch the web page of every book that has a parser, once (or again, with refresh)."""
    for book in load_books():
        if not book.parser:
            continue
        if book.raw_page.exists() and not refresh:
            print(f"{book.name}: already downloaded")
        else:
            book.page(refresh=True)
