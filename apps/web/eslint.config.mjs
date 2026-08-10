import nextVitals from "eslint-config-next/core-web-vitals";
import unusedImports from "eslint-plugin-unused-imports";
import i18next from "eslint-plugin-i18next";

export default [
  ...nextVitals,
  {
    plugins: {
      "unused-imports": unusedImports,
      i18next,
    },
    rules: {
      // Flags hardcoded JSX text/attribute strings that should go through t().
      // "warn" for now - there's an existing backlog (run `npm run i18n:lint`
      // for the more accurate, i18next-config-aware version of this check).
      "i18next/no-literal-string": [
        "warn",
        {
          markupOnly: true,
          ignoreAttribute: [
            "aria-label",
            "data-testid",
            "className",
            "styleName",
            "src",
            "href",
            "role",
            "type",
          ],
        },
      ],
      "@next/next/no-img-element": "off",
      "@next/next/no-html-link-for-pages": "warn",
      "react/display-name": "warn",
      "react/jsx-key": "warn",
      "react/no-unescaped-entities": "warn",
      "react-hooks/exhaustive-deps": "off",
      "react-hooks/immutability": "warn",
      "react-hooks/preserve-manual-memoization": "warn",
      "react-hooks/refs": "warn",
      "react-hooks/rules-of-hooks": "warn",
      "react-hooks/set-state-in-effect": "warn",
      "react-hooks/static-components": "warn",
      "react-hooks/purity": "warn",
      "react-hooks/use-memo": "warn",
      "no-unused-vars": "off",
      "@typescript-eslint/no-unused-vars": "off",
      "unused-imports/no-unused-imports": "warn",
      "unused-imports/no-unused-vars": [
        "warn",
        {
          vars: "all",
          varsIgnorePattern: "^_",
          args: "after-used",
          argsIgnorePattern: "^_",
          ignoreRestSiblings: true,
        },
      ],
    },
  },
];
