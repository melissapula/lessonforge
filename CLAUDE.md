# CLAUDE.md

> Context for Claude Code (and for me, future-Missa) when working in this repo.
> Read this first. It explains what the project is, the order to do things in,
> and the conventions to keep.

---

## What this project is

**LessonForge** — an agentic, human-in-the-loop generator for self-paced,
mastery-based lessons, built around the Modern Classrooms instructional model.
A teacher gives an objective + grade + subject; a LangGraph pipeline drafts a
lesson, generates a mastery check, scores its own work, and **pauses for the
teacher to approve / revise / reject** before finalizing.

This is a portfolio project demonstrating production agentic patterns:
graph orchestration, conditional edges, structured outputs, a human-in-the-loop
interrupt, durable execution, a bounded self-correction loop, and an eval harness.

**The design contract is `SPEC.md`. It is the source of truth. If behavior and
the spec disagree, fix one of them deliberately — don't let them drift.**

---

## FIRST-TIME SETUP (do this once, in order)

1. **Unzip the project** somewhere permanent (not Downloads).
2. **Create the git repo and make the spec the first commit** — this ordering is
   the point. It's the evidence of spec-driven development.
   ```bash
   cd lessonforge
   git init
   git add SPEC.md
   git commit -m "Spec: LessonForge design contract (spec-driven development)"
   git add .
   git commit -m "Scaffold: headless agentic backend + evals"
   ```
3. **Create a virtual environment and install deps:**
   ```bash
   python -m venv .venv
   source .venv/bin/activate          # Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   ```
4. **Set your API key.** Two options:
   - **Recommended:** `cp .env.example .env` and put the key in `.env`.
     `app/__init__.py` loads it at import time via python-dotenv.
     `.env` is gitignored.
   - **Or a real env var:** `export ANTHROPIC_API_KEY=sk-...` (or
     persistent Windows User-scope). Real env vars win over `.env`.
5. **Confirm the model name.** Open `app/llm.py` and check the `MODEL` constant
   against the current Anthropic docs — model strings change. Update if needed.
6. **Install the frontend (if you'll be running the web UI):**
   ```bash
   cd web && npm install                # Angular + its devDeps
   cd .. && npm install                 # repo root: husky + lint-staged + prettier
   ```
   The root `npm install` activates the husky pre-commit hook (Prettier
   auto-fix + ESLint check on the `web/` tree).

---

## BUILD ORDER (the sequence to work through)

The backend (steps 1–2) is already scaffolded. Work top to bottom; each step is
a complete, defensible stopping point.

- [x] **1. Headless graph.** Nodes, schemas, conditional edge, interrupt.
      → Verify: `python -m app.run`
- [x] **2. Checkpointer + real interrupt.** State persists; graph pauses/resumes.
      → Already wired via SqliteSaver in `app/run.py`.
- [x] **3. Eval harness.** Already written — just run it and read the output:
      → `python -m evals.run_evals`
- [x] **4. FastAPI wrapper + progress stream.** Thin transport layer over the
      graph; stream node-completion events so a UI can subscribe.
      → Verify: `uvicorn app.api:app --reload`, then `GET /healthz` and
        `POST /lessons` (SSE). API contract is in SPEC.md §6.
- [x] **5. Angular + RxJS frontend.** Input → live progress → review panel →
      final lesson. SSE-over-POST wrapped as an RxJS Observable via
      `fetch + ReadableStream`; signals-based state store; state-driven
      view switching via `@switch`; accessibility (skip link, aria-live,
      labelled controls, focus styles).
      → Verify: `cd web; npm start` and visit http://localhost:4200
        (with `uvicorn app.api:app --reload` running in another terminal).
- [x] **6a. Polish the README + architecture diagram.** Mermaid diagrams
      render inline on GitHub; the README leads with what the project
      demonstrates and links to the spec for depth.
- [ ] **6b. Deploy** — deferred. `POST /lessons` is an open door to your
      Anthropic credits without auth + rate limit + spend cap. Reasons +
      the path to "yes" are in the README's *Status* section.

> If time runs short, steps 1–3 + a strong README are already a complete artifact.
> The frontend is the polish pass, not the proof.

### Stretch goals (only after the above)
- Cross-provider benchmark: a second model behind `generate_structured`, with the
  eval harness reporting cost / latency / pass-rate.
- LMS export (Google Classroom / Canvas).

---

## HOW TO VERIFY THINGS WORK

- **Run the pipeline:** `python -m app.run` — enter an objective, watch nodes
  complete, see the draft, then choose approve / revise / reject.
- **Test the interrupt properly:** run it once and choose **revise** with real
  notes; confirm it loops back through `draft_lesson` and the redraft reflects
  your notes. Then run again and **approve** to see `finalize`.
- **Run evals:** `python -m evals.run_evals` — expect a pass/fail table.
- **Re-run evals after ANY prompt change** in `app/nodes.py` to catch regressions.

---

## CONVENTIONS (keep these)

- **Structured output, never prose between nodes.** Every model call goes through
  `generate_structured()` and validates against a Pydantic schema. If you need a
  new piece of generated data, add a schema first.
- **Nodes return partial state updates**, never mutate state in place. A node
  returns a dict of only the fields it changed.
- **Scoring and routing are separate.** `quality_gate` produces a report; the
  decision to loop or continue lives in the conditional edge (`route_after_quality`).
  Keep that separation.
- **The quality loop must stay bounded.** `MAX_QUALITY_REVISIONS` in `schemas.py`
  is the completion promise. Never remove the bound — an unbounded autonomous loop
  is a bug, not a feature.
- **One provider seam.** Model choice lives in the `MODEL` constant in `llm.py`.
  Don't import the Anthropic SDK anywhere else.
- **Update SPEC.md when you change behavior**, in the same commit. The spec is
  not documentation-after-the-fact; it leads.

---

## FILE MAP

| File | What it owns |
|---|---|
| `SPEC.md` | The design contract. Source of truth. |
| `app/schemas.py` | Pydantic output contracts + the graph's shared state. |
| `app/llm.py` | Structured-output model wrapper; the provider seam. |
| `app/nodes.py` | The four pipeline steps (draft, check, quality, finalize). |
| `app/graph.py` | LangGraph wiring: edges, the RALPH loop, the interrupt. |
| `app/run.py` | Headless CLI driver + interrupt/resume cycle. |
| `app/api.py` | FastAPI transport: SSE streams for the two pause-phases. |
| `evals/dataset.json` | Pinned objectives for regression testing. |
| `evals/run_evals.py` | The eval harness. |
| `web/src/app/api/api.types.ts` | TS types mirroring the Pydantic schemas + SSE events. |
| `web/src/app/api/lesson-api.service.ts` | SSE-over-POST wrapped as RxJS Observable. |
| `web/src/app/api/lesson-state.service.ts` | Lifecycle store (signals). |
| `web/src/app/{input-form,progress,review,final-lesson}/` | Four standalone components, one per lifecycle phase. |
| `web/src/app/app.{ts,html,css}` | Root shell with state-driven view switching. |
| `package.json` + `.husky/pre-commit` | Repo-level dev tooling (prettier + lint-staged + husky). |

---

## NOTES TO SELF

- Commit small and often, with messages that show the spec-then-code rhythm.
- When asking Claude Code for a feature, point it at `SPEC.md` and the relevant
  file; describe the change as a spec update first, then the implementation.
- The interview value is being able to explain every line. If something here is a
  black box to you, ask Claude Code to walk you through it before you extend it.
