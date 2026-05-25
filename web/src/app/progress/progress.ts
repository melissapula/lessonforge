import { Component, computed, CUSTOM_ELEMENTS_SCHEMA, inject } from '@angular/core';
import { LessonStateService } from '../api/lesson-state.service';

@Component({
    selector: 'app-progress',
    standalone: true,
    imports: [],
    templateUrl: './progress.html',
    styleUrl: './progress.css',
    schemas: [CUSTOM_ELEMENTS_SCHEMA],
})
export class Progress {
    protected readonly state = inject(LessonStateService);

    protected heading(): string {
        const s = this.state.status();
        if (s === 'reviewing') return 'Awaiting your review';
        if (s === 'finalizing') return 'Finalizing…';
        return 'Generating lesson…';
    }

    /**
     * Quality gate is the only step with a real pass/fail outcome. When any
     * rubric dimension fails, the step renders in error (red) regardless of
     * whether it's in the past, current, or future relative to `current`.
     */
    protected readonly qualityFailed = computed(() => {
        const report = this.state.snapshot()?.quality_report;
        if (!report) return false;
        return (
            !report.alignment.passed ||
            !report.reading_level.passed ||
            !report.check_validity.passed
        );
    });

    /**
     * Maps the lesson lifecycle onto the stepper's `current` index.
     * Lifecycle status takes precedence over the last completed node so the
     * teacher-review pause and finalize-in-progress states are always reflected.
     */
    protected readonly currentStep = computed(() => {
        const status = this.state.status();
        if (status === 'finalizing') return 4;
        if (status === 'reviewing') return 3;

        const last = this.state.nodesCompleted().at(-1)?.node;
        switch (last) {
            case 'finalize':
                return 5;
            case 'quality_gate':
                return 3;
            case 'generate_mastery_check':
                return 2;
            case 'bump_revision':
                return 1;
            case 'draft_lesson':
                return 1;
            default:
                return 0;
        }
    });
}
