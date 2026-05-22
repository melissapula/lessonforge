"""
run_evals.py
============
A test suite for AI BEHAVIOR. The point is not a perfect automated grader — it's
to demonstrate that prompt changes are measured, not eyeballed. When you tweak a
prompt in nodes.py, rerun this and watch the pass/fail table to catch regressions.

It runs the graph up to (but NOT through) the human interrupt for each pinned
objective, then asserts the structural expectations from dataset.json.

Usage:
    export ANTHROPIC_API_KEY=sk-...
    python -m evals.run_evals
"""

from __future__ import annotations
import json
import os
from pathlib import Path
from langgraph.checkpoint.sqlite import SqliteSaver

from app.graph import build_graph, fresh_state


DATASET = Path(__file__).parent / "dataset.json"


def evaluate_entry(graph, config, entry: dict) -> dict:
    """Run one objective up to the interrupt and check expectations."""
    state = fresh_state(entry["objective"], entry["grade_level"], entry["subject"])

    # Stream until the graph pauses at the interrupt.
    for _ in graph.stream(state, config):
        pass

    values = graph.get_state(config).values
    check = values.get("mastery_check")
    lesson = values.get("lesson")
    exp = entry["expectations"]

    results = {}

    # Did we get the structured pieces at all?
    results["produced_lesson"] = lesson is not None
    results["produced_check"] = check is not None

    if check is not None:
        n = len(check.questions)
        results["question_count_in_range"] = (
            exp["min_questions"] <= n <= exp["max_questions"]
        )
    else:
        results["question_count_in_range"] = False

    if lesson is not None and exp.get("must_include_extension"):
        results["has_extension"] = bool(lesson.extension_activity.strip())
    else:
        results["has_extension"] = not exp.get("must_include_extension", False)

    return results


def main() -> None:
    entries = json.loads(DATASET.read_text())

    # In-memory checkpointer is fine for evals; each entry uses its own thread_id.
    with SqliteSaver.from_conn_string(":memory:") as checkpointer:
        graph = build_graph(checkpointer)

        print(f"\nRunning {len(entries)} eval cases...\n")
        all_pass = True
        rows = []
        for entry in entries:
            config = {"configurable": {"thread_id": f"eval-{entry['id']}"}}
            try:
                results = evaluate_entry(graph, config, entry)
            except Exception as e:
                results = {"error": str(e)}
            passed = all(v is True for v in results.values()) and "error" not in results
            all_pass = all_pass and passed
            rows.append((entry["id"], passed, results))

        # Print a simple table.
        for eid, passed, results in rows:
            flag = "PASS" if passed else "FAIL"
            print(f"[{flag}] {eid}")
            if not passed:
                for k, v in results.items():
                    if v is not True:
                        print(f"        - {k}: {v}")

        print(f"\n{'ALL PASSED' if all_pass else 'SOME FAILED'}")


if __name__ == "__main__":
    main()
