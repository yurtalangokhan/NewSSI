"""Truth table for service.memory_flags.resolve_memory_flags."""

from __future__ import annotations

import pytest

from service.memory_flags import resolve_memory_flags


@pytest.mark.parametrize(
    ("recall", "extract", "participates", "agent_extract", "expected"),
    [
        # User recall off → nothing, regardless of agent / extract.
        (False, True, True, True, (False, False)),
        (False, False, True, True, (False, False)),
        (False, True, False, True, (False, False)),
        # Recall on but the agent does not participate → nothing.
        (True, True, False, True, (False, False)),
        # Recall on, agent participates → recall on; save follows the update flag.
        (True, True, True, True, (True, True)),
        (True, False, True, True, (True, False)),
        # Agent-level extract label can still veto the save.
        (True, True, True, False, (True, False)),
        # Update on is inert while recall is off.
        (False, True, True, True, (False, False)),
    ],
)
def test_resolve_memory_flags(recall, extract, participates, agent_extract, expected):
    assert (
        resolve_memory_flags(
            user_recall_enabled=recall,
            user_extract_enabled=extract,
            agent_participates=participates,
            agent_extract_allowed=agent_extract,
        )
        == expected
    )


def test_agent_extract_allowed_defaults_to_true():
    assert resolve_memory_flags(
        user_recall_enabled=True,
        user_extract_enabled=True,
        agent_participates=True,
    ) == (True, True)


def test_returns_plain_bools():
    ltm, extract = resolve_memory_flags(
        user_recall_enabled=1,  # truthy non-bool
        user_extract_enabled=1,
        agent_participates=1,
    )
    assert ltm is True and extract is True
