# SPEC: LessonForge — Self-Paced Lesson Generator

> A spec-driven-development document. Written before any code, this is the
> contract the implementation is built against. Update the spec first, then
> the code follows.

---

## 1. Context & Purpose

### What this is
LessonForge is an agentic web application that helps a teacher turn a single
learning objective into a complete, self-paced, mastery-based lesson — the
instructional model used by the Modern Classrooms Project. The teacher provides
an objective and some context; an orchestrated graph of AI steps drafts the
lesson, generates a mastery check, scores its own work against a rubric, and
pauses for the teacher to approve, edit, or reject before anything is finalized.

### Why it exists
1. **Real utility.** Building a single self-paced lesson — instruction, a
   "must-do" mastery check, and a differentiated extension — is time-consuming.
   This compresses the first draft from an hour to a minute, with the teacher
   firmly in control of the result.
2. **A demonstration of agentic engineering.** The project is deliberately
   built to exercise production agentic patterns: a graph with conditional
   edges, structured outputs, durable-style state, a human-in-the-loop
   interrupt, and an evaluation harness.

### Who uses it
A K-12 classroom teacher. The product is subject-agnostic: it serves a 3rd-grade
ELA teacher and a high-school algebra teacher equally. Subject area and grade
level are captured as structured inputs so the output adapts appropriately.

### Design principles
- **The teacher is always in the loop.** No generated content is ever treated
  as final without explicit teacher approval. This is a hard requirement, not a
  feature — it reflects the reality of putting AI-generated material in front of
  children.
- **The product is open-ended; the evals are pinned.** Teachers can enter any
  objective. The test suite uses a fixed set of objectives so prompt changes can
  be measured.
- **Every AI step returns structured data, not prose.** Free-text output between
  steps is a bug. Each node emits JSON matching a declared schema.

---

## 2. Architecture Overview

```
                         ┌─────────────────────────┐
                         │   Angular frontend (UI)  │
                         │  - objective + context   │
                         │  - live progress (RxJS)  │
                         │  - review / approve panel │
                         └────────────┬────────────┘
                                      │  HTTP + stream
                         ┌────────────▼────────────┐
                         │   FastAPI server         │
                         │   (thin transport layer) │
                         └────────────┬────────────┘
                                      │ invokes
                         ┌────────────▼────────────┐
                         │   LangGraph orchestrator │
                         └─────────────────────────┘
```

### Stack
| Layer | Choice | Why |
|---|---|---|
| Orchestration | **LangGraph** (Python) | The named, de-facto library for graph-based agent workflows. Legible to reviewers. |
| Model | Claude (via Anthropic API) | Provider-agnostic by design; model name lives in one config constant so a second provider can be added for a benchmark. |
| Structured outputs | **Pydantic** schemas | Each node validates its output against a schema. |
| Transport | **FastAPI** | Thin layer between the graph and the UI; streams progress events. |
| Frontend | **Angular + RxJS** | Plays directly to the role's frontend pillar; progress arrives as an observable stream. |
| State persistence | LangGraph checkpointer (SQLite) | Lets the graph pause at the interrupt and resume — the durable-execution story in miniature. |
| Evals | Python script + JSON dataset | A runnable test suite for AI behavior. |

---

## 3. The Graph

### Shared state
A single state object flows through every node and is updated at each step.

```python
class LessonState(TypedDict):
    # Inputs (set once, at the start)
    objective: str            # free text, e.g. "Identify the main idea of a paragraph"
    grade_level: str          # e.g. "3rd grade"
    subject: str              # enum: Math | ELA | Science | Social Studies | Other

    # Produced by nodes
    lesson: LessonContent | None          # node 1
    mastery_check: MasteryCheck | None    # node 2
    quality_report: QualityReport | None  # node 3
    revision_count: int                   # incremented each time we loop back

    # Set at the interrupt
    teacher_decision: Literal["approve", "revise", "reject"] | None
    teacher_notes: str | None

    # Final
    final_lesson: FinalLesson | None      # node 4
```

### Nodes & edges

**Node 1 — `draft_lesson`**
- Input: `objective`, `grade_level`, `subject`
- Output (structured): `LessonContent` — a short instructional explanation, 2-3
  worked examples, and an "aspire-to" extension activity for students who finish
  early (the differentiation piece of the model).

**Node 2 — `generate_mastery_check`**
- Input: `objective`, `grade_level`, `lesson`
- Output (structured): `MasteryCheck` — 3-5 questions that verify the objective
  is met, each with the correct answer and a one-line rationale.

**Node 3 — `quality_gate`** *(this is the conditional edge)*
- Input: `objective`, `grade_level`, `lesson`, `mastery_check`
- Output (structured): `QualityReport` — scores on (a) alignment to the
  objective, (b) grade-appropriate reading level, (c) whether the check actually
  tests the objective. Each scored pass/fail with a short critique.
- **Conditional routing:**
  - All pass → proceed to the teacher interrupt.
  - Any fail AND `revision_count < 2` → increment `revision_count`, route back to
    `generate_mastery_check` with the critique injected into context. *(This
    loop-until-a-defined-quality-bar pattern is a small RALPH loop: the completion
    promise is "all quality checks pass OR we've revised twice.")*
  - Any fail AND `revision_count >= 2` → proceed to the interrupt anyway, but
    surface the failing report to the teacher so they decide.

**Interrupt — `teacher_review`** *(human-in-the-loop circuit breaker)*
- The graph **pauses** here and persists its state via the checkpointer.
- The UI surfaces the drafted lesson, the mastery check, and the quality report.
- The teacher chooses: **approve** / **revise (with notes)** / **reject**.
- On resume:
  - `approve` → proceed to `finalize`.
  - `revise` → route back to `draft_lesson` with `teacher_notes` in context.
  - `reject` → end without a final lesson.

**Node 4 — `finalize`**
- Input: approved `lesson` + `mastery_check`
- Output (structured): `FinalLesson` — the assembled, formatted lesson ready to
  display/export.

### Graph diagram

```
draft_lesson
     │
     ▼
generate_mastery_check ◄──────────────┐ (revise: quality fail, <2 revisions)
     │                                │
     ▼                                │
quality_gate ─────────────────────────┘
     │ (pass, or revisions exhausted)
     ▼
teacher_review  ⏸ INTERRUPT ───► reject ──► END
     │
     ├── approve ──► finalize ──► END
     └── revise ───► draft_lesson (with teacher notes)
```

---

## 4. Structured Output Schemas

Each is a Pydantic model. The model is instructed to return JSON only; the
response is validated against the schema and a validation failure triggers one
retry before erroring.

- `LessonContent`: `{ explanation: str, worked_examples: list[Example], extension_activity: str }`
- `Example`: `{ prompt: str, solution: str }`
- `MasteryCheck`: `{ questions: list[CheckQuestion] }`
- `CheckQuestion`: `{ question: str, answer: str, rationale: str }`
- `QualityReport`: `{ alignment: Check, reading_level: Check, check_validity: Check }`
- `Check`: `{ passed: bool, critique: str }`
- `FinalLesson`: `{ title: str, lesson: LessonContent, mastery_check: MasteryCheck }`

---

## 5. Evaluation Harness

A runnable script (`evals/run_evals.py`) over a **pinned** dataset
(`evals/dataset.json`) of 5-8 objectives spanning subjects and grades.

Each dataset entry:
```json
{
  "id": "ela-3-main-idea",
  "objective": "Identify the main idea of a paragraph",
  "grade_level": "3rd grade",
  "subject": "ELA",
  "expectations": {
    "min_questions": 3,
    "max_questions": 5,
    "must_include_extension": true,
    "reading_level_band": "2-4"
  }
}
```

The harness runs the graph up to (but not through) the interrupt for each entry,
then asserts the structural expectations and prints a pass/fail table. This
catches regressions when a prompt is edited. The point is not a perfect grader —
it is demonstrating that AI behavior is tested like code, not eyeballed.

> Stretch goal: a second provider behind the same interface, with the harness
> printing a cost / latency / pass-rate comparison. This is the cross-provider
> benchmark. Not required for v1.

---

## 6. Frontend Spec (Angular)

- **Input view:** objective (textarea), grade level (select), subject (select),
  Generate button.
- **Progress view:** as the graph runs, the UI subscribes to a stream of progress
  events (`drafting`, `generating check`, `quality check`, `awaiting review`) via
  an RxJS `Observable`. This is the place to show clean reactive patterns.
- **Review panel:** renders the lesson, the mastery check, and the quality
  report; offers Approve / Revise (with a notes field) / Reject.
- **Final view:** the formatted approved lesson, with a copy/export button.
- **Accessibility:** semantic headings, labelled controls, focus management when
  the review panel appears, adequate contrast. (Front-and-center because the role
  names accessibility explicitly.)

---

## 7. Build Order (scoped to a weekend)

1. **The graph, headless.** Build all four nodes, the conditional edge, and the
   schemas. Drive it from a Python script with hardcoded inputs. *Stop the
   interrupt here as a simple console prompt.* — This is the hard, impressive
   core. If you ship only this with a great README, it's already strong.
2. **The checkpointer + real interrupt.** Wire the SQLite checkpointer so the
   graph genuinely pauses and resumes across the interrupt.
3. **FastAPI wrapper + progress stream.**
4. **Angular frontend.** Input → progress → review → final.
5. **Eval harness + dataset.**
6. **README** with the architecture diagram, the spec link, and run instructions.

> If time runs short, items 1, 2, 5, and 6 produce a complete, defensible
> artifact on their own. The frontend is the polish pass.

---

## 8. Out of Scope (v1)

- User accounts / auth.
- Saving lessons to a database (final lesson is displayed/exported, not stored).
- LMS integrations (Canvas, Google Classroom) — noted as a future direction.
- Multi-lesson unit sequencing.

---

## 9. What This Demonstrates (for the reader)

| JD requirement | Where it lives in this project |
|---|---|
| Graph-based agentic orchestration, nodes & conditional edges | The graph (§3) |
| Structured outputs | Pydantic schemas (§4) |
| Human-in-the-loop circuit breakers / interrupts | `teacher_review` interrupt (§3) |
| Durable execution surviving restarts | SQLite checkpointer (§2, §3) |
| Evaluation harness, annotated datasets | §5 |
| Cross-provider benchmark | §5 stretch goal |
| RALPH loop with a completion promise | `quality_gate` revision loop (§3) |
| Spec-Driven Development | This document |
| Angular, RxJS, accessibility | Frontend spec (§6) |
| Edtech product sense | The whole premise |
