import { bootstrapApplication } from '@angular/platform-browser';
import { appConfig } from './app/app.config';
import { App } from './app/app';

// Register design system custom elements (side-effect imports).
import '@mfp-design-system/button';

bootstrapApplication(App, appConfig).catch((err) => console.error(err));
