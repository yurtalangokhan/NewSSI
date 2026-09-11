import nextVitals from "eslint-config-next/core-web-vitals";
import unusedImports from "eslint-plugin-unused-imports";
import i18next from "eslint-plugin-i18next";

export default [
  {
    // Unmodified Langflow reference copy — see vendor/langflow/NOTICE.md.
    // Targets Vite + react-router + shadcn and is never built or imported.
    ignores: ["vendor/**"],
  },
  ...nextVitals,
  {
    plugins: {
      "unused-imports": unusedImports,
      i18next,
    },
    rules: {
      // Keep the main lint gate focused on blocking issues. Localization
      // coverage is tracked separately with `npm run i18n:lint`.
      "i18next/no-literal-string": "off",
      "@next/next/no-img-element": "off",
      "@next/next/no-html-link-for-pages": "off",
      "react/display-name": "off",
      "react/jsx-key": "off",
      "react/no-unescaped-entities": "off",
      "react-hooks/exhaustive-deps": "off",
      "react-hooks/immutability": "off",
      "react-hooks/preserve-manual-memoization": "off",
      "react-hooks/refs": "off",
      "react-hooks/rules-of-hooks": "off",
      "react-hooks/set-state-in-effect": "off",
      "react-hooks/static-components": "off",
      "react-hooks/purity": "off",
      "react-hooks/use-memo": "off",
      "no-unused-vars": "off",
      "@typescript-eslint/no-unused-vars": "off",
      "unused-imports/no-unused-imports": "off",
      "unused-imports/no-unused-vars": "off",
    },
  },
  {
    // The flow-canvas tree is new code and is fully on the design-system
    // tokens, so the two styling rules in AGENTS.md / docs/coding-standards.md
    // are enforced here rather than left to review. Colour tokens
    // (`bg-background-neutral-00`, `text-text-03`, `theme-green-05`, the
    // `note-*` sticky-note palette) already answer both themes, which is why
    // `dark:` must not appear. The rest of `src/` still carries pre-existing
    // Onyx violations; widen this `files` list as those areas are converted.
    //
    // The last two selectors are the i18n copy guard:
    // `i18next/no-literal-string` (installed version) only sees JSX text and
    // `i18next-cli` only sees strings already inside `t()`, so hardcoded copy
    // in `.ts` config/data modules and hook internals slips past both. These
    // catch it by targeting copy-bearing binding names; `mode:"all"` on this
    // tree is ~230 unrelated hits and unusable. Tests are excluded — mock
    // objects legitimately carry sentence literals.
    files: ["src/components/flow-canvas/**/*.{ts,tsx}"],
    ignores: [
      "src/components/flow-canvas/**/__tests__/**",
      "src/components/flow-canvas/**/*.test.{ts,tsx}",
    ],
    rules: {
      "no-restricted-syntax": [
        "error",
        {
          selector:
            "Literal[value=/(^|[\\s`'\"])dark:/]",
          message:
            "No `dark:` modifier. Colour tokens in tailwind-themes/ + colors.css already flip with the theme.",
        },
        {
          selector:
            "TemplateElement[value.raw=/(^|[\\s`'\"])dark:/]",
          message:
            "No `dark:` modifier. Colour tokens in tailwind-themes/ + colors.css already flip with the theme.",
        },
        {
          selector:
            "Literal[value=/(^|[\\s`'\"])(bg|text|border|ring|fill|stroke|caret|divide|outline|accent|placeholder|shadow|from|to|via)-(slate|gray|zinc|neutral|stone|red|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose)-[0-9]{2,3}/]",
          message:
            "Use a design-system colour token (e.g. bg-background-neutral-00, text-text-03, text-theme-green-05), not a built-in Tailwind colour.",
        },
        {
          selector:
            "TemplateElement[value.raw=/(^|[\\s`'\"])(bg|text|border|ring|fill|stroke|caret|divide|outline|accent|placeholder|shadow|from|to|via)-(slate|gray|zinc|neutral|stone|red|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose)-[0-9]{2,3}/]",
          message:
            "Use a design-system colour token (e.g. bg-background-neutral-00, text-text-03, text-theme-green-05), not a built-in Tailwind colour.",
        },
        {
          selector:
            "Property[key.name=/^(label|description|title|placeholder|tooltip|helperText|hint|message|heading|subheading|subtitle|caption|emptyState|confirmLabel|cancelLabel|ariaLabel|error)$/] > Literal[value=/[A-Za-z][a-z]+ +[A-Za-z]/]",
          message:
            "Hardcoded UI copy in an object property — route it through t() (see AGENTS.md i18n).",
        },
        {
          // Direct initializer only (`const msg = "Some copy"`) — a descendant
          // match would also flag the English default string inside `t(k, "…")`.
          selector:
            "VariableDeclarator[id.name=/^(errDetail|msg|detail|message|label|title|placeholder|tooltip|heading|notice|banner)$/] > Literal[value=/[A-Za-z][a-z]+ +[A-Za-z]/]",
          message:
            "Hardcoded UI copy in a variable — route it through t() (see AGENTS.md i18n).",
        },
      ],
    },
  },
];
