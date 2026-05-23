"""
llm.py
======
A thin wrapper around the model call. Two jobs:

1. STRUCTURED OUTPUT. We ask the model to return JSON only, then validate it
   against a Pydantic schema. If validation fails, we retry once with the
   error fed back in. This is how you turn an LLM's free-form text into a
   reliable data source for the next node.

2. PROVIDER-AGNOSTIC SEAM. The rest of the code never imports the Anthropic
   SDK directly — it calls `generate_structured(...)`. The model name lives in
   ONE constant. That's what makes the "cross-provider benchmark" stretch goal
   cheap later: add a second implementation behind the same function signature.

You'll need: pip install anthropic pydantic
And an API key in your environment: export ANTHROPIC_API_KEY=sk-...
"""

from __future__ import annotations
import json
import os
from typing import Type, TypeVar
from pydantic import BaseModel, ValidationError

# The ONE place the provider/model is named. Swap here, or add a branch for a
# second provider when you build the benchmark.
MODEL = "claude-sonnet-4-6"  # check current model names in Anthropic docs when you run this

T = TypeVar("T", bound=BaseModel)


def _client():
    """Lazily construct the Anthropic client so importing this module doesn't
    require the key to be set (handy for tests that don't hit the API)."""
    from anthropic import Anthropic
    return Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])


def generate_structured(
    system: str,
    user: str,
    schema: Type[T],
    max_tokens: int = 2000,
) -> T:
    """
    Call the model and return an instance of `schema`, validated.

    `schema` is a Pydantic model class. We hand the model its JSON schema and
    instruct it to return ONLY matching JSON. We then parse + validate. One
    retry on failure, with the validation error injected so the model can fix
    its own mistake — a tiny self-correction loop.
    """
    # Pydantic can emit a JSON schema describing exactly the shape we want.
    json_schema = json.dumps(schema.model_json_schema(), indent=2)

    full_system = (
        f"{system}\n\n"
        f"You MUST respond with ONLY a JSON object matching this schema. "
        f"No prose, no markdown fences, no commentary — JSON only.\n\n"
        f"Schema:\n{json_schema}"
    )

    client = _client()
    messages = [{"role": "user", "content": user}]

    last_error = None
    for attempt in range(2):  # initial try + one retry
        resp = client.messages.create(
            model=MODEL,
            max_tokens=max_tokens,
            system=full_system,
            messages=messages,
        )
        text = resp.content[0].text.strip()

        # Models sometimes wrap JSON in ```json fences despite instructions.
        # Strip them defensively.
        text = text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()

        try:
            data = json.loads(text)
            return schema.model_validate(data)  # validates against the contract
        except (json.JSONDecodeError, ValidationError) as e:
            last_error = e
            # Feed the failure back so the model can correct on the retry.
            messages.append({"role": "assistant", "content": text})
            messages.append({
                "role": "user",
                "content": f"That did not validate against the schema. Error:\n{e}\n"
                           f"Return corrected JSON only.",
            })

    raise RuntimeError(f"Model failed to produce valid {schema.__name__} after retry: {last_error}")
