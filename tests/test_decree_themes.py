import json
import re
import tomllib
from pathlib import Path

THEMES = json.loads(Path("frontend/decree-themes.json").read_text(encoding="utf-8"))["themes"]
LAW_THEMES = set(tomllib.loads(Path("data/laws/themes.toml").read_text(encoding="utf-8")))
COLOR = re.compile(r"^#[0-9a-f]{6}$")
REQUIRED = {"id", "name", "title", "paper", "ink"}
CHOICES = {  # the styles decree.js can draw; a design that leaves one out gets its default
    "texture": {"none", "speckle", "fibers", "veins", "grain"},
    "border": {"double", "wedges", "dots", "bold"},
    "portrait": {"circle", "oval", "square"},
}
OPTIONAL = {"suits", "accent", "seal", "font", *CHOICES}


def luminance(color: str) -> float:
    def channel(c: float) -> float:
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (channel(int(color[i : i + 2], 16) / 255) for i in (1, 3, 5))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a: str, b: str) -> float:
    light, dark = sorted((luminance(a), luminance(b)), reverse=True)
    return (light + 0.05) / (dark + 0.05)


def test_every_design_has_known_fields_and_values():
    ids = [theme["id"] for theme in THEMES]
    assert len(ids) == len(set(ids))
    for theme in THEMES:
        assert REQUIRED <= set(theme) <= REQUIRED | OPTIONAL, theme.get("id")  # catches typos
        assert re.match(r"^[a-z0-9]+(-[a-z0-9]+)*$", theme["id"])
        assert len(theme["paper"]) == 2
        extra = [theme[key] for key in ("accent", "seal") if key in theme]
        colors = [*theme["paper"], theme["ink"], *extra]
        assert all(COLOR.match(color) for color in colors), theme["id"]
        assert set(theme.get("suits", [])) <= LAW_THEMES, theme["id"]
        for key, allowed in CHOICES.items():
            assert theme.get(key, next(iter(allowed))) in allowed, (theme["id"], key)


def test_every_design_is_readable():
    # WCAG: 4.5:1 for body text; 3:1 for the large, bold labels and the seal.
    for theme in THEMES:
        accent = theme.get("accent", theme["ink"])
        seal = theme.get("seal", accent)
        for paper in theme["paper"]:
            assert contrast(theme["ink"], paper) >= 4.5, theme["id"]
            assert contrast(accent, paper) >= 3, theme["id"]
        assert contrast(seal, theme["paper"][0]) >= 3, theme["id"]
