import { Component, inject } from '@angular/core';
import { LessonStateService } from '../api/lesson-state.service';

const NODE_LABELS: Record<string, string> = {
    draft_lesson: 'Drafting lesson',
    generate_mastery_check: 'Generating mastery check',
    quality_gate: 'Running quality gate',
    bump_revision: 'Revising for quality',
    finalize: 'Finalizing approved lesson',
};

@Component({
    selector: 'app-progress',
    standalone: true,
    imports: [],
    templateUrl: './progress.html',
    styleUrl: './progress.css',
})
export class Progress {
    protected readonly state = inject(LessonStateService);

    protected nodeLabel(node: string): string {
        return NODE_LABELS[node] ?? node;
    }

    protected heading(): string {
        const s = this.state.status();
        if (s === 'reviewing') return 'Awaiting your review';
        if (s === 'finalizing') return 'Finalizing…';
        return 'Generating lesson…';
    }
}
