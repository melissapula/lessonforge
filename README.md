# LessonForge

**An agentic, human-in-the-loop generator for self-paced, mastery-based lessons.**

A teacher enters a learning objective, a grade level, and a subject. An
orchestrated graph of AI steps drafts the instruction, generates a mastery
check, scores its own work against a rubric, and **pauses for the teacher to
approve, edit, or reject** before anything is finalized. No AI-generated content
is ever treated as final without a human in the loop.

Built around the [Modern Classrooms](https://www.modernclassrooms.org/)
self-paced, mastery-based instructional model.

> The full design contract lives in [`SPEC.md`](./SPEC.md), written **before**
> the implementation — this project follows spec-driven development.

---

## Architecture

```
draft_lesson
     │
     ▼
generate_mastery_check ◄──────────────┐  (revise: quality fail, < 2 revisions)
     │                                │
     ▼                                │
quality_gate ─────────────────────────┘
     │ (pass, or revisions exhausted)
     ▼
teacher_review   ⏸  HUMAN-IN-THE-LOOP INTERRUPT
     │
     ├── approve ──► finalize ──► END
     ├── revise ───► draft_lesson (with the teacher's notes)
     └── reject ───► END
```

A single shared **state** object flows through every node, picking up fields as
it goes. The graph is built with [LangGraph](https://langchain-ai.github.io/langgraph/).

### Key engineering patterns

| Pattern | Where it lives |
|---|---|
| Graph-based orchestration: nodes + conditional edges | `app/graph.py` |
| Structured outputs (validated JSON, not prose) | `app/schemas.py`, `app/llm.py` |
| Human-in-the-loop interrupt / circuit breaker | `interrupt_before=["teacher_review"]` in `app/graph.py` |
| Durable execution (state survives restarts) | SQLite checkpointer in `app/run.py` |
| Self-correcting quality loop with a bounded completion promise | `route_after_quality` in `app/graph.py` |
| Evaluation harness over a pinned dataset | `evals/` |
| Provider-agnostic model seam | `app/llm.py` (one `MODEL` constant) |

---

## Setup

Requires Python 3.10+.

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-...     # Windows: set ANTHROPIC_API_KEY=sk-...
```

> Check the current model name in the Anthropic docs and update `MODEL` in
> `app/llm.py` if needed before your first run.

## Run the headless pipeline

```bash
python -m app.run
```

You'll be prompted for an objective, grade, and subject. Watch each node
complete, see the draft + quality report, then make the approve/revise/reject
decision. This is the core agentic engine end to end, including the real
interrupt-and-resume cycle.

## Run the evals

```bash
python -m evals.run_evals
```

Runs the graph up to the interrupt for each pinned objective in
`evals/dataset.json` and prints a pass/fail table. Rerun after editing a prompt
to catch regressions.

---

## Project layout

```
lessonforge/
├── SPEC.md                  # the design contract (written first)
├── README.md
├── requirements.txt
├── app/
│   ├── schemas.py           # Pydantic output contracts + graph state
│   ├── llm.py               # structured-output model wrapper (provider seam)
│   ├── nodes.py             # the four pipeline steps
│   ├── graph.py             # LangGraph wiring: edges, RALPH loop, interrupt
│   └── run.py               # headless CLI driver
└── evals/
    ├── dataset.json         # pinned objectives across subjects/grades
    └── run_evals.py         # the eval harness
```

---

## Roadmap

- **Angular + RxJS frontend** — input view, live progress stream, review panel,
  final lesson with export. (The backend is structured so the FastAPI layer
  streams progress events the UI subscribes to.)
- **Cross-provider benchmark** — a second model behind the same `generate_structured`
  seam, with the eval harness reporting cost / latency / pass-rate.
- **LMS integrations** — export to Google Classroom / Canvas.
- **Unit sequencing** — chain multiple lessons into a self-paced unit.
```
