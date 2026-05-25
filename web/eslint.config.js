// @ts-check
const eslint = require('@eslint/js');
const { defineConfig } = require('eslint/config');
const tseslint = require('typescript-eslint');
const angular = require('angular-eslint');

module.exports = defineConfig([
    {
        files: ['**/*.ts'],
        extends: [
            eslint.configs.recommended,
            tseslint.configs.recommended,
            tseslint.configs.stylistic,
            angular.configs.tsRecommended,
        ],
        processor: angular.processInlineTemplates,
        rules: {
            '@angular-eslint/directive-selector': [
                'error',
                {
                    type: 'attribute',
                    // 'app' for app-local directives, 'mfp' for bridge directives
                    // that attach to @mfp-design-system custom elements (e.g.
                    // ControlValueAccessor adapters under src/app/shared/).
                    prefix: ['app', 'mfp'],
                    style: 'camelCase',
                },
            ],
            '@angular-eslint/component-selector': [
                'error',
                {
                    type: 'element',
                    prefix: 'app',
                    style: 'kebab-case',
                },
            ],
        },
    },
    {
        // Bridge directives that attach Angular ControlValueAccessor to the
        // @mfp-design-system custom elements. They MUST select on the
        // element name (e.g. `mfp-select`), not an attribute selector, since
        // they bind to existing custom elements consumers already have in
        // their templates. The standard Angular directive-selector rule
        // assumes attribute selectors and doesn't apply here.
        files: ['src/app/shared/**/*.ts'],
        rules: {
            '@angular-eslint/directive-selector': 'off',
        },
    },
    {
        files: ['**/*.html'],
        extends: [angular.configs.templateRecommended, angular.configs.templateAccessibility],
        rules: {},
    },
]);
