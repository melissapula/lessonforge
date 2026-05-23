"""
schemas.py
==========
Every AI step in this project returns STRUCTURED DATA, not free-form prose.
That is the single most important discipline in agentic engineering: if the
output of one node is going to feed the next, it must have a known, validated
shape. We use Pydantic models as those contracts.

We also define the graph's shared State here. In LangGraph, a single state
object flows through every node; each node reads from it and returns a partial
update that gets merged back in. Think of it as the data that travels the
length of the pipeline, picking up more fields as it goes.
"""

from __future__ import annotations
from typing import Literal, Optional
from pydantic import BaseModel, Field
from typing_extensions import TypedDict


# ---------------------------------------------------------------------------
# Structured outputs produced BY the AI nodes.
# Each model is a "contract": the model is told to return JSON matching this,
# and we validate the response against it. A mismatch is a bug we catch early,
# not a surprise three nodes later.
# ---------------------------------------------------------------------------

class Example(BaseModel):
    """A single worked example inside the instructional content."""
    prompt: str = Field(description="The example problem or question posed to the student.")
    solution: str = Field(description="A clear, step-by-step solution a student could follow.")


class LessonContent(BaseModel):
    """Output of node 1 (draft_lesson). The core instructional material."""
    explanation: str = Field(description="A concise instructional explanation of the concept, written at the target grade level.")
    worked_examples: list[Example] = Field(description="2-3 worked examples that demonstrate the concept.")
    extension_activity: str = Field(description="An 'aspire-to' activity for students who finish early — the differentiation piece.")


class CheckQuestion(BaseModel):
    """A single mastery-check question with its answer key."""
    question: str
    answer: str = Field(description="The correct answer.")
    rationale: str = Field(description="One line explaining why this is correct — helps the teacher grade quickly.")


class MasteryCheck(BaseModel):
    """Output of node 2 (generate_mastery_check)."""
    questions: list[CheckQuestion] = Field(description="3-5 questions that verify the objective is met.")


class Check(BaseModel):
    """One dimension of the quality report."""
    passed: bool
    critique: str = Field(description="If failed, what's wrong and how to fix it. If passed, a brief note.")


class QualityReport(BaseModel):
    """
    Output of node 3 (quality_gate). The graph routes on these results:
    if anything failed (and we haven't exhausted revisions), we loop back.
    """
    alignment: Check = Field(description="Does the lesson actually teach the stated objective?")
    reading_level: Check = Field(description="Is the language appropriate for the target grade level?")
    check_validity: Check = Field(description="Does the mastery check genuinely test the objective?")

    @property
    def all_passed(self) -> bool:
        return self.alignment.passed and self.reading_level.passed and self.check_validity.passed


class FinalLesson(BaseModel):
    """Output of node 4 (finalize). The assembled, teacher-approved lesson."""
    title: str
    lesson: LessonContent
    mastery_check: MasteryCheck


# ---------------------------------------------------------------------------
# The graph's shared State.
#
# NOTE on TypedDict vs Pydantic: LangGraph wants its state as a TypedDict (or
# dataclass). The Pydantic models above are the *contents* of individual
# fields. So the state is a TypedDict whose fields are typed with our Pydantic
# models. Best of both worlds: LangGraph-friendly container, validated payloads.
# ---------------------------------------------------------------------------

class LessonState(TypedDict):
    # --- Inputs: set once when the graph is invoked ---
    objective: str
    grade_level: str
    subject: str

    # --- Produced by nodes as the state travels through the graph ---
    lesson: Optional[LessonContent]
    mastery_check: Optional[MasteryCheck]
    quality_report: Optional[QualityReport]
    revision_count: int           # how many times the quality loop has fired

    # --- Set at the human-in-the-loop interrupt ---
    teacher_decision: Optional[Literal["approve", "revise", "reject"]]
    teacher_notes: Optional[str]

    # --- Final ---
    final_lesson: Optional[FinalLesson]


# Subject options — kept here so the frontend dropdown and the backend agree.
SUBJECTS = ["Math", "ELA", "Science", "Social Studies", "Music", "Other"]

# How many automatic quality-revision loops before we give up and show the
# teacher the flawed draft anyway. This is the "completion promise" of the
# small RALPH loop in the quality gate: stop when quality passes OR we hit this.
MAX_QUALITY_REVISIONS = 2
