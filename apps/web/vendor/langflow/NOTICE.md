# Vendored Langflow frontend — reference copy

This directory contains a **partial, unmodified copy** of the Langflow
frontend source, vendored as a **reading and diffing reference** for the
agent flow-canvas port (project phase P4).

## Provenance

| | |
|---|---|
| Upstream | <https://github.com/langflow-ai/langflow> |
| Commit | `3ec070e99af5196fdb187546de2c4f29a35ebe46` |
| Branch | `main` |
| Vendored on | 2026-08-06 |
| Upstream path | `src/frontend/src/` |
| License | **MIT** — full text in [`LICENSE`](./LICENSE) |

## What is here

Only the canvas-relevant subtrees were vendored, not the whole Langflow
frontend:

| Path | Upstream path |
|---|---|
| `CustomNodes/` | `src/frontend/src/CustomNodes/` |
| `CustomEdges/` | `src/frontend/src/CustomEdges/` |
| `pages/FlowPage/` | `src/frontend/src/pages/FlowPage/` |
| `stores/` | `src/frontend/src/stores/` |
| `utils/` | `src/frontend/src/utils/` |
| `types/` | `src/frontend/src/types/` |
| `components/core/parameterRenderComponent/` | same |

## This code does not build, and is not meant to

It is **excluded from the Next.js build and from TypeScript path
resolution.** It targets Vite + react-router + shadcn-ui and will not
compile inside this app. Nothing under `apps/web/src/` may import from
here — a test enforces that boundary.

Its purpose is to let ported files be diffed against their origin, so that
an upstream improvement can be re-diffed later and so attribution has a
concrete, inspectable subject.

## Attribution in ported files

Ported code lives in `apps/web/src/components/flow-canvas/` and carries a
header naming its origin, per MIT's "substantial portions" clause:

```ts
// Ported from Langflow (MIT) — src/frontend/src/utils/reactflowUtils.ts
// Upstream: https://github.com/langflow-ai/langflow @ 3ec070e9
// Adapted for Onyx: refresh-components primitives, @opal icons, FlowSpec types.
```

## Refreshing this copy

```sh
git clone --filter=blob:none --sparse --depth 1 \
  https://github.com/langflow-ai/langflow.git lf
cd lf && git config core.longpaths true
git sparse-checkout set src/frontend/src
```

Clone to a **short path** (e.g. `~/lf`) — Langflow has paths that exceed
Windows' 260-character limit even with `core.longpaths` enabled when the
destination is already deep.
