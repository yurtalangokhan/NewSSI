"use client";

import { useState } from "react";
import InputTextArea from "@/refresh-components/inputs/InputTextArea";
import type { FieldRendererProps } from "./types";

function stringify(value: unknown): string {
  try {
    return JSON.stringify(value ?? null, null, 2);
  } catch {
    return "";
  }
}

/**
 * Keeps its own text buffer rather than round-tripping every keystroke
 * through `JSON.parse`/`onChange`: an in-progress edit is frequently
 * invalid JSON, and writing that into node.values would corrupt the
 * saved flow (P1's FlowSpec expects `values` to already be
 * template-shaped). `onChange` only fires once the text parses.
 *
 * Resyncs the text buffer from an external `value` change during render
 * (React's own recommended pattern for "adjusting state when a prop
 * changes"), not in a `useEffect` — an effect-based resync would set
 * state after an already-committed render, causing an extra render pass
 * for every external value change.
 */
export function JsonField({ value, onChange, disabled }: FieldRendererProps) {
  const [prevValue, setPrevValue] = useState(value);
  const [text, setText] = useState(() => stringify(value));
  const [invalid, setInvalid] = useState(false);

  if (value !== prevValue) {
    setPrevValue(value);
    setText(stringify(value));
    setInvalid(false);
  }

  function handleChange(e: React.ChangeEvent<HTMLTextAreaElement>) {
    const next = e.target.value;
    setText(next);
    try {
      const parsed = JSON.parse(next);
      setInvalid(false);
      onChange(parsed);
    } catch {
      setInvalid(true);
    }
  }

  return (
    <InputTextArea
      value={text}
      onChange={handleChange}
      variant={disabled ? "disabled" : invalid ? "error" : undefined}
      className="font-mono"
      autoResize
      maxRows={16}
    />
  );
}
