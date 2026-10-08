"use client";

import { useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@opal/components";
import type { IconProps } from "@opal/types";
import { SvgArrowRight, SvgLoader, SvgX } from "@opal/icons";
import InputTypeIn from "@/refresh-components/inputs/InputTypeIn";
import RetrievalKindToggle from "@/sections/knowledge-search/components/RetrievalKindToggle";
import type { RetrievalKind } from "@/lib/api/domains/knowledge/knowledge-search-types";
import { cn } from "@/lib/utils";

/** SvgLoader wrapped with `animate-spin` so it can be passed as a Button icon. */
const SpinningLoader = (props: IconProps) => (
  <SvgLoader {...props} className={cn("animate-spin", props.className)} />
);

interface SearchBoxProps {
  value: string;
  kind: RetrievalKind;
  onChange: (value: string) => void;
  onSubmit: () => void;
  onClear: () => void;
  onKindChange: (kind: RetrievalKind) => void;
  graphDisabled?: boolean;
  /** A search is in flight: the submit button spins and blocks a second submit. */
  busy?: boolean;
  /** Focus the box when "/" is pressed outside another text field. */
  shortcut?: boolean;
  autoFocus?: boolean;
  className?: string;
}

function isTypingTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  return (
    target.isContentEditable ||
    ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName)
  );
}

/** The search card: query, clear, retrieval kind, and submit. */
export default function SearchBox({
  value,
  kind,
  onChange,
  onSubmit,
  onClear,
  onKindChange,
  graphDisabled = false,
  busy = false,
  shortcut = false,
  autoFocus = false,
  className,
}: SearchBoxProps) {
  const { t } = useTranslation();
  const inputRef = useRef<HTMLInputElement>(null);
  const canSubmit = value.trim().length > 0;

  useEffect(() => {
    if (!shortcut) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "/" || event.metaKey || event.ctrlKey) return;
      if (isTypingTarget(event.target)) return;
      event.preventDefault();
      inputRef.current?.focus();
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [shortcut]);

  return (
    <form
      role="search"
      aria-busy={busy}
      // globals.css styles every <form> as a column, so the row layout only
      // holds while `flex-row` overrides that direction.
      className={cn(
        "flex w-full flex-row flex-nowrap items-center gap-2 rounded-16 bg-background-neutral-00 py-1.5 pl-3 pr-1.5 shadow-01",
        className
      )}
      onSubmit={(event) => {
        event.preventDefault();
        if (canSubmit) onSubmit();
      }}
    >
      <InputTypeIn
        ref={inputRef}
        type="search"
        variant="internal"
        leftSearchIcon
        showClearButton={false}
        autoFocus={autoFocus}
        value={value}
        placeholder={t("knowledgeSearch.searchBox.placeholder")}
        aria-label={t("knowledgeSearch.searchBox.ariaLabel")}
        onChange={(event) => onChange(event.target.value)}
        className="min-w-0"
      />
      {value && (
        <Button
          icon={SvgX}
          prominence="tertiary"
          size="md"
          tooltip={t("knowledgeSearch.searchBox.clear")}
          aria-label={t("knowledgeSearch.searchBox.clear")}
          onClick={onClear}
        />
      )}
      <RetrievalKindToggle
        kind={kind}
        onChange={onKindChange}
        graphDisabled={graphDisabled}
      />
      <Button
        icon={busy ? SpinningLoader : SvgArrowRight}
        type="submit"
        prominence="primary"
        disabled={!canSubmit || busy}
        aria-label={t("knowledgeSearch.searchBox.submit")}
        tooltip={t("knowledgeSearch.searchBox.submit")}
      />
    </form>
  );
}
