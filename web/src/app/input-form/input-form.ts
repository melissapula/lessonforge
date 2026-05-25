import { Component, computed, CUSTOM_ELEMENTS_SCHEMA, inject } from '@angular/core';
import { FormControl, FormGroup, ReactiveFormsModule, Validators } from '@angular/forms';
import { LessonStateService } from '../api/lesson-state.service';
import { GRADE_LEVELS, SUBJECTS, type GradeLevel, type Subject } from '../api/api.types';
import { MfpSelectValueAccessor } from '../shared/mfp-select.directive';
import { MfpTextareaValueAccessor } from '../shared/mfp-textarea.directive';

@Component({
    selector: 'app-input-form',
    standalone: true,
    imports: [ReactiveFormsModule, MfpSelectValueAccessor, MfpTextareaValueAccessor],
    templateUrl: './input-form.html',
    styleUrl: './input-form.css',
    schemas: [CUSTOM_ELEMENTS_SCHEMA],
})
export class InputForm {
    protected readonly state = inject(LessonStateService);
    protected readonly subjects = SUBJECTS;
    protected readonly gradeLevels = GRADE_LEVELS;

    protected readonly form = new FormGroup({
        objective: new FormControl('', {
            nonNullable: true,
            validators: [Validators.required, Validators.minLength(8)],
        }),
        grade_level: new FormControl<GradeLevel>('3rd grade', {
            nonNullable: true,
            validators: [Validators.required],
        }),
        subject: new FormControl<Subject>('ELA', {
            nonNullable: true,
            validators: [Validators.required],
        }),
    });

    protected readonly disabled = computed(() => this.state.isBusy());

    protected submit(): void {
        if (this.form.invalid) return;
        const v = this.form.getRawValue();
        this.state.startLesson({
            objective: v.objective.trim(),
            grade_level: v.grade_level,
            subject: v.subject,
        });
    }
}
