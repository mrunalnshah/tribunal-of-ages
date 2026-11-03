"""Manual check of the LLM client: uv run python scripts/try_llm.py"""

import logging

from pydantic import BaseModel

from tribunal.config import Settings
from tribunal.llm import LLMClient

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)  # hide per-request lines


class Joke(BaseModel):
    setup: str
    punchline: str


llm = LLMClient(Settings().providers())
system = 'Reply with JSON only: {"setup": "...", "punchline": "..."}'
print(llm.complete_json(Joke, system, "A one-liner about the Code of Hammurabi"))
