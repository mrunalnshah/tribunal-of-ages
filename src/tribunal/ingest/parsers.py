"""Split downloaded pages into individual laws.

Each source has quirks, so each gets a small parser. They share `blocks()`, which hides
how a page is laid out (one <p> per law, or one <p> of <br>-separated lines) behind a
plain list of text blocks in reading order. A parser returns each law's own number as its
"id"; sources.py adds the book's name, so every law ID in the library follows one rule.
"""

import re

from bs4 import BeautifulSoup

HTML_PARSER = "html5lib"  # parses like a browser, so unclosed <p> tags on old pages are fine
BLOCK_TAGS = ["p", "h1", "h2", "h3", "h4", "h5", "li", "td", "div", "blockquote"]
LINE_BREAK = "\u2029"  # stands in for <br>; this character never appears in the texts
LAST_LAW = 282  # the Code's last law: a bigger number is something else on the page
NUMBERED = re.compile(r"^(\d{1,3})\.?\s+(.+)$")  # "8. If any one..." and the odd "229 If..."
TITLE = re.compile(r"^Title ([IVXL]+)\b")
EDITORIAL = re.compile(r"\s*\[[^\]]*\]")  # the web editors' notes, e.g. "[ An eye for an eye ]"


def blocks(html: bytes | str) -> list[str]:
    """Text of every innermost block element: whitespace collapsed, editors' notes removed."""
    soup = BeautifulSoup(html, HTML_PARSER)
    for br in soup.find_all("br"):
        br.replace_with(LINE_BREAK)
    texts = []
    for element in soup.find_all(BLOCK_TAGS):
        if element.find(BLOCK_TAGS):  # a container: its children are visited on their own
            continue
        for piece in element.get_text().split(LINE_BREAK):
            text = EDITORIAL.sub("", " ".join(piece.split())).strip()
            if text:
                texts.append(text)
    return texts


def parse_hammurabi(html: bytes | str) -> list[dict]:
    """Laws numbered 1-282, in increasing order. Anything else on the page that starts with a
    number is skipped: the footer's address, or the site menu's "Medieval 400 - 1399"."""
    laws: list[dict] = []
    last = 0
    for text in blocks(html):
        match = NUMBERED.match(text)
        if match and last < int(match.group(1)) <= LAST_LAW:
            last = int(match.group(1))
            laws.append({"id": str(last), "citation": f"Law {last}", "text": match.group(2)})
    return laws


def parse_salic(html: bytes | str) -> list[dict]:
    """Clauses numbered within titles: clause 1 of Title II gets the id "II-1"."""
    laws: list[dict] = []
    title: str | None = None
    in_title = 0
    for text in blocks(html):
        if text.startswith("Henderson"):  # the editor's closing note: no laws after this
            break
        if match := TITLE.match(text):
            title, in_title = match.group(1), 0
            continue
        match = NUMBERED.match(text)
        if title and match:
            number, body = match.group(1), match.group(2)
        elif title and in_title == 0 and text.startswith("If "):
            number, body = "1", text  # Title XVIII's only clause has no number
        else:
            continue
        law_id = f"{title}-{number}"
        while any(law["id"] == law_id for law in laws):
            law_id += "b"  # the source numbers two clauses of Title LIX as "3"
        in_title += 1
        laws.append({"id": law_id, "citation": f"Title {title}, §{number}", "text": body})
    return laws


PARSERS = {"hammurabi": parse_hammurabi, "salic": parse_salic}
