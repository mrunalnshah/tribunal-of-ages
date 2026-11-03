"""The Tribunal: turns a grievance into a ruling grounded in one law from the corpus.

Pipeline: analyze the story (fast model), search the laws, prefer laws near the Outrage
Dial, judge (smart model), then attach the law's verbatim text. The model refers to laws
only by ID; the text users see comes from our corpus, so it can't be misquoted. A petition
that isn't a grievance (an app, the time, a shopping list) is held in contempt instead,
under a law about conduct before a court. Real harm is always declined, never joked about.
"""

import json
import math
from typing import Literal

from tribunal import prompts
from tribunal.llm import LLMClient, LLMUnavailable, Usage
from tribunal.models import Analysis, Case, CitedLaw, Draft, Ruling
from tribunal.search import Hit, LawIndex, SearchUnavailable
from tribunal.telemetry import observe, trace_id

ANALYSIS_PROMPT = "analysis_v1"
VERDICT_PROMPT = "verdict_v1"
CONTEMPT_PROMPT = "contempt_v1"
CONTEMPT_QUERY = (
    "If any one bring before the judges a case that is no case, and waste the time of the court"
)
CONTEMPT = {"contempt", "false_accusation"}  # laws the court may hold someone in contempt under
DECLINED = {
    "real_harm": (
        "This sounds like a real situation that could involve harm, so the court won't joke "
        "about it. If anyone is in danger, contact local emergency services or someone you trust."
    ),
    "not_a_grievance": "The court found no grievance here. Tell it what someone did to you.",
    "no_law": "The ancients were silent on this matter. Try describing it another way.",
}


class TribunalUnavailable(Exception):
    """No ruling right now: the LLM providers or the search index are down, or out of quota.

    `retry_after` is the seconds until the providers expect to answer again when they're only
    out of quota, and None when something is actually down.
    """

    def __init__(self, message: str, retry_after: float | None = None):
        super().__init__(message)
        self.retry_after = retry_after


class Tribunal:
    def __init__(self, llm: LLMClient, index: LawIndex):
        self.llm = llm
        self.index = index

    @observe()
    def judge(self, case: Case) -> Ruling:
        usage = Usage()  # what this case costs, and who answered
        try:
            analysis = self._analyze(case, usage)
            if analysis.scope == "real_harm":
                return Ruling(kind="declined", message=DECLINED["real_harm"], meta=usage.meta())
            kind: Literal["verdict", "contempt"]
            facts: dict[str, str | list[str]]  # neutral facts, never the visitor's words
            if analysis.scope == "not_a_grievance":  # the petition itself is the offense
                kind, prompt, facts = "contempt", CONTEMPT_PROMPT, {"offense": analysis.offense}
                candidates = self._contempt_laws(case)
            else:
                kind, prompt = "verdict", VERDICT_PROMPT
                facts = {"case": analysis.summary, "details": analysis.details}
                region = None if case.jurisdiction == "any" else case.jurisdiction
                hits = self.index.search(analysis.search_query, case.themes, region)
                candidates = pick_for_outrage(hits, case.outrage)
            if not candidates:
                reason = "not_a_grievance" if kind == "contempt" else "no_law"
                return Ruling(kind="declined", message=DECLINED[reason], meta=usage.meta())
            draft = self._deliberate(prompt, facts, case, candidates, usage)
        except LLMUnavailable as err:
            raise TribunalUnavailable(str(err), err.retry_after) from err
        except SearchUnavailable as err:
            raise TribunalUnavailable(str(err)) from err
        law = next(hit.law for hit in candidates if hit.law.law_id == draft.law_id)
        return Ruling(
            kind=kind,
            verdict=draft,
            law=CitedLaw(**law.model_dump()),
            meta={"prompt": VERDICT_PROMPT, "trace_id": trace_id() or ""},
        )

    @observe()
    def _analyze(self, case: Case, usage: Usage) -> Analysis:
        def has_query(analysis: Analysis) -> None:
            if analysis.scope == "petty" and not analysis.search_query.strip():
                raise ValueError("search_query is required when scope is petty")
            if analysis.scope == "not_a_grievance" and not analysis.offense.strip():
                raise ValueError("offense is required when scope is not_a_grievance")

        user = json.dumps({"grievance": case.crime})
        return self.llm.complete_json(
            Analysis, prompts.load(ANALYSIS_PROMPT), user, check=has_query, usage=usage
        )

    def _contempt_laws(self, case: Case) -> list[Hit]:
        """Laws about conduct before a court: from the chosen themes if any, else from all."""
        for themes in (case.themes, None):
            hits = self.index.search(CONTEMPT_QUERY, themes, None, limit=20)
            hits = [hit for hit in hits if CONTEMPT & set(hit.law.categories)]
            if hits:
                return pick_for_outrage(hits, case.outrage)
        return []

    @observe()
    def _deliberate(
        self, prompt: str, facts: dict, case: Case, candidates: list[Hit], usage: Usage
    ) -> Draft:
        allowed = [hit.law.law_id for hit in candidates]

        def cites_a_candidate(draft: Draft) -> None:
            if draft.law_id not in allowed:
                raise ValueError(f"law_id must be one of {allowed}")

        laws = [
            {
                "law_id": hit.law.law_id,
                "theme": hit.law.theme,
                "jurisdiction": hit.law.jurisdiction_name,
                "citation": hit.law.citation,
                "text": hit.law.text,
                "verbatim": hit.law.verbatim,
                "punishment": hit.law.punishment,
                "tier": hit.law.tier,
            }
            for hit in candidates
        ]
        # Only the analysis's neutral facts reach the judge, never the visitor's own words.
        user = json.dumps({**facts, "outrage_dial": case.outrage, "laws": laws})
        return self.llm.complete_json(
            Draft,
            prompts.load(prompt),
            user,
            tier="smart",
            temperature=0.8,
            check=cites_a_candidate,
            usage=usage,
        )


def pick_for_outrage(
    hits: list[Hit], outrage: int, keep: int = 4, weight: float = 0.5
) -> list[Hit]:
    """Order laws by relevance minus distance from the Outrage Dial, best first.

    Hit scores are cross-encoder logits; the sigmoid turns them into 0..1 relevance that
    can be mixed with tier distance (also 0..1). A law that states no punishment counts
    as far from every dial setting, so it's chosen only when nothing better fits.
    """

    def value(hit: Hit) -> float:
        relevance = 1 / (1 + math.exp(-max(-30.0, min(30.0, hit.score))))
        distance = abs(hit.law.tier - outrage) / 4 if hit.law.tier else 1.0
        return relevance - weight * distance

    return sorted(hits, key=value, reverse=True)[:keep]
