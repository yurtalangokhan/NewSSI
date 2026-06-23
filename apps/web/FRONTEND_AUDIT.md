# Frontend Stabilization Audit

Use this checklist for each frontend stabilization batch. The goal is a dense,
stable Onyx admin console built from existing tokens and refresh/opal
components.

## Forbidden Pattern Checks

Run these from `apps/web` before and after a batch:

```sh
rg -l "<button\\b|<input\\b|<textarea\\b|<select\\b" src/app/admin src/components/admin src/refresh-pages/admin -g "*.tsx"
rg -l "\\bdark:" src/app/admin src/components/admin src/refresh-pages/admin -g "*.tsx" -g "*.ts"
rg -l "react-icons|lucide-react" src/app/admin src/components/admin src/refresh-pages/admin -g "*.tsx" -g "*.ts"
rg -l "<p\\b|<h[1-6]\\b" src/app/admin src/components/admin src/refresh-pages/admin -g "*.tsx"
rg -n "^import .* from ['\\\"]\\." src/app/admin src/components/admin src/refresh-pages/admin -g "*.tsx" -g "*.ts"
```

## Review Checklist

- Use `<Text>` for user-visible text and refresh/opal controls for buttons,
  inputs, selects, textareas, switches, and menus.
- Use existing color tokens only. Do not add `dark:` overrides.
- Use `@/` imports for app code and icons from the project icon system.
- Keep operational pages compact: stable toolbars, tables, filters, empty
  states, and action menus.
- Patch row-level mutation results into local cache where possible. Refresh the
  full list only when list membership changes.
- Use `useEffect` for external synchronization only, not for mirroring props
  into duplicate local state.
- Close every batch with `npm run types:check`, `npm run lint`, and targeted
  Prettier checks for changed files.
