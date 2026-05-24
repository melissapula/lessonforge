# LessonForge

**An agentic, human-in-the-loop generator for self-paced, mastery-based lessons.**

A teacher enters a learning objective, a grade level, and a subject. An
orchestrated graph of AI steps drafts the instruction, generates a mastery
check, scores its own work against a rubric, and **pauses for the teacher to
approve, revise, or reject** before anything is finalized. No AI-generated
content is ever treated as final without a human in the loop.

Built around the [Modern Classrooms](https://www.modernclassrooms.org/)
self-paced, mastery-based instructional model.

> The full design contract lives in [`SPEC.md`](./SPEC.md), written **before**
> any code — this project follows spec-driven development. Spec and
> implementation move together; if they ever disagree, fix one of them
> deliberately.

---

## Demo

<p align="center">
  <video src="./docs/demo.mp4" controls width="720"></video>
</p>

A walkthrough of one full lesson: enter an objective → watch the pipeline
stream node-completion events → review the draft, the mastery check, and the
quality report → approve → see the finalized lesson.

---

## What this demonstrates

A portfolio piece for production agentic engineering. Each pattern below is
small and load-bearing; together they form the playbook for shipping LLM
features that don't catch fire in production.

| Pattern | Where it lives |
|---|---|
| Graph-based orchestration with conditional edges | `app/graph.py` — four nodes, two conditional routes ([SPEC §3](./SPEC.md#3-the-graph)) |
| Structured outputs (validated JSON, never prose between nodes) | `app/schemas.py`, `app/llm.py` ([SPEC §4](./SPEC.md#4-structured-output-schemas)) |
| Human-in-the-loop interrupt / circuit breaker | `interrupt_before=["teacher_review"]` in `app/graph.py` |
| Durable execution — a paused graph survives a process restart | SQLite checkpointer wired in `app/api.py` and `app/run.py` |
| Bounded self-correction (RALPH) loop with an explicit completion promise | `route_after_quality` in `app/graph.py`, `MAX_QUALITY_REVISIONS=2` |
| Evaluation harness over a pinned dataset | `evals/run_evals.py` ([SPEC §5](./SPEC.md#5-evaluation-harness)) |
| Streaming transport mirroring the interrupt boundary | `app/api.py` — two SSE streams per lesson ([SPEC §6](./SPEC.md#6-api-contract-fastapi--graph)) |
| Single provider seam (one model, one place to swap) | `MODEL` constant in `app/llm.py` |
| Spec-driven development | This README + [`SPEC.md`](./SPEC.md) |

---

## Architecture

### System view

```mermaid
flowchart LR
    UI["Angular + RxJS<br/>web/"]
    CLI["Headless CLI<br/>app/run.py"]
    API["FastAPI<br/>app/api.py"]
    Graph["LangGraph orchestrator<br/>app/graph.py"]
    DB[("SQLite checkpointer<br/>lessonforge_state.db")]
    Model["Anthropic Claude<br/>(claude-sonnet-4-6)"]

    UI -->|HTTP + SSE| API
    API -->|stream events| UI
    CLI -->|drives directly| Graph
    API -->|graph.stream| Graph
    Graph <-->|persist / resume| DB
    Graph -->|generate_structured| Model
```

### Graph view

```mermaid
flowchart TD
    Start([objective + grade + subject])
    draft[draft_lesson]
    check[generate_mastery_check]
    quality{quality_gate}
    bump[bump_revision]
    review[/teacher_review<br/>⏸ INTERRUPT/]
    final[finalize]
    Done([END])

    Start --> draft
    draft --> check
    check --> quality
    quality -->|all pass| review
    quality -->|fail + revisions left| bump
    bump --> check
    quality -.->|fail + revisions exhausted| review
    review -->|approve| final
    review -->|revise| draft
    review -->|reject| Done
    final --> Done
```

A single shared **state** flows through every node, picking up fields as it
goes. Each node returns a partial update; LangGraph merges it. The conditional
edge after `quality_gate` is a small **RALPH loop**: regenerate up to
`MAX_QUALITY_REVISIONS` times if quality fails, then surface the flawed draft
to the teacher rather than loop forever. The completion promise — the rule
that bounds the loop — is the central discipline of autonomous loops, and it
lives in code, not in hope.

The `teacher_review` interrupt is the human-in-the-loop circuit breaker. The
graph **pauses** there, persisting state via the checkpointer. The outside
world reads the paused state, collects the teacher's choice, writes it back,
and resumes. Because state is durable, the process can restart between pause
and resume without losing the run.

---

## Setup

Requires Python 3.10+, Node 20+, and an [Anthropic API key](https://console.anthropic.com/).

### Backend

```bash
python -m venv .venv
source .venv/bin/activate              # Windows: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Set the Anthropic API key one of two ways:

- **Recommended — `.env` file.** Copy `.env.example` to `.env` and fill in the
  key. `app/__init__.py` loads it at import time, so every entry point
  (`uvicorn app.api:app`, `python -m app.run`, `python -m evals.run_evals`)
  picks it up automatically. `.env` is gitignored.
- **Or a real env var.** `export ANTHROPIC_API_KEY=sk-...` (Linux/macOS) or
  set it persistently on Windows. A real env var still wins over `.env`.

> Check the current model name in the Anthropic docs and update `MODEL` in
> `app/llm.py` if needed. Model strings change.

### Frontend

```bash
cd web
npm install                            # installs Angular + its devDeps
```

### Repo tooling (optional but recommended)

```bash
npm install                            # at the repo root: husky + lint-staged
```

Activates a pre-commit hook that runs Prettier (auto-fix on staged files)
and ESLint (check) on the `web/` tree before each commit. Skip this if
you don't plan to commit.

---

## Four ways to drive it

### 1. Headless CLI — full interrupt/resume cycle in the terminal

```bash
python -m app.run
```

Prompts for an objective, grade, and subject. Watch each node complete, see
the draft and quality report, then make the approve / revise / reject
decision. State persists to `lessonforge_state.db`, so you can kill the
process mid-pause and resume from where it stopped — the durable-execution
story in miniature.

### 2. Eval harness — regression test over a pinned dataset

```bash
python -m evals.run_evals
```

Runs the graph up to (but not through) the interrupt for each entry in
`evals/dataset.json` and prints a pass/fail table. Rerun after any prompt
edit to catch regressions. The point isn't a perfect grader — it's
demonstrating that AI behavior is tested like code, not eyeballed.

```
Running 6 eval cases...

[PASS] ela-3-main-idea
[PASS] math-8-two-step-equations
[PASS] sci-5-water-cycle
[PASS] ss-7-branches-of-government
[PASS] math-2-place-value
[PASS] ela-10-thesis-statement

ALL PASSED
```

### 3. HTTP API — FastAPI server with streamed progress

```bash
uvicorn app.api:app --reload
```

Then visit <http://127.0.0.1:8000/docs> for Swagger UI, or call the endpoints
directly. Two SSE endpoints mirror the graph's pause boundary:

- `POST /lessons` opens an event stream that emits `node_complete` events
  through `draft → check → quality`, then closes with `awaiting_review`.
- `POST /lessons/{id}/decision` opens a second stream that resumes the graph
  to `finalize` (or back through the loop on `revise`).

Full event-type reference and design rationale in
[SPEC §6](./SPEC.md#6-api-contract-fastapi--graph). The two-stream design
keeps the HTTP boundary aligned with the graph's pause boundary — no
background tasks, no shared queues, no concurrency surface.

### 4. Browser UI — Angular + RxJS

Run the backend and the Angular dev server in two terminals:

```bash
# Terminal A — backend
uvicorn app.api:app --reload

# Terminal B — frontend (from web/)
cd web
npm start
```

Open <http://localhost:4200>. Enter an objective, grade, and subject; watch
each pipeline node complete; review the draft and approve / revise / reject;
see the finalized lesson with a copy button.

The frontend showcases:

- **SSE-over-POST as an RxJS Observable.** The browser's native `EventSource`
  is GET-only, but our endpoints are POST. `LessonApiService` wraps
  `fetch` + `ReadableStream` + manual SSE frame parsing as an `Observable`
  that emits each typed event; unsubscribing aborts the in-flight fetch
  via `AbortController`.
- **State as a signal store.** `LessonStateService` owns the lifecycle
  (`idle | running | reviewing | finalizing | approved | rejected | error`)
  and exposes it as Angular signals. Components stay declarative; the
  service handles the subscription dance.
- **State-driven view switching.** The root template is a single
  `@switch` over `state.status()` — no router needed; the graph's state
  machine is the view router.
- **Accessibility.** Semantic landmarks, skip-to-main link, `aria-live`
  on the progress region, labelled controls, focus styles, and pass/fail
  badges that don't rely on color alone.

---

## Project layout

| File | What it owns |
|---|---|
| [`SPEC.md`](./SPEC.md) | The design contract. Source of truth. |
| [`CLAUDE.md`](./CLAUDE.md) | Working conventions + build order for contributors. |
| `app/schemas.py` | Pydantic output contracts + the graph's shared state. |
| `app/llm.py` | Structured-output model wrapper; the single provider seam. |
| `app/nodes.py` | The four pipeline nodes (draft, check, quality, finalize). |
| `app/graph.py` | LangGraph wiring: edges, the RALPH loop, the interrupt. |
| `app/run.py` | Headless CLI driver + interrupt/resume cycle. |
| `app/api.py` | FastAPI transport with SSE streams. |
| `evals/dataset.json` | Pinned objectives spanning subjects and grade levels. |
| `evals/run_evals.py` | The eval harness. |
| `web/src/app/api/` | TypeScript API client (types + SSE-over-POST RxJS service + lifecycle store). |
| `web/src/app/{input-form,progress,review,final-lesson}/` | Four standalone components, one per lifecycle phase. |
| `web/src/app/app.{ts,html,css}` | Root shell with state-driven view switching. |

---

## Status

**Shipped:**

- Headless graph with all four nodes and conditional routing
- Pydantic schemas for every model output (no prose between nodes)
- Human-in-the-loop interrupt with durable resume
- Bounded self-correction (RALPH) quality loop
- Pinned eval harness (6 cases passing across grades 2–10 and four subjects)
- FastAPI transport with two-stream SSE matching the interrupt boundary
- Angular + RxJS frontend with state-driven view switching, fetch+ReadableStream wrapped as Observable, signals-based state store, and accessibility baked in
- Husky pre-commit hook (Prettier auto-fix + ESLint check) on the `web/` tree

**Deliberately deferred:**

- **Public deploy.** `POST /lessons` calls the Anthropic API on each
  invocation. Exposing it without auth, rate limiting, and a hard spend cap
  is a credit-burn risk for a single-developer project. Local-runnable is a
  deliberate choice, not an oversight.
- **Cross-provider benchmark.** A second model behind `generate_structured`
  with the eval harness reporting cost / latency / pass-rate. Stretch goal
  in [SPEC §5](./SPEC.md#5-evaluation-harness).
- **LMS export.** Google Classroom, Canvas. Future direction noted in
  [SPEC §9](./SPEC.md#9-out-of-scope-v1).
