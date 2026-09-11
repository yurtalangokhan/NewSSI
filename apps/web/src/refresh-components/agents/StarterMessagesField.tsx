"use client";

import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import InputTypeIn from "@/refresh-components/inputs/InputTypeIn";
import { Section } from "@/layouts/general-layouts";
import { MAX_STARTER_MESSAGES } from "@/lib/constants";

export interface StarterMessagesFieldProps {
  value: string[];
  onChange: (next: string[]) => void;
  max?: number;
}

/**
 * Conversation starters, lifted out of AgentEditorPage's Formik
 * `FieldArray` into a controlled string array — the flow creation modal
 * has nowhere to put a Formik context, so this owns no form state itself.
 */
export default function StarterMessagesField({
  value,
  onChange,
  max = MAX_STARTER_MESSAGES,
}: StarterMessagesFieldProps) {
  const { t } = useTranslation();
  const starterMessagePlaceholders = useMemo(
    () =>
      Array.from({ length: max }, (_, i) =>
        t(`agentEditor.conversationStarterExample${i + 1}`)
      ),
    [max, t]
  );

  const filledStarters = value.filter((s) => s).length;
  const canAddMore = filledStarters < max;
  const visibleCount = Math.min(
    max,
    Math.max(
      1,
      filledStarters === 0 ? 1 : filledStarters + (canAddMore ? 1 : 0)
    )
  );

  function setAt(index: number, next: string) {
    const updated = [...value];
    updated[index] = next;
    onChange(updated);
  }

  function removeAt(index: number) {
    // Splice, not blank — matches the original FieldArray.remove(i), which
    // shifts later starters up instead of leaving a hole.
    const updated = [...value];
    updated.splice(index, 1);
    onChange(updated);
  }

  return (
    <Section gap={0.5}>
      {Array.from({ length: visibleCount }, (_, i) => (
        // w-full on both wrapper and input: without it the row shrinks to
        // the input's intrinsic width and the field renders half-width in
        // a narrow modal.
        <div key={i} className="flex w-full flex-row items-center gap-1">
          <InputTypeIn
            data-testid="starter-message-input"
            className="w-full"
            value={value[i] ?? ""}
            onChange={(e) => setAt(i, e.target.value)}
            onClear={() => removeAt(i)}
            placeholder={
              starterMessagePlaceholders[i] ||
              t("agentEditor.enterConversationStarter")
            }
          />
        </div>
      ))}
    </Section>
  );
}
