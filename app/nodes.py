"""
nodes.py
========
The four nodes of the graph. A "node" is just a function:

    def node(state: LessonState) -> dict:
        ...
        return {"some_field": new_value}

It receives the full shared state, does its work, and returns a PARTIAL update
— a dict of just the fields it changed. LangGraph merges that back into the
state before the next node runs. You never mutate state in place; you return
what changed.

Each node here calls the model via generate_structured() and gets back a
validated Pydantic object, which it stores in state for the next node to use.
"""

from __future__ import annotations
from .schemas import (
    LessonState, LessonContent, MasteryCheck, QualityReport, FinalLesson,
)
from .llm import generate_structured


# ---------------------------------------------------------------------------
# NODE 1 — draft_lesson
# ---------------------------------------------------------------------------
def draft_lesson(state: LessonState) -> dict:
    """Turn the objective into instructional content + an extension activity.

    On a teacher-requested revision, `teacher_notes` will be present and we fold
    it into the prompt so the redraft actually responds to the feedback.
    """
    notes = state.get("teacher_notes")
    revision_hint = (
        f"\n\nThe teacher reviewed a previous draft and asked for changes: "
        f"\"{notes}\". Address this in the new draft."
        if notes else ""
    )

    user = (
        f"Create a self-paced lesson for this learning objective.\n"
        f"Objective: {state['objective']}\n"
        f"Grade level: {state['grade_level']}\n"
        f"Subject: {state['subject']}"
        f"{revision_hint}"
    )

    lesson = generate_structured(
        system=(
            "You are an expert curriculum designer working in the Modern Classrooms "
            "self-paced, mastery-based model. Write clear, grade-appropriate "
            "instruction. The extension activity should genuinely stretch students "
            "who finish early."
        ),
        user=user,
        schema=LessonContent,
    )
    # Clear teacher_notes once consumed, so a later automatic loop doesn't re-apply it.
    return {"lesson": lesson, "teacher_notes": None}


# ---------------------------------------------------------------------------
# NODE 2 — generate_mastery_check
# ---------------------------------------------------------------------------
def generate_mastery_check(state: LessonState) -> dict:
    """Produce the mastery check that verifies the objective is met.

    If the quality gate sent us back here, `quality_report` holds the critique;
    we inject it so the regenerated check fixes the specific problem.
    """
    report = state.get("quality_report")
    critique_hint = ""
    if report and not report.check_validity.passed:
        critique_hint = (
            f"\n\nA previous mastery check was rejected for this reason: "
            f"\"{report.check_validity.critique}\". Fix it."
        )

    user = (
        f"Write a mastery check for this lesson.\n"
        f"Objective: {state['objective']}\n"
        f"Grade level: {state['grade_level']}\n"
        f"Lesson explanation: {state['lesson'].explanation}"
        f"{critique_hint}"
    )

    check = generate_structured(
        system=(
            "You write mastery checks: 3-5 questions that confirm a student has "
            "actually met the objective. Each question needs a correct answer and "
            "a one-line rationale."
        ),
        user=user,
        schema=MasteryCheck,
    )
    return {"mastery_check": check}


# ---------------------------------------------------------------------------
# NODE 3 — quality_gate
# ---------------------------------------------------------------------------
def quality_gate(state: LessonState) -> dict:
    """Score the draft against a rubric. This node only PRODUCES the report;
    the ROUTING decision (loop back vs continue) lives in graph.py as a
    conditional edge. Keeping 'scoring' and 'routing' separate keeps each
    piece simple.
    """
    lesson = state["lesson"]
    check = state["mastery_check"]

    user = (
        f"Evaluate this lesson and mastery check against the objective.\n\n"
        f"Objective: {state['objective']}\n"
        f"Grade level: {state['grade_level']}\n\n"
        f"Lesson explanation: {lesson.explanation}\n"
        f"Extension: {lesson.extension_activity}\n\n"
        f"Mastery check questions: "
        f"{[q.question for q in check.questions]}\n\n"
        f"Score three things, each pass/fail with a critique: "
        f"(1) alignment — does the lesson teach the objective? "
        f"(2) reading_level — is the language right for {state['grade_level']}? "
        f"(3) check_validity — does the mastery check truly test the objective?"
    )

    report = generate_structured(
        system=(
            "You are a meticulous instructional-quality reviewer. Be honest: if "
            "something is off, fail it and say precisely why. Passing weak work "
            "helps no one."
        ),
        user=user,
        schema=QualityReport,
    )
    return {"quality_report": report}


# ---------------------------------------------------------------------------
# NODE 4 — finalize
# ---------------------------------------------------------------------------
def finalize(state: LessonState) -> dict:
    """Assemble the approved pieces into the final lesson. No model call needed
    for the body — but we do ask for a nice title. (You could skip the call and
    template a title; calling the model keeps it simple and flexible.)"""
    title_holder = generate_structured(
        system="You write short, clear lesson titles.",
        user=(
            f"Give a concise lesson title for objective: {state['objective']} "
            f"({state['grade_level']} {state['subject']}). "
            f"Return it as the FinalLesson with the provided lesson and mastery_check."
        ),
        # We only really need the title; reuse FinalLesson and overwrite the
        # nested objects with the already-approved ones below to be safe.
        schema=FinalLesson,
        max_tokens=2500,
    )
    final = FinalLesson(
        title=title_holder.title,
        lesson=state["lesson"],
        mastery_check=state["mastery_check"],
    )
    return {"final_lesson": final}
