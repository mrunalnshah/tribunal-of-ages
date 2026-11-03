"""All runtime settings, read from environment variables (12-factor style).

Only the entry points (cli.py and api.py) create Settings; every other module receives
plain values as arguments, so modules stay testable without any environment setup.
"""

import os
import tomllib
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict
from pydantic_settings import BaseSettings

from tribunal.llm import Provider

PAID = {"cases": 1_000, "tokens": 2_500_000}  # Groq's Developer tier: about $0.60 a day at most
FREE_CASES = 150  # when no configured provider says what it can serve for free
TOKENS_PER_CASE = 2_400  # the free plan's token budget: its cases at a little over the average


class ProviderEntry(BaseModel):
    """One [[provider]] in providers.toml: an OpenAI-compatible API to fall back to."""

    model_config = ConfigDict(extra="forbid")  # a misspelled key is an error, not ignored

    name: str
    base_url: str  # may name environment variables, like ${CLOUDFLARE_ACCOUNT_ID}
    api_key_env: str  # the environment variable that holds its key
    fast_model: str
    smart_model: str
    reasoning_effort: str | None = None
    cap_field: str = "max_completion_tokens"
    cases_per_day: int = 0


class Settings(BaseSettings):
    # LLM providers, in fallback order. A provider is used only if its key or URL is set.
    groq_api_key: str = ""
    groq_fast_model: str = "openai/gpt-oss-20b"
    groq_smart_model: str = "openai/gpt-oss-120b"
    gemini_api_key: str = ""
    gemini_fast_model: str = "gemini-flash-lite-latest"
    gemini_smart_model: str = "gemini-flash-latest"
    ollama_url: str = ""  # e.g. http://localhost:11434/v1 for local development
    ollama_model: str = "llama3.2"
    llm_timeout: float = 30.0
    groq_spare: bool = True  # Groq's free limits are per model: when one runs out, try the other
    max_output_tokens_fast: int = 700  # caps on each answer, reasoning included
    max_output_tokens_smart: int = 1_200
    providers_file: str = "providers.toml"  # extra providers, tried after Groq (Step 16)
    estimated_answer_tokens: int = 800  # what a chatbot's answer might cost: an assumption

    # Search
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str = ""
    collection: str = "laws"
    model_cache: str = ".cache/models"
    catalog_path: str = "data/processed/catalog.json"  # written by `tribunal curate`

    # API protection. PLAN picks the daily budgets; DAILY_BUDGET and TOKEN_BUDGET override them.
    plan: Literal["free", "paid"] = "free"
    allowed_origins: list[str] = ["http://localhost:5500", "http://127.0.0.1:5500"]
    requests_per_minute: int = 5
    visitor_daily_limit: int = 7  # cases one visitor may file a day
    daily_budget: int | None = None  # cases a day, for everyone
    token_budget: int | None = None  # LLM tokens a day, for everyone
    max_body_bytes: int = 32_768  # a bigger request is refused before it's read

    # The public record (Step 14). Empty means off; sqlite:///data/records.db works locally,
    # and production uses Postgres: Neon's connection string.
    database_url: str = ""
    record_report_limit: int = 3  # reports that hide a case until you review it

    @property
    def cases_per_day(self) -> int:
        """Most cases the court hears in a day: DAILY_BUDGET, or the plan's. On the free plan,
        that's what the configured providers can serve for free, added up."""
        if self.daily_budget is not None:
            return self.daily_budget
        if self.plan == "paid":
            return PAID["cases"]
        return sum(provider.cases_per_day for provider in self.providers()) or FREE_CASES

    @property
    def tokens_per_day(self) -> int:
        if self.token_budget is not None:
            return self.token_budget
        return PAID["tokens"] if self.plan == "paid" else self.cases_per_day * TOKENS_PER_CASE

    def providers(self) -> list[Provider]:
        providers = []
        if self.groq_api_key:
            providers.append(
                Provider(
                    name="groq",
                    base_url="https://api.groq.com/openai/v1",
                    api_key=self.groq_api_key,
                    fast_model=self.groq_fast_model,
                    smart_model=self.groq_smart_model,
                    reasoning_effort="low",
                    cases_per_day=75,  # both models' free tokens serve about 150 cases a day
                )
            )
            if self.groq_spare:  # the same models, swapped: each tier's second chance
                providers.append(
                    Provider(
                        name="groq-spare",
                        base_url="https://api.groq.com/openai/v1",
                        api_key=self.groq_api_key,
                        fast_model=self.groq_smart_model,
                        smart_model=self.groq_fast_model,
                        reasoning_effort="low",
                        cases_per_day=75,
                    )
                )
        providers += _extra_providers(Path(self.providers_file))
        if self.gemini_api_key:
            providers.append(
                Provider(
                    name="gemini",
                    base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
                    api_key=self.gemini_api_key,
                    fast_model=self.gemini_fast_model,
                    smart_model=self.gemini_smart_model,
                )
            )
        if self.ollama_url:
            providers.append(
                Provider(
                    name="ollama",
                    base_url=self.ollama_url,
                    api_key="ollama",  # Ollama ignores the key, but the SDK requires one
                    fast_model=self.ollama_model,
                    smart_model=self.ollama_model,
                )
            )
        return providers


def _extra_providers(path: Path) -> list[Provider]:
    """The [[provider]] entries in providers.toml whose key, and every ${VARIABLE} in whose
    address, is set in this environment, in the file's order."""
    if not path.exists():
        return []
    found = []
    for raw in tomllib.loads(path.read_text(encoding="utf-8")).get("provider", []):
        entry = ProviderEntry(**raw)
        key, base_url = os.environ.get(entry.api_key_env, ""), os.path.expandvars(entry.base_url)
        if key and "$" not in base_url:  # configured here
            found.append(
                Provider(
                    name=entry.name,
                    base_url=base_url,
                    api_key=key,
                    fast_model=entry.fast_model,
                    smart_model=entry.smart_model,
                    reasoning_effort=entry.reasoning_effort,
                    cap_field=entry.cap_field,
                    cases_per_day=entry.cases_per_day,
                )
            )
    return found
