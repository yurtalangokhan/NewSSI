"use client";

import { useEffect, useState } from "react";
import Modal from "@/refresh-components/Modal";
import Button from "@/refresh-components/buttons/Button";
import IconButton from "@/refresh-components/buttons/IconButton";
import InputTextArea from "@/refresh-components/inputs/InputTextArea";
import { SvgFileText, SvgMaximize2 } from "@opal/icons";
import type { FieldRendererProps } from "./types";
import { useTranslation } from "react-i18next";

/**
 * Ported from Langflow (MIT) — src/frontend/src/modals/textAreaModal/index.tsx
 * (`ComponentTextModal`), concept only. Upstream: https://github.com/langflow-ai/langflow @ 3ec070e9
 *
 * Upstream's PROMPT-typed field actually opens a different, richer modal —
 * `modals/promptModal` (`PromptModal`) — which highlights `{variable}`
 * syntax and calls a backend `validate_prompt` endpoint that mutates the
 * node's own template with one new input per detected variable. That's
 * Langflow's dynamic per-node templating system; this project's
 * `ComponentTemplate` is a fixed, registry-owned shape with no per-node
 * mutation (P1 §4.4 — same reason the node toolbar's "Tool Mode" was left
 * out, see NodeToolbar.tsx). `ComponentTextModal`'s plainer shape — a big
 * textarea in a modal, Save commits, closing any other way discards — has
 * no such dependency, so that's what's ported for the expand action.
 */
export function PromptField({
  value,
  onChange,
  disabled,
  field,
}: FieldRendererProps) {
  const { t } = useTranslation();
  const stringValue = typeof value === "string" ? value : "";
  const [expanded, setExpanded] = useState(false);
  const [draft, setDraft] = useState(stringValue);

  // Seed the draft from the committed value each time the modal opens, not
  // on every parent re-render — otherwise typing in the modal would be
  // clobbered by the (still-uncommitted) inline value on the next render.
  useEffect(() => {
    if (expanded) setDraft(stringValue);
  }, [expanded, stringValue]);

  function handleSave() {
    onChange(draft);
    setExpanded(false);
  }

  return (
    <>
      <div className="relative">
        <InputTextArea
          value={stringValue}
          onChange={(e) => onChange(e.target.value)}
          variant={disabled ? "disabled" : undefined}
          autoResize
          maxRows={12}
        />
        {!disabled && (
          <div className="absolute right-1.5 top-1.5 rounded-04 bg-background-neutral-00">
            <IconButton
              icon={SvgMaximize2}
              tooltip={t(
                "flowCanvas.fields.prompt.expand",
                "Expand Prompt Editor"
              )}
              aria-label={t(
                "flowCanvas.fields.prompt.expand",
                "Expand Prompt Editor"
              )}
              small
              onClick={() => setExpanded(true)}
            />
          </div>
        )}
      </div>

      <Modal open={expanded} onOpenChange={setExpanded}>
        <Modal.Content width="lg" height="full">
          <Modal.Header
            icon={SvgFileText}
            title={field.display_name}
            onClose={() => setExpanded(false)}
          />
          {/* `InputTextArea` sizes itself off its `rows` prop, not its
              container. A tall `rows` plus `autoResize`/`maxRows` gives a
              generous editor that grows with the prompt inside the modal. */}
          <Modal.Body>
            <InputTextArea
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              autoFocus
              autoResize
              rows={18}
              maxRows={40}
              className="w-full"
            />
          </Modal.Body>
          <Modal.Footer>
            <Button secondary onClick={() => setExpanded(false)}>
              {t("flowCanvas.fields.prompt.cancel", "Cancel")}
            </Button>
            <Button onClick={handleSave}>
              {t("flowCanvas.inspector.saveDescription", "Save")}
            </Button>
          </Modal.Footer>
        </Modal.Content>
      </Modal>
    </>
  );
}
