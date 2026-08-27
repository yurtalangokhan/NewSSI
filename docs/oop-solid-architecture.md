# OOP, SOLID, and Clean Architecture

Canonical reference for object-oriented design, the SOLID principles, and clean
architecture as applied in this monorepo. The deterministic gate in
`scripts/quality/check_architecture.py` enforces the objective subset of these
rules on every commit and push (see `docs/coding-standards.md`, section
"Architecture & code-quality gate"). This document explains the *why*; the
gate enforces the *what*.

Read this before writing or reviewing code. The layered FastAPI architecture
(`api/routes → controller → service → repository`) described in
`docs/architecture-overview.md` and `docs/coding-standards.md` is a
consequence of these principles, not a separate concern.

## SOLID

### S — Single Responsibility Principle

A module, class, or function should have one reason to change. One job, one
owner, one axis of change.

- **Do:** split `create_user()` from `send_welcome_email()`; put email in its
  own adapter.
- **Don't:** let one class own realm config, user lifecycle, role sync, and
  token grants at once.
- **Heuristic:** if you struggle to name a class honestly, it has more than one
  responsibility.

### O — Open/Closed Principle

Software entities should be open for extension but closed for modification. Add
behavior through new types or overrides, not by editing stable code.

- **Do:** define a `BaseToolCategory` ABC and add a new category by subclassing;
  register it dynamically (as tools-service does).
- **Don't:** keep editing a central `if tool == "x":` dispatcher every time a
  tool is added.
- **Heuristic:** repeated `switch`/`if` on the same type across the codebase is
  a violation.

### L — Liskov Substitution Principle

Subtypes must be substitutable for their base types without altering correctness.

- **Do:** any `BaseRepository` subclass honors the same query/commit contract.
- **Don't:** a subclass that ignores or overrides most of what it inherits
  (refused bequest) — prefer composition.
- **Heuristic:** if callers must `isinstance`-check a subtype to avoid breaking,
  the hierarchy is wrong.

### I — Interface Segregation Principle

Clients should not depend on interfaces they do not use. Prefer small, focused
interfaces over one do-everything contract.

- **Do:** small role/permission port interfaces; a `BaseToolCategory` with only
  what every tool needs.
- **Don't:** a 30-method `Service` interface that most callers never touch.
- **Heuristic:** a fat interface that forces empty implementations is a
  violation.

### D — Dependency Inversion Principle

High-level policy must not depend on low-level details. Both depend on
abstractions. Details (DB, HTTP, external systems) plug in at the edge.

- **Do:** domain code depends on a repository *port*; the SQLAlchemy
  implementation lives in the infrastructure layer.
- **Don't:** `domain/` importing concrete `integrations`, `core.db`, or
  `repository` implementations.
- **Heuristic:** arrows point inward. The farther in, the more abstract.

## OOP Fundamentals

- **Encapsulation:** expose behavior, hide state. Methods, not public fields,
  guard invariants.
- **Composition over inheritance:** build objects from collaborators instead of
  deep `is-a` chains. Favor the refused-bequest fix.
- **Law of Demeter:** a module talks to its immediate collaborators, not to
  strangers via long `a.b().c().d()` chains. Hide the walk behind one method.
- **Tell, don't ask:** objects do work when told, rather than handing their
  state out for someone else to mutate.

## Clean Architecture

- **Dependency direction points inward.** Routes → controllers → services →
  repositories/ports. Outer layers know inner; inner never knows outer.
- **Delivery adapters stay at the edge.** FastAPI `UploadFile`, `HTTPException`,
  `Request`/`Response`, `status` belong in the API/controller boundary, not in
  domain services.
- **Ports & adapters (hexagonal):** domain defines ports (interfaces); the
  framework, DB, and external clients are adapters plugged in at the boundary.
- **Deep modules:** the interface should be simpler than the implementation. A
  route handler as complex as the service it calls is too shallow — push logic
  down.
- **Small cohesive modules over utility buckets:** split by domain capability,
  not a generic `Utils`/`Helpers` category. Names must explain ownership.
- **Delete only with evidence:** do not remove files on size or name alone; use
  import scans, registry checks, and tests first (see deletion policy in the
  codebase-simplification spec).

## Anti-Pattern Catalog

| Anti-pattern | Signal | Fix |
|---|---|---|
| God class / module | One file owns many unrelated responsibilities (>~500 LOC) | Split by domain capability |
| Feature envy | A method reaches into another object's data more than its own | Move the method onto the data it envies |
| Layer leakage | `fastapi`/`UploadFile`/`status` in `service/` or `domain/` | Move to API/controller boundary |
| Wrong-layer placement | `Repository`/`Client`/`Gateway` classes in `service/` or `controller/` | Move to `repository/`/`integrations/` |
| Dependency inversion | `domain/` imports `integrations`/`core.db`/`repository` | Introduce a port; depend on the abstraction |
| Utility bucket | `Utils.py`, `Helpers.py` | Rename to a domain module; split |
| Anemic domain | domain types are bags of getters/setters; logic lives in services | Move behavior into the domain type |
| Refused bequest | subclass overrides/ignores most of the parent | Composition over inheritance |
| Primitive obsession | string/int stands in for a domain concept | Introduce a small domain type |

## Quick-Reference Checklist (for implementers and reviewers)

1. Does each module/class have one responsibility? (S)
2. Can behavior extend without editing stable code? (O)
3. Are subtypes substitutable? (L)
4. Are interfaces small and focused? (I)
5. Does the domain depend only on abstractions, never on `integrations`/`core.db`/concrete `repository`? (D)
6. Do delivery types (`UploadFile`, `HTTPException`, `status`) live only at the API edge?
7. Are repositories/clients/gateways in their own layers, not in `service/`/`controller/`?
8. Are names domain-specific, not `Utils`/`Helpers` buckets?
9. Are modules cohesive and below the size threshold (warn at 500 LOC backend / 1000 LOC web)?
10. Does the change keep behavior facades and shims only where migration safety requires, with a removal note?

The gate enforces items 5–8 as **HARD** rules and items 9 as **WARN**
heuristics. Items 1–4 and 10 are judgement calls reviewed by humans/agents.
