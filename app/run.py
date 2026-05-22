"""
run.py
======
The headless driver — build-order item 1 + 2 from the spec. Run this from the
terminal to watch the whole graph execute, PAUSE at the teacher interrupt,
collect your decision, and resume. No web server, no frontend — just the core
agentic engine, which is the hard and impressive part.

Usage:
    export ANTHROPIC_API_KEY=sk-...
    python -m app.run

This demonstrates the interrupt/resume cycle explicitly so you can see exactly
how a human-in-the-loop checkpoint works under the hood.
"""

from __future__ import annotations
import sys
from langgraph.checkpoint.sqlite import SqliteSaver

from .graph import build_graph, fresh_state
from .schemas import SUBJECTS


def _print_draft(state: dict) -> None:
    """Show the teacher what the graph produced, so they can decide."""
    lesson = state["lesson"]
    check = state["mastery_check"]
    report = state["quality_report"]

    print("\n" + "=" * 70)
    print("DRAFT FOR REVIEW")
    print("=" * 70)
    print("\n-- Explanation --\n" + lesson.explanation)
    print("\n-- Worked examples --")
    for i, ex in enumerate(lesson.worked_examples, 1):
        print(f"  {i}. {ex.prompt}\n     -> {ex.solution}")
    print("\n-- Extension activity --\n" + lesson.extension_activity)
    print("\n-- Mastery check --")
    for i, q in enumerate(check.questions, 1):
        print(f"  {i}. {q.question}\n     answer: {q.answer}")
    print("\n-- Quality report --")
    for name, c in [
        ("alignment", report.alignment),
        ("reading level", report.reading_level),
        ("check validity", report.check_validity),
    ]:
        flag = "PASS" if c.passed else "FAIL"
        print(f"  [{flag}] {name}: {c.critique}")
    print("=" * 70)


def main() -> None:
    # A unique id ties together all the checkpoints for one lesson run. Reusing
    # the same id is what lets us resume the SAME paused graph. In a web app this
    # would be per-session; here we hardcode one.
    config = {"configurable": {"thread_id": "demo-lesson-1"}}

    # The checkpointer persists state to a SQLite file. Because state is on disk,
    # you could kill this process after the pause, rerun, and resume — that's the
    # durable-execution point. We use a context manager per the library API.
    with SqliteSaver.from_conn_string("lessonforge_state.db") as checkpointer:
        graph = build_graph(checkpointer)

        # --- Gather inputs ---
        print("LessonForge — self-paced lesson generator\n")
        objective = input("Learning objective: ").strip() or \
            "Identify the main idea of a paragraph"
        grade = input("Grade level (e.g. '3rd grade'): ").strip() or "3rd grade"
        print(f"Subjects: {', '.join(SUBJECTS)}")
        subject = input("Subject: ").strip() or "ELA"

        state = fresh_state(objective, grade, subject)

        # --- Run until the interrupt ---
        # .stream yields after each node so you can SEE the pipeline progress.
        print("\nRunning the graph...\n")
        for step in graph.stream(state, config):
            node_name = list(step.keys())[0]
            print(f"  [done] {node_name}")

        # Execution paused at interrupt_before=["teacher_review"]. Pull the
        # saved state back out to show the teacher.
        snapshot = graph.get_state(config)
        _print_draft(snapshot.values)

        # --- Collect the human decision ---
        decision = input("\nDecision — [a]pprove / [r]evise / re[j]ect: ").strip().lower()
        notes = None
        if decision.startswith("r") and not decision.startswith("re j"):
            mapped = "revise"
            notes = input("What should change? ").strip()
        elif decision.startswith("j"):
            mapped = "reject"
        else:
            mapped = "approve"

        # Write the decision INTO the paused state, then resume by streaming
        # again with `None` as input (None = "continue from where you paused").
        graph.update_state(config, {"teacher_decision": mapped, "teacher_notes": notes})

        print("\nResuming...\n")
        for step in graph.stream(None, config):
            node_name = list(step.keys())[0]
            print(f"  [done] {node_name}")

        # --- Show the result ---
        final = graph.get_state(config).values.get("final_lesson")
        if final:
            print("\n" + "#" * 70)
            print(f"FINAL LESSON: {final.title}")
            print("#" * 70)
            print(final.lesson.explanation)
        else:
            print("\nLesson was rejected — nothing finalized.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
