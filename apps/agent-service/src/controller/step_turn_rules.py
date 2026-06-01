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
    "custom_tool_start": StepTurnRule(new_turn=True),
    "custom_tool_delta": StepTurnRule(
        new_turn=False,
        groups_with=frozenset({"custom_tool_start", "custom_tool_delta"}),
        check_tool_change=True,
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
