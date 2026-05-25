import { Component, CUSTOM_ELEMENTS_SCHEMA, inject, signal } from '@angular/core';
import { FormControl, ReactiveFormsModule, Validators } from '@angular/forms';
import { LessonStateService } from '../api/lesson-state.service';
import { MfpTextareaValueAccessor } from '../shared/mfp-textarea.directive';

@Component({
    selector: 'app-review',
    standalone: true,
    imports: [ReactiveFormsModule, MfpTextareaValueAccessor],
    templateUrl: './review.html',
    styleUrl: './review.css',
    schemas: [CUSTOM_ELEMENTS_SCHEMA],
})
export class Review {
    protected readonly state = inject(LessonStateService);
    protected readonly showRevisePanel = signal(false);
    protected readonly notes = new FormControl('', {
        nonNullable: true,
        validators: [Validators.required, Validators.minLength(4)],
    });

    protected approve(): void {
        this.state.decide({ decision: 'approve' });
    }

    protected reject(): void {
        this.state.decide({ decision: 'reject' });
    }

    protected openRevise(): void {
        this.showRevisePanel.set(true);
    }

    protected submitRevise(): void {
        if (this.notes.invalid) return;
        this.state.decide({ decision: 'revise', notes: this.notes.value.trim() });
        this.showRevisePanel.set(false);
        this.notes.reset('');
    }

    protected cancelRevise(): void {
        this.showRevisePanel.set(false);
        this.notes.reset('');
    }
}
