/**
 * lesson-state.service.ts
 *
 * The lifecycle store for a single lesson run. Components read signals from
 * here; the service drives them by subscribing to the API streams. Modern
 * Angular pattern: signals for component-facing state, RxJS internally for
 * the streaming work.
 *
 * Lifecycle states:
 *   idle        -> nothing happening, ready to start
 *   running     -> POST /lessons stream is open, nodes completing
 *   reviewing   -> graph paused at the interrupt, teacher needs to decide
 *   finalizing  -> POST /lessons/{id}/decision stream is open
 *   approved    -> done, final_lesson available
 *   rejected    -> done, teacher rejected
 *   error       -> something failed; errorMessage holds the detail
 */

import { Injectable, computed, inject, signal } from '@angular/core';
import { Subscription } from 'rxjs';
import { LessonApiService } from './lesson-api.service';
import type {
  CreateLessonRequest,
  DecisionRequest,
  FinalLesson,
  LessonEvent,
  LessonStateSnapshot,
} from './api.types';

export type LessonStatus =
  | 'idle'
  | 'running'
  | 'reviewing'
  | 'finalizing'
  | 'approved'
  | 'rejected'
  | 'error';

export interface NodeProgress {
  node: string;
  at: number; // ms since epoch
}

@Injectable({ providedIn: 'root' })
export class LessonStateService {
  private api = inject(LessonApiService);

  // --- Component-facing state (signals) ---
  readonly status = signal<LessonStatus>('idle');
  readonly threadId = signal<string | null>(null);
  readonly snapshot = signal<LessonStateSnapshot | null>(null);
  readonly nodesCompleted = signal<NodeProgress[]>([]);
  readonly finalLesson = signal<FinalLesson | null>(null);
  readonly errorMessage = signal<string | null>(null);

  // Derived
  readonly isBusy = computed(() => {
    const s = this.status();
    return s === 'running' || s === 'finalizing';
  });
  readonly isReviewing = computed(() => this.status() === 'reviewing');
  readonly isDone = computed(() => {
    const s = this.status();
    return s === 'approved' || s === 'rejected';
  });

  private subscription?: Subscription;

  // --- Commands ---

  startLesson(req: CreateLessonRequest): void {
    if (this.isBusy()) return;
    this.reset();
    // Seed the snapshot from the request so the UI can show "what's being
    // generated" before the first node finishes.
    this.snapshot.set({
      objective: req.objective,
      grade_level: req.grade_level,
      subject: req.subject,
      lesson: null,
      mastery_check: null,
      quality_report: null,
      revision_count: 0,
      teacher_decision: null,
      teacher_notes: null,
      final_lesson: null,
    });
    this.status.set('running');
    this.subscription = this.api.createLesson(req).subscribe({
      next: (e) => this.handleEvent(e),
      error: (err) => this.handleError(err),
    });
  }

  decide(req: DecisionRequest): void {
    const tid = this.threadId();
    if (!tid || this.status() !== 'reviewing') return;
    this.status.set('finalizing');
    this.subscription?.unsubscribe();
    this.subscription = this.api.submitDecision(tid, req).subscribe({
      next: (e) => this.handleEvent(e),
      error: (err) => this.handleError(err),
    });
  }

  reset(): void {
    this.subscription?.unsubscribe();
    this.subscription = undefined;
    this.status.set('idle');
    this.threadId.set(null);
    this.snapshot.set(null);
    this.nodesCompleted.set([]);
    this.finalLesson.set(null);
    this.errorMessage.set(null);
  }

  // --- Event handling ---

  private handleEvent(e: LessonEvent): void {
    switch (e.event) {
      case 'thread_id':
        this.threadId.set(e.data.thread_id);
        break;

      case 'node_complete': {
        const node = e.data.node;
        // The teacher_review node is a no-op stub in the graph; it carries
        // no useful payload (LangGraph normalizes its empty return to null).
        if (node === 'teacher_review') return;
        this.nodesCompleted.update((arr) => [...arr, { node, at: Date.now() }]);
        // Accumulate partial state updates so the UI can show the lesson
        // appearing incrementally as each node finishes.
        const update = e.data.update;
        if (update) {
          this.snapshot.update((cur) => (cur ? { ...cur, ...update } : cur));
        }
        break;
      }

      case 'awaiting_review':
        this.threadId.set(e.data.thread_id);
        this.snapshot.set(e.data.state); // authoritative snapshot from server
        this.status.set('reviewing');
        break;

      case 'complete':
        if (e.data.status === 'approved' && e.data.final_lesson) {
          this.finalLesson.set(e.data.final_lesson);
          this.status.set('approved');
        } else {
          this.status.set('rejected');
        }
        break;

      case 'error':
        this.errorMessage.set(e.data.message);
        this.status.set('error');
        break;
    }
  }

  private handleError(err: unknown): void {
    const message = err instanceof Error ? err.message : String(err);
    this.errorMessage.set(message);
    this.status.set('error');
  }
}
