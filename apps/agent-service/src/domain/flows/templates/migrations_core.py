"""Core / control-flow template migrations.

The Router v1->v2 change (truthiness-of-a-key routes become operator
comparisons) is the migration registry's first real use; every template
change before it was additive and needed none.

Registered from ``get_registry()`` so production always has them and test
code that builds an isolated ``ComponentRegistry()`` stays unaffected.
"""

from __future__ import annotations

from typing import Any

from domain.flows.migrations import (
    register_handle_rename,
    register_migration,
    register_type_rename,
)


def _router_v1_to_v2(values: dict[str, Any]) -> dict[str, Any]:
    """Rewrite each route row from "this scratch key is truthy" to a compare.

    v1 row: ``{"condition": X, "route" | "label": Y}``
    v2 row: ``{"source": X, "operator": "is_truthy", "match_text": "", "route": Y}``

    ``is_truthy`` ignores ``match_text`` and reports ``bool(source)``, so the
    old rule — "take this branch when the scratch key X is truthy" — carries
    across unchanged. ``label`` is normalised to ``route`` here, which is why
    the compiler's transitional ``row.get("route") or row.get("label")``
    fallback is removed in the same phase.
    """
    new = dict(values)
    rows = new.get("routes")
    migrated: list[dict[str, Any]] = []
    if isinstance(rows, list):
        for row in rows:
            if not isinstance(row, dict):
                continue
            if "source" in row or "operator" in row:
                # Already a v2 row. A hand-authored spec can carry v2 rows and
                # still declare template_version 1 (easy to forget in JSON);
                # rewriting them would force every operator to is_truthy and
                # wipe match_text, after which the first row matches
                # everything. A genuine v1 row only ever has "condition".
                migrated.append(row)
                continue
            migrated.append(
                {
                    "source": row.get("condition", ""),
                    "operator": "is_truthy",
                    "match_text": "",
                    "route": row.get("route") or row.get("label") or "",
                }
            )
    new["routes"] = migrated
    return new


def _loop_v1_to_v2(values: dict[str, Any]) -> dict[str, Any]:
    """v1 Loop (counter while-loop) -> v2 Loop (foreach).

    In practice this never runs: ``migrate_spec`` renames a v1 ``Loop`` node
    to ``While`` first, keeping the counter semantics. It exists so the
    registry-wide "every version has a migration path" guard holds and so a
    hand-written v1 ``Loop`` that dodged the rename still lands on a sane
    foreach shape rather than crashing.
    """
    return {"items_source": ""}


def _smart_router_v1_to_v2(values: dict[str, Any]) -> dict[str, Any]:
    """v1 ``custom_prompt`` replaced the base prompt and used
    ``{input}`` / ``{categories}``; v2 is appended to it and uses Langflow's
    ``{input_text}`` / ``{routes}``.

    Only the placeholders can be carried automatically. The replace->append
    change cannot be: a v1 prompt now lands *after* the base prompt instead of
    instead of it. Both texts ask for the same thing — classify this message
    into one of these categories — so the outcome holds, and the design doc
    records the difference rather than pretending the migration is total.
    """
    new = dict(values)
    prompt = new.get("custom_prompt")
    if isinstance(prompt, str) and prompt:
        new["custom_prompt"] = prompt.replace("{input}", "{input_text}").replace(
            "{categories}", "{routes}"
        )
    return new


def _human_input_v1_to_v2(values: dict[str, Any]) -> dict[str, Any]:
    """``enable_fallback`` -> ``enable_unmatched``.

    Langflow's ``fallback`` is its *timeout* path — "taken when the answer
    arrives after the timeout window". Ours is taken when the answer matches
    no action, which Langflow's button UI cannot even produce. Different job,
    so a different name (the name-function bond); ``fallback`` stays reserved
    in case a real timeout ever arrives.

    The ``fallback`` handle on stored edges is renamed by the handle-rename
    registry, registered alongside this migration.
    """
    new = dict(values)
    if "enable_fallback" in new:
        new["enable_unmatched"] = bool(new.pop("enable_fallback"))
    return new


def register_core_migrations() -> None:
    """Register every Core / control-flow template migration."""
    register_migration("Router", 1, _router_v1_to_v2)
    register_migration("Loop", 1, _loop_v1_to_v2)
    register_migration("SmartRouter", 1, _smart_router_v1_to_v2)
    register_migration("HumanInput", 1, _human_input_v1_to_v2)
    register_handle_rename("HumanInput", 1, "fallback", "unmatched")
    # The counter while-loop kept its behaviour but lost the Loop name to
    # Langflow's foreach; a stored v1 Loop node becomes a While node.
    register_type_rename("Loop", 1, "While")
