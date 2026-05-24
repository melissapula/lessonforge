import { Component, inject, signal } from '@angular/core';
import { LessonStateService } from './api/lesson-state.service';
import { InputForm } from './input-form/input-form';
import { Progress } from './progress/progress';
import { Review } from './review/review';
import { FinalLesson } from './final-lesson/final-lesson';

@Component({
    selector: 'app-root',
    standalone: true,
    imports: [InputForm, Progress, Review, FinalLesson],
    templateUrl: './app.html',
    styleUrl: './app.css',
})
export class App {
    protected readonly title = signal('LessonForge');
    protected readonly state = inject(LessonStateService);
}
