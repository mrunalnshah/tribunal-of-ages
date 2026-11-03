"""The data shapes that cross module boundaries. Pydantic checks them at runtime."""

from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints

# Theme and jurisdiction IDs are short lowercase names, like "ancient" or "wonderland".
Slug = Annotated[str, StringConstraints(pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$", max_length=40)]
Category = Literal[
    "theft",
    "robbery",
    "property_damage",
    "assault",
    "insult",
    "fraud",
    "debt",
    "negligence",
    "trespass",
    "idleness",
    "false_accusation",
    "contempt",
    "other",
]


class Law(BaseModel):
    """One citable law, from history, myth or fiction.

    `text` is the only thing users ever see as "the law": verbatim from a public-domain
    source or, when `verbatim` is false, our own paraphrase of a copyrighted story. The label
    fields are written during curation; they power search and the Outrage Dial.
    """

    law_id: str
    book: Slug
    theme: Slug
    jurisdiction: Slug
    jurisdiction_name: str
    source: str
    source_url: str = ""
    citation: str
    text: str = Field(min_length=10)
    verbatim: bool = True
    summary: str = ""
    categories: list[Category] = []
    punishment: str = ""
    tier: int | None = Field(default=None, ge=1, le=5)  # None: the law states no penalty
    sensitive: bool = False  # never retrieved; see docs/DATA_POLICY.md


class LawLabel(BaseModel):
    """The labeling model's answer for one law."""

    law_id: str
    summary: str = Field(max_length=400)
    categories: list[Category]
    punishment: str
    tier: int | None = Field(default=None, ge=1, le=5)
    sensitive: bool


class LabelBatch(BaseModel):
    labels: list[LawLabel]


CRIME_MAX = 600  # characters the court reads; anything longer is kept, but never judged
KEPT_MAX = 5_000  # characters the private history keeps of a grievance


class Case(BaseModel):
    """A grievance submitted by a user, and which kinds of law may judge it."""

    crime: str = Field(min_length=10, max_length=CRIME_MAX)
    outrage: int = Field(default=3, ge=1, le=5)
    themes: list[Slug] = Field(default=["ancient"], min_length=1, max_length=10)
    jurisdiction: Slug = "any"


class Analysis(BaseModel):
    """Stage A: what the case is about, with names replaced by roles."""

    scope: Literal["petty", "real_harm", "not_a_grievance"]
    categories: list[Category] = []
    summary: str = Field(default="", max_length=400)
    details: list[str] = Field(default=[], max_length=4)
    search_query: str = Field(default="", max_length=400)
    offense: str = Field(default="", max_length=160)  # what a not_a_grievance petition asked for


class Draft(BaseModel):
    """Stage C: the judge's verdict. It names its law by ID and never quotes it."""

    case_title: str = Field(max_length=120)
    charge: str = Field(max_length=200)
    law_id: str
    sentence: str = Field(max_length=600)
    remarks: str = Field(max_length=600)
    historical_note: str = Field(max_length=400)


class CitedLaw(BaseModel):
    law_id: str
    theme: str
    jurisdiction: str
    jurisdiction_name: str
    source: str
    source_url: str
    citation: str
    text: str
    verbatim: bool
    tier: int | None


class Ruling(BaseModel):
    """The API response. `kind` tells clients which fields to render."""

    kind: Literal["verdict", "contempt", "declined"]
    message: str = ""
    verdict: Draft | None = None
    law: CitedLaw | None = None
    meta: dict[str, str] = {}


class Jurisdiction(BaseModel):
    id: str
    name: str
    laws: int


class Theme(BaseModel):
    id: str
    name: str
    description: str
    default: bool = False
    laws: int
    jurisdictions: list[Jurisdiction]


class Catalog(BaseModel):
    """Every theme and jurisdiction that has searchable laws. Built by `tribunal curate`."""

    themes: list[Theme]

    def check(self, themes: list[str], jurisdiction: str) -> None:
        """Raise ValueError unless every theme exists and the jurisdiction is in one of them."""
        known = {theme.id: theme for theme in self.themes}
        unknown = sorted(set(themes) - set(known))
        if unknown:
            raise ValueError(f"unknown theme: {', '.join(unknown)}")
        places = {place.id for theme in themes for place in known[theme].jurisdictions}
        if jurisdiction != "any" and jurisdiction not in places:
            raise ValueError(f"no jurisdiction {jurisdiction!r} in the chosen themes")
