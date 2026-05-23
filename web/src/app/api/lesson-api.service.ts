/**
 * lesson-api.service.ts
 *
 * The HTTP client for the LessonForge backend. Two of the three endpoints
 * stream Server-Sent Events; this service exposes them as RxJS Observables.
 *
 * The browser's native EventSource only supports GET, but our endpoints are
 * POST (they take a JSON body). So we use fetch() with a ReadableStream,
 * parse SSE frames manually, and emit each parsed event through an Observable.
 * Cancelling the subscription aborts the in-flight fetch.
 *
 * See SPEC.md §6 for the wire format we're parsing here.
 */

import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';
import type {
  CreateLessonRequest,
  DecisionRequest,
  LessonEvent,
  LessonSnapshot,
} from './api.types';

// Hard-coded to the local dev backend. SPEC.md §9 lists "public deploy" as
// deferred; when that lands, this becomes an environment-driven value.
const API_BASE = 'http://127.0.0.1:8000';

@Injectable({ providedIn: 'root' })
export class LessonApiService {
  /**
   * POST /lessons — start a new lesson and stream events until the interrupt.
   * The stream completes after `awaiting_review` (or `error`/`complete` if the
   * graph never reaches the interrupt, which shouldn't happen in normal flow).
   */
  createLesson(req: CreateLessonRequest): Observable<LessonEvent> {
    return this.streamSse(`${API_BASE}/lessons`, req);
  }

  /**
   * POST /lessons/{id}/decision — resume a paused graph with the teacher's
   * decision. Streams events until graph END (or, on `revise`, until the next
   * interrupt at which point it pauses again).
   */
  submitDecision(threadId: string, req: DecisionRequest): Observable<LessonEvent> {
    return this.streamSse(`${API_BASE}/lessons/${encodeURIComponent(threadId)}/decision`, req);
  }

  /**
   * GET /lessons/{id} — snapshot endpoint. Useful for hydrating the review
   * panel if the client navigates away and comes back, or after a network blip.
   */
  async fetchSnapshot(threadId: string): Promise<LessonSnapshot> {
    const response = await fetch(`${API_BASE}/lessons/${encodeURIComponent(threadId)}`);
    if (!response.ok) {
      throw new Error(`Snapshot fetch failed (${response.status} ${response.statusText})`);
    }
    return response.json() as Promise<LessonSnapshot>;
  }

  /**
   * The streaming primitive. Opens a POST request, treats the response body as
   * a UTF-8 text stream, splits on the SSE event terminator (\n\n), parses each
   * frame into a LessonEvent, and emits it. Unsubscribing aborts the fetch.
   */
  private streamSse(url: string, body: unknown): Observable<LessonEvent> {
    return new Observable<LessonEvent>((subscriber) => {
      const controller = new AbortController();

      (async () => {
        try {
          const response = await fetch(url, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              Accept: 'text/event-stream',
            },
            body: JSON.stringify(body),
            signal: controller.signal,
          });

          if (!response.ok) {
            const detail = await response.text().catch(() => '');
            throw new Error(
              `${response.status} ${response.statusText}${detail ? ' - ' + detail : ''}`,
            );
          }
          if (!response.body) {
            throw new Error('Response body is empty; expected an SSE stream.');
          }

          const reader = response.body.getReader();
          const decoder = new TextDecoder();
          let buffer = '';

          while (!subscriber.closed) {
            const { value, done } = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, { stream: true });

            // SSE events are separated by a blank line. Pull as many complete
            // events out of the buffer as we have, leaving any partial event
            // for the next chunk.
            let boundary = buffer.indexOf('\n\n');
            while (boundary !== -1) {
              const frame = buffer.slice(0, boundary);
              buffer = buffer.slice(boundary + 2);
              const parsed = parseSseFrame(frame);
              if (parsed) subscriber.next(parsed);
              boundary = buffer.indexOf('\n\n');
            }
          }
          subscriber.complete();
        } catch (err) {
          if (controller.signal.aborted) {
            // Unsubscribe is normal completion, not an error.
            subscriber.complete();
          } else {
            subscriber.error(err);
          }
        }
      })();

      return () => controller.abort();
    });
  }
}

/**
 * Parse a single SSE frame. A frame looks like:
 *
 *   event: node_complete
 *   data: {"node":"draft_lesson","update":{...}}
 *
 * Returns null if the frame is missing required fields or the JSON is invalid.
 * We trust the event name from our own backend (the type cast at the end is
 * the place where wire-format drift would surface).
 */
function parseSseFrame(raw: string): LessonEvent | null {
  let eventName = '';
  let dataJson = '';

  for (const line of raw.split('\n')) {
    if (line.startsWith('event:')) {
      eventName = line.slice('event:'.length).trim();
    } else if (line.startsWith('data:')) {
      // SSE permits multi-line data (each data: line is joined with \n).
      // Our backend never emits multi-line data, but handle it correctly anyway.
      dataJson += (dataJson ? '\n' : '') + line.slice('data:'.length).trim();
    }
  }

  if (!eventName) return null;

  try {
    const data = dataJson ? JSON.parse(dataJson) : {};
    return { event: eventName, data } as LessonEvent;
  } catch {
    return null;
  }
}
