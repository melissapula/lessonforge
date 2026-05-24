/**
 * api.types.ts
 *
 * TypeScript shapes for the LessonForge HTTP API. These mirror the Pydantic
 * schemas in app/schemas.py and the SSE event contract documented in
 * SPEC.md §6. Keep them in sync — the backend is the source of truth.
 */

// --- Structured outputs produced by the graph (Pydantic models on the server) ---

export interface Example {
    prompt: string;
    solution: string;
}

export interface LessonContent {
    explanation: string;
    worked_examples: Example[];
    extension_activity: string;
}

export interface CheckQuestion {
    question: string;
    answer: string;
    rationale: string;
}

export interface MasteryCheck {
    questions: CheckQuestion[];
}

export interface Check {
    passed: boolean;
    critique: string;
}

export interface QualityReport {
    alignment: Check;
    reading_level: Check;
    check_validity: Check;
}

export interface FinalLesson {
    title: string;
    lesson: LessonContent;
    mastery_check: MasteryCheck;
}

// --- The graph's shared state, projected to JSON over the wire ---

export interface LessonStateSnapshot {
    objective: string;
    grade_level: string;
    subject: string;
    lesson: LessonContent | null;
    mastery_check: MasteryCheck | null;
    quality_report: QualityReport | null;
    revision_count: number;
    teacher_decision: TeacherDecision | null;
    teacher_notes: string | null;
    final_lesson: FinalLesson | null;
}

// Partial update yielded by a single node completion.
export type NodeUpdate = Partial<LessonStateSnapshot>;

// --- Requests ---

export interface CreateLessonRequest {
    objective: string;
    grade_level: string;
    subject: Subject;
}

export type TeacherDecision = 'approve' | 'revise' | 'reject';

export interface DecisionRequest {
    decision: TeacherDecision;
    notes?: string | null;
}

// Mirrors SUBJECTS in app/schemas.py — keep these in sync.
export const SUBJECTS = ['Math', 'ELA', 'Science', 'Social Studies', 'Music', 'Other'] as const;
export type Subject = (typeof SUBJECTS)[number];

export const GRADE_LEVELS = [
    'Kindergarten',
    '1st grade',
    '2nd grade',
    '3rd grade',
    '4th grade',
    '5th grade',
    '6th grade',
    '7th grade',
    '8th grade',
    '9th grade',
    '10th grade',
    '11th grade',
    '12th grade',
] as const;
export type GradeLevel = (typeof GRADE_LEVELS)[number];

// --- SSE events (discriminated union; see SPEC.md §6 event table) ---

export interface ThreadIdEvent {
    event: 'thread_id';
    data: { thread_id: string };
}

export interface NodeCompleteEvent {
    event: 'node_complete';
    data: { node: string; update: NodeUpdate | null };
}

export interface AwaitingReviewEvent {
    event: 'awaiting_review';
    data: { thread_id: string; state: LessonStateSnapshot };
}

export interface CompleteEvent {
    event: 'complete';
    data: { status: 'approved' | 'rejected'; final_lesson: FinalLesson | null };
}

export interface ErrorEvent {
    event: 'error';
    data: { message: string };
}

export type LessonEvent =
    | ThreadIdEvent
    | NodeCompleteEvent
    | AwaitingReviewEvent
    | CompleteEvent
    | ErrorEvent;

// --- Snapshot endpoint (GET /lessons/{id}) ---

export type LessonStatus = 'running' | 'awaiting_review' | 'approved' | 'rejected';

export interface LessonSnapshot {
    thread_id: string;
    status: LessonStatus;
    state: LessonStateSnapshot;
}
