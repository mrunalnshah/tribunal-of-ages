from tribunal.ingest.parsers import blocks, parse_hammurabi, parse_salic

HAMMURABI = """<html><body>
<p>When the gods made me king (a prologue without numbers).</p>
<h3>CODE OF LAWS</h3>
<p>1. If any one steal a goat, he shall pay tenfold.</p>
<p>2. If any one break a jar,
   he shall pay for the jar. [ A jar for a jar ]</p>
<p>229 If a builder build badly, he shall be put to death.</p>
<h3>THE EPILOGUE</h3>
<p>127 Wall Street, New Haven</p>
</body></html>"""

SALIC = """<html><body>
<h3>Title II. Concerning Thefts of Pigs etc.</h3>
<p>1. If any one steal a pig, he shall pay 3 shillings.</p>
<p>Title XVIII. Concerning him who accuses an innocent man.</p>
<p>If any one accuse an innocent man, he shall pay 63 shillings.</p>
<h3>Title LIX. Concerning Private Property.</h3>
<p>3. The first clause three.</p>
<p>3. The second clause three.</p>
<h3>Henderson's Note</h3>
<p>127 Wall Street, New Haven</p>
</body></html>"""


def test_blocks_split_line_breaks_and_drop_editor_notes():
    assert blocks("<p>1. First law. [note]<br>2. Second law.</p>") == [
        "1. First law.",
        "2. Second law.",
    ]


def test_hammurabi_keeps_numbered_laws_in_order():
    laws = parse_hammurabi(HAMMURABI)
    assert [law["id"] for law in laws] == ["1", "2", "229"]
    assert laws[1]["text"] == "If any one break a jar, he shall pay for the jar."


def test_hammurabi_skips_numbers_from_the_sites_menu():
    menu = "<p><a>Ancient<br>4000bce - 399</a> <a>Medieval<br>400 - 1399</a></p>"
    laws = parse_hammurabi(HAMMURABI.replace("<body>", "<body>" + menu))
    assert [law["id"] for law in laws] == ["1", "2", "229"]  # not the period "400 - 1399"


def test_salic_handles_unnumbered_and_duplicate_clauses():
    ids = [law["id"] for law in parse_salic(SALIC)]
    assert ids == ["II-1", "XVIII-1", "LIX-3", "LIX-3b"]
