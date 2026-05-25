import { Directive, ElementRef, HostListener, forwardRef, inject } from '@angular/core';
import { ControlValueAccessor, NG_VALUE_ACCESSOR } from '@angular/forms';

type MfpTextareaElement = HTMLElement & { value: string; disabled: boolean };
type MfpInputEvent = CustomEvent<{ value: string }>;

@Directive({
    selector: 'mfp-textarea[formControlName], mfp-textarea[formControl], mfp-textarea[ngModel]',
    standalone: true,
    providers: [
        {
            provide: NG_VALUE_ACCESSOR,
            useExisting: forwardRef(() => MfpTextareaValueAccessor),
            multi: true,
        },
    ],
})
export class MfpTextareaValueAccessor implements ControlValueAccessor {
    private readonly host = inject(ElementRef<MfpTextareaElement>);
    private onChange: (value: string) => void = () => undefined;
    private onTouched: () => void = () => undefined;

    @HostListener('input', ['$event'])
    handleInput(event: Event): void {
        const value = (event as MfpInputEvent).detail?.value ?? this.host.nativeElement.value ?? '';
        this.onChange(value);
    }

    @HostListener('change')
    handleChange(): void {
        this.onTouched();
    }

    writeValue(value: string | null): void {
        this.host.nativeElement.value = value ?? '';
    }

    registerOnChange(fn: (value: string) => void): void {
        this.onChange = fn;
    }

    registerOnTouched(fn: () => void): void {
        this.onTouched = fn;
    }

    setDisabledState(isDisabled: boolean): void {
        this.host.nativeElement.disabled = isDisabled;
    }
}
