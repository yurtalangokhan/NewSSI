/**
 * Jest configuration with separate projects for different test environments.
 *
 * We use two separate projects:
 * 1. "unit" - Node environment for pure unit tests (no DOM needed)
 * 2. "integration" - jsdom environment for React integration tests
 *
 * This allows us to run tests with the correct environment automatically
 * without needing @jest-environment comments in every test file.
 */

// Shared configuration
const sharedConfig = {
  preset: "ts-jest",
  setupFilesAfterEnv: ["<rootDir>/tests/setup/jest.setup.ts"],

  // Performance: Use 50% of CPU cores for parallel execution
  maxWorkers: "50%",

  moduleNameMapper: {
    // Mock CSS files (before path alias resolution)
    // CSS/static assets cannot be executed in tests and must be mocked
    "^@/.*\\.(css|less|scss|sass)$": "<rootDir>/tests/setup/mocks/cssMock.js",
    "^katex/dist/katex.min.css$": "<rootDir>/tests/setup/mocks/cssMock.js",
    "\\.(css|less|scss|sass)$": "<rootDir>/tests/setup/mocks/cssMock.js",
    // Mock static file imports
    "\\.(jpg|jpeg|png|gif|svg|woff|woff2|ttf|eot)$":
      "<rootDir>/tests/setup/fileMock.js",
    // Mock specific components that have complex dependencies
    "^@/providers/UserProvider$":
      "<rootDir>/tests/setup/mocks/components/UserProvider.tsx",
    // Path aliases (must come after specific mocks)
    "^@/(.*)$": "<rootDir>/src/$1",
    "^@tests/(.*)$": "<rootDir>/tests/$1",
    "^@opal$": "<rootDir>/lib/opal/src/index.ts",
    "^@opal/(.*)$": "<rootDir>/lib/opal/src/$1",
  },

  // "/vendor/" holds an unmodified Langflow reference copy (see
  // vendor/langflow/NOTICE.md). It targets Vite + react-router and does not
  // compile here; it exists for diffing ported files against their origin.
  testPathIgnorePatterns: [
    "/node_modules/",
    "/tests/e2e/",
    "/.next/",
    "/vendor/",
  ],

  // Transform ES Modules in node_modules to CommonJS for Jest compatibility
  // Add packages here when you encounter: "SyntaxError: Unexpected token 'export'"
  // These packages ship as ESM and need to be transformed to work in Jest
  transformIgnorePatterns: [
    "/node_modules/(?!(" +
      [
        // Auth & Security
        "jose",
        // UI Libraries
        "@radix-ui",
        "@headlessui",
        "@phosphor-icons",
        // Flow canvas (P4) — ships ESM ("@xyflow/react" itself needed no
        // entry here — its build is already jest-compatible, confirmed by
        // Task 20's xyflowLoads.test.tsx passing with no config change)
        "react-hotkeys-hook",
        // Testing & Mocking
        "msw",
        "until-async",
        // Markdown & Syntax Highlighting
        "react-markdown",
        "linguist-languages",
        "remark-.*", // All remark packages
        "rehype-.*", // All rehype packages
        "unified",
        "lowlight",
        "highlight\\.js",
        // Markdown Utilities
        "bail",
        "is-plain-obj",
        "trough",
        "vfile",
        "vfile-.*", // All vfile packages
        "unist-.*", // All unist packages
        "mdast-.*", // All mdast packages
        "hast-.*", // All hast packages
        "hastscript",
        "micromark.*", // All micromark packages
        "decode-named-character-reference",
        "character-entities",
        "devlop",
        "comma-separated-tokens",
        "property-information",
        "space-separated-tokens",
        "html-void-elements",
        "html-url-attributes",
        "aria-attributes",
        "web-namespaces",
        "svg-tag-names",
        "style-to-object",
        "inline-style-parser",
        "ccount",
        "escape-string-regexp",
        "markdown-table",
        "longest-streak",
        "zwitch",
        "trim-lines",
        "stringify-entities",
        "estree-.*", // All estree packages
      ].join("|") +
      ")/)",
  ],

  transform: {
    "^.+\\.(t|j)sx?$": [
      "ts-jest",
      {
        // Performance: Disable type-checking in tests (types are checked by tsc)
        isolatedModules: true,
        tsconfig: {
          jsx: "react-jsx",
          // Allow ts-jest to process JavaScript files from node_modules
          allowJs: true,
        },
      },
    ],
  },

  // Performance: Cache results between runs
  cache: true,
  cacheDirectory: "<rootDir>/.jest-cache",

  collectCoverageFrom: [
    "src/**/*.{ts,tsx}",
    "!src/**/*.d.ts",
    "!src/**/*.stories.tsx",
  ],

  coveragePathIgnorePatterns: ["/node_modules/", "/tests/", "/.next/"],

  // Performance: Clear mocks automatically between tests
  clearMocks: true,
  resetMocks: false,
  restoreMocks: false,
};

module.exports = {
  projects: [
    {
      displayName: "unit",
      ...sharedConfig,
      testEnvironment: "node",
      testMatch: [
        // Pure unit tests that don't need DOM
        "**/src/**/codeUtils.test.ts",
        "**/src/lib/**/*.test.ts",
        "**/src/app/**/services/*.test.ts",
        "**/src/app/**/utils/*.test.ts",
        "**/src/app/**/hooks/*.test.ts", // Pure packet processor tests
        "**/src/app/**/renderers/**/*.test.ts", // Pure timeline renderer state helpers
        // Pure timeline parsing helpers (node-type classification, stage
        // ordering) — no DOM. The timeline's component tests sit alongside
        // as .test.tsx and belong to the "integration" project below.
        "**/src/app/**/timeline/**/*.test.ts",
        "**/src/refresh-components/**/*.test.ts",
        "**/src/sections/**/*.test.ts",
        // Next.js route handlers (no DOM needed) — P4 Task 28's new
        // /api/flow-components proxy and the existing catch-all's own
        // coverage-confirmation test.
        "**/src/app/api/**/*.test.ts",
        "**/src/refresh-components/**/*.test.ts",
        // Flow-canvas pure-logic tests (port triage, handle types, FlowSpec
        // serialization) — no DOM needed. Component tests live alongside as
        // .test.tsx and are picked up by the "integration" project below.
        "**/src/components/flow-canvas/**/*.test.ts",
        // Add more patterns here as you add more unit tests
      ],
    },
    {
      displayName: "integration",
      ...sharedConfig,
      testEnvironment: "jsdom",
      testMatch: [
        // React component integration tests
        "**/src/app/**/*.test.tsx",
        "**/src/components/**/*.test.tsx",
        "**/src/hooks/**/*.test.tsx",
        "**/src/lib/**/*.test.tsx",
        "**/src/providers/**/*.test.tsx",
        "**/src/refresh-components/**/*.test.tsx",
        // P4 Task 28's mount point (flow-vs-form mode branch).
        "**/src/refresh-pages/**/*.test.tsx",
        "**/src/sections/input/**/*.test.tsx",
        "**/src/sections/AppHealthBanner.test.tsx",
        // Flow list surface: FlowCard, FlowSettingsModal (agents/flows split).
        "**/src/sections/cards/**/*.test.tsx",
        "**/src/sections/modals/**/*.test.tsx",
        // Add more patterns here as you add more integration tests
      ],
    },
  ],
};
