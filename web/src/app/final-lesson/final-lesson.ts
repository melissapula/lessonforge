import { Component, CUSTOM_ELEMENTS_SCHEMA, inject, signal } from '@angular/core';
import { LessonStateService } from '../api/lesson-state.service';
import type { FinalLesson as FinalLessonType } from '../api/api.types';

@Component({
    selector: 'app-final-lesson',
    standalone: true,
    imports: [],
    templateUrl: './final-lesson.html',
    styleUrl: './final-lesson.css',
    schemas: [CUSTOM_ELEMENTS_SCHEMA],
})
export class FinalLesson {
    protected readonly state = inject(LessonStateService);
    protected readonly copied = signal(false);

    protected async copy(): Promise<void> {
        const lesson = this.state.finalLesson();
        if (!lesson) return;
        try {
            await navigator.clipboard.writeText(formatLessonText(lesson));
            this.copied.set(true);
            setTimeout(() => this.copied.set(false), 2000);
        } catch {
            // navigator.clipboard may be unavailable (insecure context); noop.
        }
    }

    protected reset(): void {
        this.state.reset();
    }
}

function formatLessonText(lesson: FinalLessonType): string {
    const out: string[] = [];
    out.push(lesson.title);
    out.push('');
    out.push('LESSON');
    out.push(lesson.lesson.explanation);
    out.push('');
    out.push('WORKED EXAMPLES');
    lesson.lesson.worked_examples.forEach((ex, i) => {
        out.push(`${i + 1}. ${ex.prompt}`);
        out.push(`   ${ex.solution}`);
    });
    out.push('');
    out.push('EXTENSION ACTIVITY');
    out.push(lesson.lesson.extension_activity);
    out.push('');
    out.push('MASTERY CHECK');
    lesson.mastery_check.questions.forEach((q, i) => {
        out.push(`${i + 1}. ${q.question}`);
        out.push(`   Answer: ${q.answer}`);
        out.push(`   (${q.rationale})`);
    });
    return out.join('\n');
}
