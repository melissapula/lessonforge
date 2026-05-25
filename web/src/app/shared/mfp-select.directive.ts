import { Directive, ElementRef, HostListener, forwardRef, inject } from '@angular/core';
import { ControlValueAccessor, NG_VALUE_ACCESSOR } from '@angular/forms';

type MfpSelectElement = HTMLElement & { value: string; disabled: boolean };
type MfpChangeEvent = CustomEvent<{ value: string }>;

@Directive({
    selector: 'mfp-select[formControlName], mfp-select[formControl], mfp-select[ngModel]',
    standalone: true,
    providers: [
        {
            provide: NG_VALUE_ACCESSOR,
            useExisting: forwardRef(() => MfpSelectValueAccessor),
            multi: true,
        },
    ],
})
export class MfpSelectValueAccessor implements ControlValueAccessor {
    private readonly host = inject(ElementRef<MfpSelectElement>);
    private onChange: (value: string) => void = () => undefined;
    private onTouched: () => void = () => undefined;

    @HostListener('change', ['$event'])
    handleChange(event: Event): void {
        const value =
            (event as MfpChangeEvent).detail?.value ?? this.host.nativeElement.value ?? '';
        this.onChange(value);
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
