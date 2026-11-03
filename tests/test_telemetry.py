from tribunal.telemetry import content_attributes


def test_only_attributes_that_can_hold_words_are_deleted():
    attributes = {
        "langfuse.observation.input": '{"grievance": "He ate my pizza"}',
        "langfuse.observation.output": "A verdict",
        "langfuse.observation.metadata.case": "pizza",
        "langfuse.trace.input": "...",
        "gen_ai.prompt.0.content": "He ate my pizza",
        "gen_ai.completion.0.content": "Guilty",
        "gen_ai.input.messages": "[...]",
        "langfuse.observation.model.name": "openai/gpt-oss-120b",
        "langfuse.observation.usage_details": '{"input": 812}',
        "gen_ai.usage.input_tokens": 812,
        "langfuse.observation.level": "DEFAULT",
    }
    assert set(content_attributes(attributes)) == {
        "langfuse.observation.input",
        "langfuse.observation.output",
        "langfuse.observation.metadata.case",
        "langfuse.trace.input",
        "gen_ai.prompt.0.content",
        "gen_ai.completion.0.content",
        "gen_ai.input.messages",
    }
