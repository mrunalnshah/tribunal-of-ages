"""Tracing that works with or without Langfuse, and never records what anyone wrote.

With LANGFUSE_PUBLIC_KEY set, @observe() records each decorated call as a span, and OpenAI()
returns Langfuse's drop-in client, which records every LLM call. Spans keep their timing,
nesting, model, token counts and errors, but none of their content: decorated calls capture
no arguments or results, and before anything is exported, every span attribute that could
hold a prompt, an answer or metadata is deleted. Without the key, every name here is a
harmless stand-in, so no other module ever has to ask whether tracing is on.
"""

import os
import re
from collections.abc import Callable, Mapping
from typing import Any, cast

import openai

ENABLED = bool(os.getenv("LANGFUSE_PUBLIC_KEY"))
# Span attributes that can carry someone's words: inputs, outputs, prompts, completions and
# metadata. Timings, model names and token counts live in other attributes, and stay.
CONTENT = re.compile(
    r"^(langfuse\.(trace|observation)\.(input|output|metadata)"
    r"|gen_ai\.(prompt|completion|input\.messages|output\.messages|system_instructions))(\.|$)"
)

__all__ = ["OpenAI", "content_attributes", "flush", "observe", "score", "trace_id"]


def content_attributes(attributes: Mapping[str, object]) -> tuple[str, ...]:
    """The keys in `attributes` that could hold someone's words, so must never leave."""
    return tuple(key for key in attributes if CONTENT.match(key))


def _mask_otel_spans(*, params: Any) -> Any:
    """Langfuse's export hook: delete content attributes from every span before export."""
    from langfuse.types import MaskOtelSpansResult, OtelSpanPatch

    patches = {}
    for identifier, span in params.spans.items():
        if found := content_attributes(span.attributes):
            patches[identifier] = OtelSpanPatch(delete_attributes=found)
    return MaskOtelSpansResult(span_patches=patches)


if ENABLED:  # one client for the whole process, configured before anything is traced
    from langfuse import Langfuse

    Langfuse(mask_otel_spans=_mask_otel_spans)


def OpenAI(**options: Any) -> openai.OpenAI:
    """The OpenAI client or, with tracing on, Langfuse's version that records every call.

    It's named like the class it stands in for, so llm.py reads the same either way.
    """
    if ENABLED:
        from langfuse.openai import OpenAI as TracedOpenAI

        return cast(openai.OpenAI, TracedOpenAI(**options))
    return openai.OpenAI(**options)


def observe[F: Callable[..., Any]](**options: Any) -> Callable[[F], F]:
    """Langfuse's @observe(), without arguments or results; with tracing off, a no-op."""
    if ENABLED:
        from langfuse import observe as traced

        options = {"capture_input": False, "capture_output": False, **options}
        return cast(Callable[[F], F], traced(**options))
    return _unchanged


def _unchanged[F](function: F) -> F:
    return function


def trace_id() -> str | None:
    """The ID of the current request's trace, or None when tracing is off."""
    if not ENABLED:
        return None
    from langfuse import get_client

    return get_client().get_current_trace_id()


def score(trace: str, value: float) -> None:
    """Attach a visitor's thumbs-up (1) or thumbs-down (-1) to a trace."""
    if ENABLED:
        from langfuse import get_client

        get_client().create_score(trace_id=trace, name="user_feedback", value=value)


def flush() -> None:
    """Send buffered traces before the process exits."""
    if ENABLED:
        from langfuse import get_client

        get_client().flush()
