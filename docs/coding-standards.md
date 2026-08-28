# Coding Standards

## Python standards (all services)

### Formatting & linting

| Tool | Config location | Line length | Command |
|------|----------------|-------------|---------|
| ruff (linter) | `pyproject.toml` or `ruff.toml` | 100 (88 for rag-service) | `make lint` / `make fix` |
| ruff (formatter) | same file | same | `make format` |
| mypy (type checker) | `pyproject.toml` | — | `make typecheck` |

**Conventions:**
- `ruff` replaces `black` + `isort` + `flake8`. Never use those tools.
- `make fix` auto-fixes what ruff can fix. Run it before `make lint`.
- `make validate` runs lint → typecheck → test in that order.
- Rag-service uses `ruff select = ["ALL"]` — the strictest ruleset. Many per-file ignores in `pyproject.toml`.

### Layered architecture

```
api/routes/*.py  →  controller/*.py  →  service/*.py  →  repository/*.py
```

| Layer | Responsibility | Never |
|-------|---------------|-------|
| **Route** | Parse HTTP params, call controller, return response | Business logic, DB calls |
| **Controller** | Orchestrate services, map domain errors → HTTP statuses | Business logic, DB calls |
| **Service** | Pure domain logic. Raise `ValueError`, `NotFoundError`, etc. | HTTP exceptions |
| **Repository** | SQLAlchemy async session, auto-commit | Business logic |

### Architecture & code-quality gate

A deterministic, **blocking** gate enforces the architecture principles on every
commit and push. It is implemented by `scripts/quality/check_architecture.py`
and wired into `scripts/quality/check.sh` (which the pre-commit and pre-push git
hooks call). Committed and pushed code must obey these objective rules.

The philosophical basis is `docs/oop-solid-architecture.md` (SOLID, OOP
fundamentals, clean architecture). Read that before coding or reviewing.

**Modes**

- `--changed` (used by the hooks): checks only the files in the current diff.
  Pre-existing hotspots do **not** block unless you modify them. **HARD
  findings fail the gate** (non-zero exit).
- `--all` (used by `make architecture-check`): scans the whole tree, report-only
  (never fails). Use for trend/baseline reports.

**HARD rules (blocking in `--changed`)**

| # | Rule | Applies to |
|---|------|-----------|
| 1 | No HTTP-framework imports (`fastapi`, `starlette`, `UploadFile`, `HTTPException`, `status`, `Request`, `Response`) in `service/` or `domain/` | Python services |
| 2 | No `Repository`/`Client`/`Gateway` class defined outside its layer (`service/`, `controller/`, `api/`, `core/` are not repository/integration layers) | Python services |
| 3 | No `domain/` → `integrations`/`core.db`/`repository` dependency (inversion); no `langconnect/database/` → `services` import | Python services |
| 4 | No generic bucket module names (`Utils`, `Helpers`) unless a documented shim | Python services |
| 5 | No raw HTML/UI primitives (`<p>`, `<h1>`–`<h6>`, `<input>`, `<textarea>`, `<button>`, `<img>`) outside `@/refresh-components`/`@opal` | Web (excludes tests/snapshots) |
| 6 | No banned icon imports (`lucide-react`, `react-icons`, `@phosphor-icons/react`); use `@/icons` | Web (excludes tests/snapshots) |

**WARN heuristics (never blocking)**: module LOC (backend > 500, web > 1000),
function length > 50 lines, approximate cyclomatic complexity > 10.

**Quality score**

The hook runner also converts HARD and WARN findings into a 0-100 quality
score. HARD findings always fail threshold mode. WARN findings are weighted by
category and capped so existing codebase debt cannot collapse the score to zero
by volume alone.

`quality-staged` and `quality-push` fail when the changed-file score is below
`QUALITY_SCORE_MIN`, which defaults to `80`. Use `make quality-score` to score
the full tracked tree in report-only mode. Agents use the full-tree report to
find the next improvement backlog, but existing full-tree WARN findings do not
block unrelated pushes.

WARN scoring uses these principles:

- Architecture-adjacent WARN findings carry more weight than size or complexity
  heuristics.
- Test-file WARN findings carry less weight than production-file findings.
- Total WARN penalty is capped at 18 points, so a branch with many WARN
  findings can still pass at grade B while clearly showing improvement work.
- Fixing WARN findings raises the score above the minimum and is the preferred
  way to move a branch from passable to high quality.

**Run it locally**

```sh
make architecture-check          # full-tree report
make quality-score               # full-tree score, report-only trend metric
QUALITY_FILES="apps/agent-service/src/service/Foo.py" \
  python3 scripts/quality/check_architecture.py --changed   # one file
QUALITY_FILES="apps/agent-service/src/service/Foo.py" \
  python3 scripts/quality/score.py --changed --min-score 80 # one-file score
```

### Domain exceptions

Define all domain exceptions in `core/exceptions.py`:
```python
class NotFoundError(Exception): ...
class ConflictError(Exception): ...
class ForbiddenError(Exception): ...
```

Controllers catch these and convert to HTTP exceptions. Services never raise HTTP exceptions.

### Singleton pattern

```python
class MyService:
    _instance = None

def get_my_service() -> MyService:
    if MyService._instance is None:
        MyService._instance = MyService()
    return MyService._instance
```

### Config pattern

```python
from pydantic_settings import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):
    model_config = {"env_file": ".env"}
    database_url: str = ...

@lru_cache
def get_settings() -> Settings:
    return Settings()
```

### Async SQLAlchemy

```python
class BaseRepository:
    def __init__(self, session_factory: Callable):
        self._session = session_factory

    @asynccontextmanager
    async def _session(self):
        async with self._session() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
```

### Naming conventions

| Type | Convention | Example |
|------|-----------|---------|
| Module/package | `snake_case` | `user_service.py` |
| Class | `PascalCase` | `UserService` |
| Function/method | `snake_case` | `get_user_by_id()` |
| Variable | `snake_case` | `user_id` |
| Constant | `UPPER_SNAKE_CASE` | `MAX_RETRIES` |
| Private helper | `_prefix` | `_to_dict()` |
| Type alias | `PascalCase` | `UserDict = dict[str, Any]` |

### Testing

- `pytest` with `asyncio_mode = "auto"` — test functions are `async def`
- No `__init__.py` needed in test directories
- Fixtures in `conftest.py` at the appropriate level
- Mock HTTP with `httpx` responses or `pytest-httpx`
- Test files named `test_*.py`

**Rag-service:** Ruff select `["ALL"]` means strict lint enforcement in tests too. Per-file ignores in `pyproject.toml` relax `S101` (bare asserts), `ARG` (unused arguments), `D103` (test docstrings) for test files.

### Code clarity rules (from clean-code practices)

- **Mysterious names**: Function/variable names must reveal intent. `get_data()` is not acceptable — `get_user_permissions()` is.
- **Duplicate code**: Extract repeated logic into a shared function. If it appears in 3+ places, it belongs in the service layer.
- **Function length**: Keep functions under 50 lines. Extract helper methods.
- **Single responsibility**: One function = one job. A function named `create_user()` should not also send emails.
- **Deep modules**: A module's interface should be simpler than its implementation. If the route handler is as complex as the service it calls, the module is too shallow.
- **No speculative generality**: Don't add parameters, hooks, or abstractions for needs the current feature doesn't have. YAGNI.
- **Type annotations**: All function signatures must have type annotations. `mypy` enforces this.

---

## TypeScript/React standards (web)

### Imports

- Always absolute with `@/` prefix: `import { Button } from "@/components/ui/button"`
- Never relative imports: `../../components/`
- Path aliases: `@/*` → `src/`, `@tests/*` → `tests/`, `@opal/*` → `lib/opal/src/*`

### Components

```typescript
interface Props {
  userId: string;
  showActions?: boolean;
}

function UserProfile({ userId, showActions = false }: Props) {
  return <div>User Profile</div>;
}
```

- `function Component()` not arrow functions
- Props extracted into named `interface Props`
- One component per file

### Styling

| Standard | Rule |
|----------|------|
| Class names | `cn()` from `@/lib/utils`, never raw strings |
| Dark mode | Never `dark:` modifier. Colors defined in `colors.css` |
| Colors | Custom tokens only: `bg-background-neutral-03`, `text-02`, `border-01` |
| Icons | Only `src/icons/` — never react-icons, lucide, phosphor-icons |
| Text | `<Text>` from `@/refresh-components/texts/Text`, never `<p>`/`<h1>` |
| Forms | Components from `@/refresh-components/` or `@opal/`, never raw `<input>`/`<button>` |
| Spacing | Prefer `padding` over `margin` for layout spacing |

### Data fetching

```typescript
import useSWR from "swr";

function UserList() {
  const { data, error } = useSWR("/api/users");
  // fetch at component level, not parent
}
```

- Use `useSWR` (swr library)
- Fetch at component level, not at parent and pass down
- Display skeleton/placeholder while loading

### Testing

```typescript
import { render, screen, setupUser } from "@tests/setup/test-utils";

test("renders", async () => {
  const user = setupUser();  // not userEvent.setup()
  render(<MyComponent />);
  await user.click(screen.getByText("Submit"));
});
```

- Co-located tests alongside source
- Use `setupUser()` from test utils, not raw `userEvent.setup()`
- Mock HTTP: `jest.spyOn(global, "fetch")` — comment which endpoint
- Two Jest projects: unit (node) + integration (jsdom)

### File organization

```
src/
├── app/           # App Router pages
├── components/    # Shared components
├── hooks/         # One hook per file
├── icons/         # ONLY icon SVGs
├── lib/           # Utilities
├── providers/     # React context providers
├── layouts/       # Layout components
├── refresh-components/  # Onyx design system
└── refresh-pages/       # Page-level components
```

---

## Code smells to watch for (code-review baseline)

Based on Fowler's _Refactoring_ (ch.3). Review diffs against these:

| Smell | What to look for | How to fix |
|-------|-----------------|------------|
| Mysterious Name | Name doesn't reveal what the function/type does | Rename; if no honest name emerges, design is murky |
| Duplicated Code | Same logic shape in multiple hunks/files | Extract shared function |
| Feature Envy | Method reaches into another object's data more than its own | Move method to the data it envies |
| Data Clumps | Same fields/params keep travelling together | Bundle into one type |
| Primitive Obsession | String/primitive used where a domain type belongs | Create the domain type |
| Repeated Switches | Same switch/if-cascade on same type in multiple places | Polymorphism or shared map |
| Shotgun Surgery | One logical change needs edits in many files | Consolidate related code into one module |
| Speculative Generality | Abstractions added for needs not in the spec | Delete; inline until a real need appears |
| Long Parameter List | Function takes too many params | Bundle related params into an object |
| Message Chains | Long `a.b().c().d()` navigation | Hide walk behind one method |
| Middle Man | Class mostly delegates to another | Cut it, call the real target |
| Refused Bequest | Subclass ignores most of what it inherits | Composition over inheritance |

---

## General principles

1. **The repo's documented standards override the baseline.** If a documented convention endorses something a smell would flag, follow the convention.
2. **Skip what tooling already enforces.** Don't manually flag what ruff/flake8/mypy/ESLint already catch.
3. **Smells are judgement calls, not hard violations.** Flag them as heuristics.
4. **Prefer readable code over clever code.** If junior developers can't understand it in 30 seconds, it's too clever.
5. **Avoid `TODO` and `FIXME` in committed code.** If it's not done, don't commit it.
