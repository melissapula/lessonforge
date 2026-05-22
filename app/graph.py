"""
graph.py
========
This is where the pipeline becomes a GRAPH. Three concepts to understand:

1. EDGES connect nodes. A plain edge ("after A, always do B") is unconditional.
   A CONDITIONAL edge runs a function that looks at the state and decides which
   node to go to next. That's how branching and loops happen.

2. The CONDITIONAL EDGE after quality_gate is our small RALPH loop:
       quality passed?            -> go to the teacher interrupt
       failed, revisions left?    -> loop back to generate_mastery_check
       failed, revisions used up? -> go to the interrupt anyway (show the flaws)
   The "completion promise" — the rule that guarantees the loop ends — is
   MAX_QUALITY_REVISIONS. Without a bound, an autonomous loop can run forever.

3. The INTERRUPT is the human-in-the-loop checkpoint. We compile the graph with
   `interrupt_before=["teacher_review"]`, which tells LangGraph: pause and save
   state BEFORE running that node, and wait. The outside world (a script, or the
   API) inspects the paused state, collects the teacher's decision, writes it
   into state, and resumes. Because we attach a CHECKPOINTER, that paused state
   is persisted — the graph can resume even after the process restarts. That's
   durable execution in miniature.
"""

from __future__ import annotations
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.sqlite import SqliteSaver

from .schemas import LessonState, MAX_QUALITY_REVISIONS
from .nodes import (
    draft_lesson, generate_mastery_check, quality_gate, finalize,
)


# ---------------------------------------------------------------------------
# The teacher_review node is intentionally a NO-OP.
# The real work (collecting the teacher's choice) happens OUTSIDE the graph,
# during the interrupt pause. By the time this node actually runs on resume,
# state["teacher_decision"] has already been set by the caller. We then route
# on it. Keeping the node empty makes the interrupt boundary crystal clear.
# ---------------------------------------------------------------------------
def teacher_review(state: LessonState) -> dict:
    return {}


# --- Conditional edge functions: they RETURN THE NAME of the next node ---

def route_after_quality(state: LessonState) -> str:
    """The RALPH loop's routing logic."""
    report = state["quality_report"]
    if report.all_passed:
        return "teacher_review"
    if state["revision_count"] < MAX_QUALITY_REVISIONS:
        return "revise"        # mapped to generate_mastery_check below
    return "teacher_review"    # revisions exhausted — let the human decide


def route_after_review(state: LessonState) -> str:
    """Branch on the teacher's decision collected during the interrupt."""
    decision = state["teacher_decision"]
    if decision == "approve":
        return "finalize"
    if decision == "revise":
        return "redraft"       # mapped to draft_lesson below
    return END                 # reject -> stop with no final lesson


def _bump_revision(state: LessonState) -> dict:
    """Tiny helper node: increment the counter when we loop back for quality.
    Splitting this out keeps the counter logic in one obvious place."""
    return {"revision_count": state["revision_count"] + 1}


def build_graph(checkpointer):
    """Assemble and compile the graph. Pass in a checkpointer instance so the
    caller controls persistence (a file for real runs, in-memory for tests)."""
    g = StateGraph(LessonState)

    # Register nodes
    g.add_node("draft_lesson", draft_lesson)
    g.add_node("generate_mastery_check", generate_mastery_check)
    g.add_node("bump_revision", _bump_revision)
    g.add_node("quality_gate", quality_gate)
    g.add_node("teacher_review", teacher_review)
    g.add_node("finalize", finalize)

    # Linear spine: start -> draft -> mastery check -> quality gate
    g.set_entry_point("draft_lesson")
    g.add_edge("draft_lesson", "generate_mastery_check")
    g.add_edge("generate_mastery_check", "quality_gate")

    # Conditional edge: the RALPH loop. Map the routing function's return
    # values to actual node names.
    g.add_conditional_edges(
        "quality_gate",
        route_after_quality,
        {
            "teacher_review": "teacher_review",
            "revise": "bump_revision",   # bump the counter, then regenerate
        },
    )
    g.add_edge("bump_revision", "generate_mastery_check")

    # Conditional edge after the human interrupt.
    g.add_conditional_edges(
        "teacher_review",
        route_after_review,
        {
            "finalize": "finalize",
            "redraft": "draft_lesson",
            END: END,
        },
    )
    g.add_edge("finalize", END)

    # interrupt_before pauses execution right before teacher_review runs,
    # persisting state via the checkpointer. This is the human-in-the-loop
    # circuit breaker.
    return g.compile(checkpointer=checkpointer, interrupt_before=["teacher_review"])


def fresh_state(objective: str, grade_level: str, subject: str) -> LessonState:
    """Build a starting state with all the produced/decision fields empty."""
    return LessonState(
        objective=objective,
        grade_level=grade_level,
        subject=subject,
        lesson=None,
        mastery_check=None,
        quality_report=None,
        revision_count=0,
        teacher_decision=None,
        teacher_notes=None,
        final_lesson=None,
    )
