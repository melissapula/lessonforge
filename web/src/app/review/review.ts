import { Component, inject, signal } from '@angular/core';
import { FormControl, ReactiveFormsModule, Validators } from '@angular/forms';
import { LessonStateService } from '../api/lesson-state.service';

@Component({
    selector: 'app-review',
    standalone: true,
    imports: [ReactiveFormsModule],
    templateUrl: './review.html',
    styleUrl: './review.css',
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
