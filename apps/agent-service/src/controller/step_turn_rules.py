"""
Registry that declares how each packet type behaves during timeline turn assignment.

Adding a new step type (e.g. a researcher_start / researcher_delta pair) only requires
adding entries to STEP_TURN_RULES — no other file needs to change.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class StepTurnRule:
    """Declares when a packet should start a new turn_index."""

    # When True the packet always starts a new turn (default for unknown types).
    new_turn: bool = True

    # Packet types after which this packet stays on the *same* turn.
    # If the previous packet's type is in this set the turn is NOT incremented
    # (unless check_tool_change applies and the tool name changed).
    groups_with: frozenset[str] = field(default_factory=frozenset)

    # When True AND the previous type is in groups_with, also split if the
    # tool_name changed between the two packets (used for custom_tool_delta).
    check_tool_change: bool = False


# Single source of truth for all packet turn-grouping rules.
#
# Unknown packet types default to StepTurnRule() → new_turn=True, so every
# new packet type is safely handled without any extra code.  Only packets that
# *group* with a predecessor need an explicit entry.
STEP_TURN_RULES: dict[str, StepTurnRule] = {
    "reasoning_start": StepTurnRule(new_turn=True),
    "reasoning_delta": StepTurnRule(
        new_turn=False,
        groups_with=frozenset({"reasoning_start", "reasoning_delta"}),
    ),
    "reasoning_done": StepTurnRule(
        new_turn=False,
        groups_with=frozenset({"reasoning_start", "reasoning_delta", "reasoning_done"}),
    ),
    # Each custom tool call gets its own turn/card.
    "custom_tool_start": StepTurnRule(new_turn=True),
    "custom_tool_delta": StepTurnRule(
        new_turn=False,
        groups_with=frozenset({"custom_tool_start", "custom_tool_delta"}),
        check_tool_change=True,
    ),
    # Search tool packets: queries and document deltas stay grouped with search_tool_start.
    # Consecutive search_tool_starts in the same tool phase group together to match the live stream.
    "search_tool_start": StepTurnRule(
        new_turn=False,
        groups_with=frozenset(
            {"search_tool_start", "search_tool_queries_delta", "search_tool_documents_delta"}
        ),
    ),
    "search_tool_queries_delta": StepTurnRule(
        new_turn=False,
        groups_with=frozenset(
            {"search_tool_start", "search_tool_queries_delta", "search_tool_documents_delta"}
        ),
    ),
    "search_tool_documents_delta": StepTurnRule(
        new_turn=False,
        groups_with=frozenset(
            {"search_tool_start", "search_tool_queries_delta", "search_tool_documents_delta"}
        ),
    ),
    # URL fetch / open tool: each open_url_start starts a new turn card; its URLs and docs group with it.
    "open_url_start": StepTurnRule(new_turn=True),
    "open_url_urls": StepTurnRule(
        new_turn=False,
        groups_with=frozenset({"open_url_start", "open_url_urls"}),
    ),
    "open_url_documents": StepTurnRule(
        new_turn=False,
        groups_with=frozenset({"open_url_start", "open_url_urls", "open_url_documents"}),
    ),
    # Document generation and file cards stay grouped on their own turn.
    "document_generation_start": StepTurnRule(new_turn=True),
    "document_generation_progress": StepTurnRule(
        new_turn=False,
        groups_with=frozenset({"document_generation_start", "document_generation_progress"}),
    ),
    "document_generation_end": StepTurnRule(
        new_turn=False,
        groups_with=frozenset(
            {"document_generation_start", "document_generation_progress", "document_generation_end"}
        ),
    ),
    "generated_file": StepTurnRule(
        new_turn=False,
        groups_with=frozenset(
            {
                "document_generation_start",
                "document_generation_progress",
                "document_generation_end",
                "generated_file",
            }
        ),
    ),
    # Python tool
    "python_tool_start": StepTurnRule(new_turn=True),
    "python_tool_delta": StepTurnRule(
        new_turn=False,
        groups_with=frozenset({"python_tool_start", "python_tool_delta"}),
    ),
    # File reader tool
    "file_reader_start": StepTurnRule(new_turn=True),
    "file_reader_result": StepTurnRule(
        new_turn=False,
        groups_with=frozenset({"file_reader_start", "file_reader_result"}),
    ),
    # Memory tool
    "memory_tool_start": StepTurnRule(new_turn=True),
    "memory_tool_delta": StepTurnRule(
        new_turn=False,
        groups_with=frozenset({"memory_tool_start", "memory_tool_delta"}),
    ),
    # Deep research plan
    "deep_research_plan_start": StepTurnRule(new_turn=True),
    "deep_research_plan_delta": StepTurnRule(
        new_turn=False,
        groups_with=frozenset({"deep_research_plan_start", "deep_research_plan_delta"}),
    ),
    # Research agent
    "research_agent_start": StepTurnRule(new_turn=True),
    "intermediate_report_start": StepTurnRule(
        new_turn=False,
        groups_with=frozenset({"research_agent_start", "intermediate_report_start"}),
    ),
    "intermediate_report_delta": StepTurnRule(
        new_turn=False,
        groups_with=frozenset(
            {"research_agent_start", "intermediate_report_start", "intermediate_report_delta"}
        ),
    ),
    "intermediate_report_cited_docs": StepTurnRule(
        new_turn=False,
        groups_with=frozenset(
            {
                "research_agent_start",
                "intermediate_report_start",
                "intermediate_report_delta",
                "intermediate_report_cited_docs",
            }
        ),
    ),
    # Long term memory
    "long_term_memory_recall": StepTurnRule(new_turn=True),
    "long_term_memory_save": StepTurnRule(new_turn=True),
    "custom_step_start": StepTurnRule(new_turn=True),
    # An ask_user question and the answer that locked it are ONE card.
    "user_clarification": StepTurnRule(new_turn=True),
    "user_clarification_answered": StepTurnRule(
        new_turn=False,
        groups_with=frozenset({"user_clarification"}),
    ),
}


def should_increment_turn(
    pkt_type: str,
    prev_type: str | None,
    prev_tool: str | None,
    curr_tool: str | None,
    *,
    is_first: bool,
) -> bool:
    """
    Return True if this packet should start a new turn_index.

    Args:
        pkt_type:  The type field of the current packet.
        prev_type: The type field of the immediately preceding packet (None if first).
        prev_tool: The tool_name of the preceding packet (None if absent).
        curr_tool: The tool_name of the current packet (None if absent).
        is_first:  True when this is the first packet in the sequence.
    """
    if is_first:
        return False

    rule = STEP_TURN_RULES.get(pkt_type, StepTurnRule(new_turn=True))

    if rule.new_turn:
        return True

    if prev_type in rule.groups_with:
        if rule.check_tool_change:
            # Same group only if the tool name hasn't changed.
            return bool(prev_tool and curr_tool and curr_tool != prev_tool)
        return False

    # Transition from a different packet type → new turn.
    return True
