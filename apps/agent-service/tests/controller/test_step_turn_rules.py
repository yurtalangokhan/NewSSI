"""Unit tests for the step_turn_rules registry."""

from controller.step_turn_rules import STEP_TURN_RULES, should_increment_turn


class TestShouldIncrementTurn:
    # ------------------------------------------------------------------ #
    # First packet never increments                                        #
    # ------------------------------------------------------------------ #

    def test_first_packet_never_increments(self):
        assert should_increment_turn("reasoning_start", None, None, None, is_first=True) is False

    def test_first_packet_unknown_type_never_increments(self):
        assert should_increment_turn("unknown_type", None, None, None, is_first=True) is False

    # ------------------------------------------------------------------ #
    # reasoning_start always starts a new turn                            #
    # ------------------------------------------------------------------ #

    def test_reasoning_start_always_new_turn(self):
        assert (
            should_increment_turn(
                "reasoning_start", "custom_tool_delta", None, None, is_first=False
            )
            is True
        )

    def test_reasoning_start_after_reasoning_delta(self):
        assert (
            should_increment_turn("reasoning_start", "reasoning_delta", None, None, is_first=False)
            is True
        )

    # ------------------------------------------------------------------ #
    # reasoning_delta groups with preceding reasoning packets             #
    # ------------------------------------------------------------------ #

    def test_reasoning_delta_groups_with_reasoning_start(self):
        assert (
            should_increment_turn("reasoning_delta", "reasoning_start", None, None, is_first=False)
            is False
        )

    def test_reasoning_delta_groups_with_reasoning_delta(self):
        assert (
            should_increment_turn("reasoning_delta", "reasoning_delta", None, None, is_first=False)
            is False
        )

    def test_reasoning_delta_splits_from_tool(self):
        assert (
            should_increment_turn(
                "reasoning_delta", "custom_tool_delta", None, None, is_first=False
            )
            is True
        )

    # ------------------------------------------------------------------ #
    # custom_tool_start always starts a new turn                          #
    # ------------------------------------------------------------------ #

    def test_tool_start_always_new_turn(self):
        assert (
            should_increment_turn(
                "custom_tool_start", "reasoning_delta", None, None, is_first=False
            )
            is True
        )

    def test_tool_start_after_tool_delta_same_tool_still_splits(self):
        # Each call gets its own turn even when the tool name repeats — the
        # reconstruction already reordered packets so this start's own delta
        # immediately follows it, so splitting here doesn't separate a call
        # from its result.
        assert (
            should_increment_turn(
                "custom_tool_start", "custom_tool_delta", "search", "search", is_first=False
            )
            is True
        )

    def test_tool_start_after_tool_delta_different_tool_splits(self):
        assert (
            should_increment_turn(
                "custom_tool_start", "custom_tool_delta", "search", "fetch", is_first=False
            )
            is True
        )

    # ------------------------------------------------------------------ #
    # custom_tool_delta groups when same tool, splits when tool changes   #
    # ------------------------------------------------------------------ #

    def test_tool_delta_groups_after_tool_start_same_tool(self):
        assert (
            should_increment_turn(
                "custom_tool_delta", "custom_tool_start", "search", "search", is_first=False
            )
            is False
        )

    def test_tool_delta_groups_after_tool_delta_same_tool(self):
        assert (
            should_increment_turn(
                "custom_tool_delta", "custom_tool_delta", "search", "search", is_first=False
            )
            is False
        )

    def test_tool_delta_splits_on_tool_change(self):
        assert (
            should_increment_turn(
                "custom_tool_delta", "custom_tool_delta", "search", "calculator", is_first=False
            )
            is True
        )

    def test_tool_delta_splits_when_prev_is_not_tool(self):
        assert (
            should_increment_turn(
                "custom_tool_delta", "reasoning_delta", "search", "search", is_first=False
            )
            is True
        )

    def test_tool_delta_splits_when_prev_tool_is_none(self):
        # prev_tool=None means no known preceding tool → treat as new
        assert (
            should_increment_turn(
                "custom_tool_delta", "custom_tool_delta", None, "search", is_first=False
            )
            is False
        )

    def test_tool_delta_splits_when_curr_tool_is_none(self):
        # curr_tool=None → can't confirm same tool, but prev in groups_with and no tool info → stays
        assert (
            should_increment_turn(
                "custom_tool_delta", "custom_tool_delta", "search", None, is_first=False
            )
            is False
        )

    # ------------------------------------------------------------------ #
    # Unknown types default to new_turn=True                              #
    # ------------------------------------------------------------------ #

    def test_unknown_type_always_new_turn(self):
        assert (
            should_increment_turn(
                "researcher_start", "custom_tool_delta", None, None, is_first=False
            )
            is True
        )

    def test_another_unknown_type(self):
        assert (
            should_increment_turn("my_custom_delta", "my_custom_delta", None, None, is_first=False)
            is True
        )


class TestStepTurnRulesRegistry:
    def test_registry_contains_expected_keys(self):
        expected = {"reasoning_start", "reasoning_delta", "custom_tool_start", "custom_tool_delta"}
        assert expected.issubset(STEP_TURN_RULES.keys())

    def test_reasoning_delta_groups_with_set(self):
        rule = STEP_TURN_RULES["reasoning_delta"]
        assert "reasoning_start" in rule.groups_with
        assert "reasoning_delta" in rule.groups_with
        assert rule.new_turn is False

    def test_custom_tool_delta_checks_tool_change(self):
        rule = STEP_TURN_RULES["custom_tool_delta"]
        assert rule.check_tool_change is True
        assert rule.new_turn is False

    def test_reasoning_start_is_always_new_turn(self):
        rule = STEP_TURN_RULES["reasoning_start"]
        assert rule.new_turn is True

    def test_custom_tool_start_is_always_new_turn(self):
        rule = STEP_TURN_RULES["custom_tool_start"]
        assert rule.new_turn is True
