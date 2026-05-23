"""
api.py
======
Thin FastAPI transport over the LangGraph pipeline. Two streaming endpoints
mirror the graph's pause boundary (see SPEC.md §6):

    POST /lessons                       -> SSE until the teacher interrupt
    POST /lessons/{id}/decision         -> SSE until graph END (or the next interrupt)

A small utility endpoint returns the current state snapshot:

    GET  /lessons/{id}

The HTTP layer is deliberately stateless. All durable state lives in the
LangGraph SqliteSaver, keyed by thread_id. We open one shared checkpointer
for the server's lifetime via the FastAPI lifespan.

Run:
    uvicorn app.api:app --reload
"""

from __future__ import annotations
import json
import uuid
from contextlib import asynccontextmanager
from typing import Iterator, Literal, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from langgraph.checkpoint.sqlite import SqliteSaver
from pydantic import BaseModel

from .graph import build_graph, fresh_state
from .schemas import SUBJECTS


CHECKPOINT_DB = "lessonforge_state.db"


# ---------------------------------------------------------------------------
# Lifespan owns the one-and-only checkpointer + compiled graph. SqliteSaver
# is a context manager; lifespan keeps it open across all requests.
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    with SqliteSaver.from_conn_string(CHECKPOINT_DB) as checkpointer:
        app.state.graph = build_graph(checkpointer)
        yield


app = FastAPI(title="LessonForge", lifespan=lifespan)

# Permissive CORS for the Angular dev server. Tighten before deploy.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------
class CreateLessonRequest(BaseModel):
    objective: str
    grade_level: str
    subject: str


class DecisionRequest(BaseModel):
    decision: Literal["approve", "revise", "reject"]
    notes: Optional[str] = None


# ---------------------------------------------------------------------------
# SSE helpers. An event on the wire looks like:
#     event: node_complete\n
#     data: {"node":"draft_lesson","update":{...}}\n
#     \n
# Three lines, terminated by a blank line. No library needed.
# ---------------------------------------------------------------------------
def _json_default(obj):
    """Serialize Pydantic BaseModel objects nested inside dicts/lists."""
    if isinstance(obj, BaseModel):
        return obj.model_dump()
    raise TypeError(f"Not JSON-serializable: {type(obj).__name__}")


def _sse(event: str, data: dict) -> str:
    payload = json.dumps(data, default=_json_default)
    return f"event: {event}\ndata: {payload}\n\n"


def _snapshot_dict(values: dict) -> dict:
    """Round-trip the state dict through JSON so Pydantic models become plain dicts."""
    return json.loads(json.dumps(values, default=_json_default))


# ---------------------------------------------------------------------------
# The streaming runner. Drives graph.stream() and yields SSE events.
# `initial` is the fresh state for a new run, or None to resume a paused graph.
# After the stream loop exits, we inspect snapshot.next to tell "paused at the
# interrupt" apart from "graph reached END".
# ---------------------------------------------------------------------------
def _stream_events(graph, config: dict, initial) -> Iterator[str]:
    try:
        for step in graph.stream(initial, config):
            node, update = next(iter(step.items()))
            # Skip LangGraph internal markers (e.g. __interrupt__) — they carry
            # no useful payload and the meaningful interrupt signal is the
            # `awaiting_review` event we emit after the loop exits.
            if node.startswith("__"):
                continue
            yield _sse("node_complete", {"node": node, "update": update})
    except Exception as e:
        yield _sse("error", {"message": str(e)})
        return

    snapshot = graph.get_state(config)
    if snapshot.next and "teacher_review" in snapshot.next:
        yield _sse("awaiting_review", {
            "thread_id": config["configurable"]["thread_id"],
            "state": _snapshot_dict(snapshot.values),
        })
    else:
        final = snapshot.values.get("final_lesson")
        yield _sse("complete", {
            "status": "approved" if final else "rejected",
            "final_lesson": final,
        })


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@app.post("/lessons")
def create_lesson(req: CreateLessonRequest):
    if req.subject not in SUBJECTS:
        raise HTTPException(400, f"subject must be one of {SUBJECTS}")
    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}
    state = fresh_state(req.objective, req.grade_level, req.subject)

    def generator():
        # Send thread_id first so the client knows what to address.
        yield _sse("thread_id", {"thread_id": thread_id})
        yield from _stream_events(app.state.graph, config, state)

    return StreamingResponse(generator(), media_type="text/event-stream")


@app.post("/lessons/{thread_id}/decision")
def submit_decision(thread_id: str, req: DecisionRequest):
    config = {"configurable": {"thread_id": thread_id}}
    snapshot = app.state.graph.get_state(config)
    if not snapshot or not snapshot.values:
        raise HTTPException(404, f"no lesson found for thread_id={thread_id}")
    if not snapshot.next or "teacher_review" not in snapshot.next:
        raise HTTPException(409, "graph is not paused at teacher_review")
    if req.decision == "revise" and not (req.notes and req.notes.strip()):
        raise HTTPException(400, "revise requires non-empty notes")

    app.state.graph.update_state(
        config,
        {"teacher_decision": req.decision, "teacher_notes": req.notes},
    )

    def generator():
        # None as input = resume from the paused interrupt.
        yield from _stream_events(app.state.graph, config, None)

    return StreamingResponse(generator(), media_type="text/event-stream")


@app.get("/lessons/{thread_id}")
def get_lesson(thread_id: str):
    config = {"configurable": {"thread_id": thread_id}}
    snapshot = app.state.graph.get_state(config)
    if not snapshot or not snapshot.values:
        raise HTTPException(404, f"no lesson found for thread_id={thread_id}")
    values = snapshot.values
    if snapshot.next and "teacher_review" in snapshot.next:
        status = "awaiting_review"
    elif values.get("final_lesson"):
        status = "approved"
    elif values.get("teacher_decision") == "reject":
        status = "rejected"
    else:
        status = "running"
    return {
        "thread_id": thread_id,
        "status": status,
        "state": _snapshot_dict(values),
    }


@app.get("/healthz")
def healthz():
    return {"ok": True}
