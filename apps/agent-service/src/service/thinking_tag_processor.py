"""Tag-based thinking/tool-call processor for streaming model output.

Originally lived inside `api.routes.AgentsRoute`. Moved here so it can be used
by chat routes and tested without importing a route module.
"""


class ThinkingTagProcessor:
    """Tag-based thinking models (<think>...</think>) için streaming state machine.

    Also strips tool-call markup: models that are not natively tool-calling emit
    `<tool_call>{...}</tool_call>` as ordinary text, and whatever the provider's
    parser leaves behind would otherwise be rendered in the chat. That text is
    reported as `tool_call_text` events instead of being dropped outright, so
    callers can still see what the model is writing (a document body streamed
    this way is the only progress signal available for those models).
    """

    OPEN_TAGS = ("<thinking>", "<think>")
    CLOSE_TAGS = ("</thinking>", "</think>")
    TOOL_OPEN_TAGS = ("<tool_call>", "<tool_use>")
    # A leading "<" is sometimes consumed by the provider's own parser, leaving
    # a bare "/tool_call>" in the text.
    TOOL_CLOSE_TAGS = ("</tool_call>", "</tool_use>", "/tool_call>", "/tool_use>")
    MAX_TAG_LEN = max(len(t) for t in OPEN_TAGS + CLOSE_TAGS + TOOL_OPEN_TAGS + TOOL_CLOSE_TAGS)

    def __init__(self):
        self.in_thinking = False
        self.in_tool_call = False
        self.reasoning_started = False
        self.buffer = ""
        self.pending_prefix = ""

    def feed(self, text: str) -> list[dict]:
        self.buffer += text
        events: list[dict] = []

        while self.buffer:
            if self.in_tool_call:
                if not self._consume_tool_call(events):
                    break
            elif not self.in_thinking:
                if not self._consume_answer(events):
                    break
            elif not self._consume_thinking(events):
                break

        return events

    def _consume_tool_call(self, events: list[dict]) -> bool:
        """Inside tool-call markup: report it separately, never as answer text."""
        pos, tag = self._find_tag(self.buffer, self.TOOL_CLOSE_TAGS)
        if pos is not None:
            if pos > 0:
                events.append({"type": "tool_call_text", "content": self.buffer[:pos]})
            self.in_tool_call = False
            self.buffer = self.pending_prefix + self.buffer[pos + len(tag) :]
            self.pending_prefix = ""
            return True

        safe_len = max(0, len(self.buffer) - self.MAX_TAG_LEN)
        if safe_len > 0:
            events.append({"type": "tool_call_text", "content": self.buffer[:safe_len]})
            self.buffer = self.buffer[safe_len:]
        return False

    def _consume_answer(self, events: list[dict]) -> bool:
        pos, tag, kind = self._find_first(
            self.buffer,
            (self.OPEN_TAGS, "think"),
            (self.TOOL_OPEN_TAGS, "tool"),
            (self.TOOL_CLOSE_TAGS, "stray"),
        )
        if pos is not None:
            if pos > 0:
                content = self.buffer[:pos]
                if kind == "tool" and not content.endswith(
                    (" ", "\n", "\t", ".", "!", "?", ":", ";", ",")
                ):
                    last_space = max(content.rfind(" "), content.rfind("\n"), content.rfind("\t"))
                    if last_space != -1:
                        events.append({"type": "token", "content": content[: last_space + 1]})
                        self.pending_prefix = content[last_space + 1 :]
                        self.buffer = self.buffer[pos + len(tag) :]
                    else:
                        events.append({"type": "token", "content": content})
                        self.buffer = self.buffer[pos + len(tag) :]
                else:
                    events.append({"type": "token", "content": content})
                    self.buffer = self.buffer[pos + len(tag) :]
            else:
                self.buffer = self.buffer[pos + len(tag) :]

            if kind == "think":
                if not self.reasoning_started:
                    events.append({"type": "reasoning_start"})
                    self.reasoning_started = True
                self.in_thinking = True
            elif kind == "tool":
                self.in_tool_call = True
            # "stray": an unmatched close tag is simply dropped.
            return True

        has_partial_tag = False
        last_lt = self.buffer.rfind("<")
        if last_lt != -1 and (len(self.buffer) - last_lt) <= self.MAX_TAG_LEN:
            has_partial_tag = True

        safe_len = max(0, last_lt) if has_partial_tag else len(self.buffer)
        if safe_len > 0:
            target_content = self.buffer[:safe_len]
            last_space = max(
                target_content.rfind(" "),
                target_content.rfind("\n"),
                target_content.rfind("\t"),
            )
            if last_space != -1:
                events.append({"type": "token", "content": self.buffer[: last_space + 1]})
                self.buffer = self.buffer[last_space + 1 :]
        return False

    def _consume_thinking(self, events: list[dict]) -> bool:
        pos, tag, kind = self._find_first(
            self.buffer,
            (self.CLOSE_TAGS, "think_end"),
            (self.TOOL_OPEN_TAGS, "tool"),
        )
        if pos is not None:
            if pos > 0:
                events.append({"type": "reasoning_delta", "reasoning": self.buffer[:pos]})
            self.buffer = self.buffer[pos + len(tag) :]
            if kind == "think_end":
                self.in_thinking = False
            else:
                # Models write their tool call inside the reasoning block too.
                self.in_tool_call = True
            return True

        safe_len = max(0, len(self.buffer) - self.MAX_TAG_LEN)
        if safe_len > 0:
            events.append({"type": "reasoning_delta", "reasoning": self.buffer[:safe_len]})
            self.buffer = self.buffer[safe_len:]
        return False

    def flush(self) -> list[dict]:
        """Stream bitişinde kalan buffer'ı emit et."""
        if not self.buffer:
            return []
        if self.in_tool_call:
            event = {"type": "tool_call_text", "content": self.buffer}
        elif self.in_thinking:
            event = {"type": "reasoning_delta", "reasoning": self.buffer}
        else:
            event = {"type": "token", "content": self.buffer}
        self.buffer = ""
        return [event]

    @classmethod
    def _find_first(cls, text: str, *groups: tuple) -> tuple:
        """Find the earliest tag across several labelled tag groups."""
        best_pos, best_tag, best_kind = None, None, None
        for tags, kind in groups:
            pos, tag = cls._find_tag(text, tags)
            if pos is not None and (best_pos is None or pos < best_pos):
                best_pos, best_tag, best_kind = pos, tag, kind
        return best_pos, best_tag, best_kind

    @staticmethod
    def _find_tag(text: str, tags: tuple) -> tuple:
        best_pos, best_tag = None, None
        for tag in tags:
            pos = text.find(tag)
            if pos != -1 and (best_pos is None or pos < best_pos):
                best_pos, best_tag = pos, tag
        return best_pos, best_tag
