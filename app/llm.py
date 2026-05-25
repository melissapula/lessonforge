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
import re
import time
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


# ---------------------------------------------------------------------------
# Mock mode. Set LESSONFORGE_MOCK=1 in .env to bypass the Anthropic API and
# return canned, schema-valid responses. Useful for UI/design-system work when
# you don't want to spend API credits. See _mock_response below.
# ---------------------------------------------------------------------------
_MOCK_LESSONS = {
    "math": {
        "explanation": (
            "To add fractions with the same denominator, keep the denominator the same "
            "and add the numerators. For example, 1/5 + 2/5 = 3/5. The bottom number "
            "(denominator) tells us the size of the pieces; the top number (numerator) "
            "tells us how many pieces we have."
        ),
        "worked_examples": [
            {"prompt": "What is 2/7 + 3/7?",
             "solution": "Keep 7 as the denominator. Add numerators: 2 + 3 = 5. Answer: 5/7."},
            {"prompt": "Sara ate 1/8 of a pizza and her brother ate 4/8. How much did they eat in total?",
             "solution": "Both fractions share the denominator 8. Add the numerators: 1 + 4 = 5. Together they ate 5/8 of the pizza."},
        ],
        "extension_activity": (
            "Design a fraction word problem of your own where two siblings share a pizza and "
            "end up eating exactly 7/8 of it together. Show two different ways the slices could be split."
        ),
    },
    "ela": {
        "explanation": (
            "The main idea of a paragraph is what the paragraph is mostly about — the single "
            "most important point the author wants you to take away. Supporting details are "
            "the facts, examples, or descriptions that back up the main idea. A good test: if "
            "you removed a sentence and the paragraph still made its point, that sentence was a detail."
        ),
        "worked_examples": [
            {"prompt": "Read: 'Sea otters use rocks as tools. They float on their backs and balance a rock on their belly, then crack open shellfish against it.' What is the main idea?",
             "solution": "The main idea is that sea otters use rocks as tools. The second sentence is a supporting detail showing HOW they use them."},
            {"prompt": "Which sentence is most likely to be the main idea: (a) 'Bats hunt at night.' (b) 'Some bats can catch insects mid-air.' (c) 'Bats are remarkable hunters.'",
             "solution": "(c) is the main idea — it's the broad claim. (a) and (b) are specific details that support it."},
        ],
        "extension_activity": (
            "Find a short news article online. Underline the sentence you think is the main idea. "
            "Then write your own one-sentence summary that captures the same idea in different words."
        ),
    },
    "science": {
        "explanation": (
            "Photosynthesis is how plants make their own food. They take in carbon dioxide from the "
            "air through tiny holes in their leaves, draw up water from the soil through their roots, "
            "and use energy from sunlight to combine them into sugar (glucose) and oxygen. The sugar "
            "feeds the plant; the oxygen is released into the air for us to breathe."
        ),
        "worked_examples": [
            {"prompt": "Name the three ingredients a plant needs to perform photosynthesis.",
             "solution": "Carbon dioxide (from the air), water (from the soil), and sunlight (for energy)."},
            {"prompt": "Why might a plant kept in a dark closet eventually die, even with plenty of water?",
             "solution": "Without sunlight, the plant cannot perform photosynthesis. With no way to make sugar for energy, it eventually runs out of stored food and dies."},
        ],
        "extension_activity": (
            "Design an experiment to test whether the COLOR of light affects how well a plant grows. "
            "List your variables, what you would measure, and what result would prove your hypothesis."
        ),
    },
    "music": {
        "explanation": (
            "A scale is a sequence of notes that rise or fall in pitch in a specific pattern. The major "
            "scale follows the pattern whole-whole-half-whole-whole-whole-half (where 'whole' and 'half' "
            "describe the distance between notes). The C major scale uses only the white keys: "
            "C, D, E, F, G, A, B, C. Every major scale sounds bright and finished because it follows "
            "this same pattern, just starting from a different note."
        ),
        "worked_examples": [
            {"prompt": "Write out the C major scale, ascending.",
             "solution": "C, D, E, F, G, A, B, C."},
            {"prompt": "If you start a major scale on G, the seventh note has to be raised a half step (F-sharp instead of F). Why?",
             "solution": "Because the major scale pattern requires a whole step between the 6th and 7th notes, and a half step between the 7th and 8th. Using F-natural would break that pattern; F-sharp keeps it intact."},
        ],
        "extension_activity": (
            "Pick a starting note that isn't C. Work out the major scale that begins on that note by "
            "applying the whole-whole-half-whole-whole-whole-half pattern. Which keys had to be sharp or flat?"
        ),
    },
}

_MOCK_MASTERY_CHECK = {
    "questions": [
        {"question": "In your own words, restate the key idea from the lesson.",
         "answer": "Student paraphrase that captures the central concept introduced in the explanation.",
         "rationale": "Tests recall and comprehension of the core idea in the student's own words."},
        {"question": "Apply the concept from the lesson to a new example of your choosing.",
         "answer": "A correctly constructed example that uses the concept appropriately in a new context.",
         "rationale": "Demonstrates transfer — the student can apply the idea, not just recognize it."},
        {"question": "What is one common mistake someone might make with this concept, and how would you avoid it?",
         "answer": "A reasonable misconception (e.g. confusing main idea with topic) paired with a strategy to catch it.",
         "rationale": "Surfaces depth of understanding by asking the student to anticipate errors."},
    ],
}

_MOCK_QUALITY_REPORT = {
    "alignment": {"passed": True, "critique": "The lesson directly addresses the stated objective."},
    "reading_level": {"passed": True, "critique": "Language and sentence structure suit the target grade."},
    "check_validity": {"passed": True, "critique": "The mastery check questions genuinely probe the objective."},
}


def _pick_mock_subject(prompt: str) -> str:
    """Best-effort match the prompt's subject text to our canned lesson library."""
    p = prompt.lower()
    for key in ("music", "math", "ela", "science"):
        if key in p:
            return key
    return "math"


def _extract_objective(prompt: str) -> str:
    """Pull the objective out of the prompt so the mock title feels responsive."""
    m = re.search(r"Objective:\s*(.+)", prompt)
    return m.group(1).strip().rstrip(".") if m else "Today's Lesson"


def _mock_response(user: str, schema):
    """Return a canned, schema-valid object. Branches on schema name to stay
    decoupled from the schemas module."""
    name = schema.__name__
    if name == "LessonContent":
        return schema.model_validate(_MOCK_LESSONS[_pick_mock_subject(user)])
    if name == "MasteryCheck":
        return schema.model_validate(_MOCK_MASTERY_CHECK)
    if name == "QualityReport":
        return schema.model_validate(_MOCK_QUALITY_REPORT)
    if name == "FinalLesson":
        # The finalize node overwrites lesson/mastery_check with the approved
        # state objects, so the inner content here is filler — only `title` is
        # actually used downstream.
        subject = _pick_mock_subject(user)
        return schema.model_validate({
            "title": _extract_objective(user).title(),
            "lesson": _MOCK_LESSONS[subject],
            "mastery_check": _MOCK_MASTERY_CHECK,
        })
    raise RuntimeError(f"No mock response defined for schema {name!r}")


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
    # Mock mode short-circuits the API call. The small sleep keeps the SSE
    # progress events visibly streaming so the UI's loading states still show.
    if os.environ.get("LESSONFORGE_MOCK"):
        time.sleep(0.4)
        return _mock_response(user, schema)

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
