import { bootstrapApplication } from '@angular/platform-browser';
import { appConfig } from './app/app.config';
import { App } from './app/app';

// Register design system custom elements (side-effect imports).
import '@mfp-design-system/badge';
import '@mfp-design-system/button';
import '@mfp-design-system/card';
import '@mfp-design-system/form-field';
import '@mfp-design-system/modal';
import '@mfp-design-system/select';
import '@mfp-design-system/stepper';
import '@mfp-design-system/textarea';

bootstrapApplication(App, appConfig).catch((err) => console.error(err));
