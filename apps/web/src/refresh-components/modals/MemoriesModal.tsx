"use client";

import { Fragment, useState, useRef, useEffect, useCallback } from "react";
import Modal from "@/refresh-components/Modal";
import { Section } from "@/layouts/general-layouts";
import InputTypeIn from "@/refresh-components/inputs/InputTypeIn";
import InputTextArea from "@/refresh-components/inputs/InputTextArea";
import IconButton from "@/refresh-components/buttons/IconButton";
import Text from "@/refresh-components/texts/Text";
import Button from "@/refresh-components/buttons/Button";
import CharacterCount from "@/refresh-components/CharacterCount";
import Separator from "@/refresh-components/Separator";
import TextSeparator from "@/refresh-components/TextSeparator";
import { toast } from "@/hooks/useToast";
import { useModalClose } from "@/refresh-components/contexts/ModalContext";
import { SvgAddLines, SvgMinusCircle, SvgPlusCircle } from "@opal/icons";
import {
  useMemoryManager,
  MAX_MEMORY_LENGTH,
  MAX_MEMORY_COUNT,
  LocalMemory,
} from "@/hooks/useMemoryManager";
import { cn } from "@/lib/utils";
import { useUser } from "@/providers/UserProvider";
import useUserPersonalization from "@/hooks/useUserPersonalization";
import type { MemoryItem } from "@/lib/types";
import { useTranslation } from "react-i18next";

interface MemoryItemProps {
  memory: LocalMemory;
  originalIndex: number;
  onUpdate: (index: number, value: string) => void;
  onBlur: (index: number) => void;
  onRemove: (index: number) => void;
  shouldFocus?: boolean;
  onFocused?: () => void;
  shouldHighlight?: boolean;
  onHighlighted?: () => void;
}

function MemoryItem({
  memory,
  originalIndex,
  onUpdate,
  onBlur,
  onRemove,
  shouldFocus,
  onFocused,
  shouldHighlight,
  onHighlighted,
}: MemoryItemProps) {
  const { t } = useTranslation("common", { keyPrefix: "memories" });
  const [isFocused, setIsFocused] = useState(false);
  const [isHighlighting, setIsHighlighting] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const wrapperRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (shouldFocus) {
      textareaRef.current?.focus();
      onFocused?.();
    }
  }, [shouldFocus, onFocused]);

  useEffect(() => {
    if (!shouldHighlight) return;

    wrapperRef.current?.scrollIntoView({ block: "center", behavior: "smooth" });
    textareaRef.current?.focus();
    setIsHighlighting(true);

    const timer = setTimeout(() => {
      setIsHighlighting(false);
      onHighlighted?.();
    }, 1000);

    return () => clearTimeout(timer);
  }, [shouldHighlight, onHighlighted]);

  return (
    <div
      ref={wrapperRef}
      className={cn(
        "rounded-08 hover:bg-background-tint-00 w-full p-0.5",
        "transition-colors ",
        isHighlighting &&
          "bg-action-link-01 border border-action-link-05 duration-700"
      )}
    >
      <Section gap={0.25} alignItems="start">
        <Section flexDirection="row" alignItems="start" gap={0.5}>
          <InputTextArea
            ref={textareaRef}
            placeholder={t("placeholder")}
            value={memory.content}
            onChange={(e) => onUpdate(originalIndex, e.target.value)}
            onFocus={() => setIsFocused(true)}
            onBlur={() => {
              setIsFocused(false);
              void onBlur(originalIndex);
            }}
            rows={3}
            maxLength={MAX_MEMORY_LENGTH}
            resizable={false}
            className={cn(!isFocused && "bg-transparent")}
          />
          <IconButton
            icon={SvgMinusCircle}
            onClick={() => void onRemove(originalIndex)}
            tertiary
            disabled={!memory.content.trim() && memory.isNew}
            aria-label={t("removeLine")}
            tooltip={t("removeLine")}
          />
        </Section>
        {isFocused && (
          <CharacterCount value={memory.content} limit={MAX_MEMORY_LENGTH} />
        )}
      </Section>
    </div>
  );
}

interface MemoriesModalProps {
  memories?: MemoryItem[];
  onSaveMemories?: (memories: MemoryItem[]) => Promise<boolean>;
  onDeleteMemory?: (id: string) => Promise<boolean>;
  onClose?: () => void;
  initialTargetMemoryId?: string | null;
  initialTargetIndex?: number | null;
  highlightFirstOnOpen?: boolean;
}

export default function MemoriesModal({
  memories: memoriesProp,
  onSaveMemories: onSaveMemoriesProp,
  onDeleteMemory,
  onClose,
  initialTargetMemoryId,
  initialTargetIndex,
  highlightFirstOnOpen = false,
}: MemoriesModalProps) {
  const { t } = useTranslation("common", { keyPrefix: "memories" });
  const close = useModalClose(onClose);
  // focusMemoryId tracks local numeric IDs from useMemoryManager (Date.now())
  const [focusMemoryId, setFocusMemoryId] = useState<number | null>(null);

  // Self-fetching: when no props provided, fetch from UserProvider
  const { user, refreshUser, updateUserPersonalization } = useUser();
  const { handleSavePersonalization } = useUserPersonalization(
    user,
    updateUserPersonalization,
    {
      onSuccess: () => toast.success(t("preferencesSaved")),
      onError: () => toast.error(t("preferencesSaveFailed")),
    }
  );

  useEffect(() => {
    if (memoriesProp === undefined) {
      void refreshUser();
    }
    // Only run on mount
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const internalSaveMemories = useCallback(
    async (newMemories: MemoryItem[]): Promise<boolean> => {
      const result = await handleSavePersonalization(
        {},
        true
      );
      return !!result;
    },
    [handleSavePersonalization]
  );

  const effectiveMemories = memoriesProp ?? [];
  const effectiveSave = onSaveMemoriesProp ?? internalSaveMemories;

  // Drives scroll-into-view + highlight when opening from a FileTile click
  const [highlightMemoryId, setHighlightMemoryId] = useState<string | null>(
    null
  );

  useEffect(() => {
    if (initialTargetMemoryId != null) {
      setHighlightMemoryId(initialTargetMemoryId);
    } else if (initialTargetIndex != null && effectiveMemories.length > 0) {
      const descIdx = effectiveMemories.length - 1 - initialTargetIndex;
      const target = effectiveMemories[descIdx];
      if (target) {
        setHighlightMemoryId(target.id);
      }
    } else if (
      highlightFirstOnOpen &&
      effectiveMemories.length > 0 &&
      effectiveMemories[0]
    ) {
      setHighlightMemoryId(effectiveMemories[0].id);
    }
  }, [initialTargetMemoryId, initialTargetIndex]);

  const {
    searchQuery,
    setSearchQuery,
    filteredMemories,
    totalLineCount,
    canAddMemory,
    handleAddMemory,
    handleUpdateMemory,
    handleRemoveMemory,
    handleBlurMemory,
  } = useMemoryManager({
    memories: effectiveMemories,
    onSaveMemories: effectiveSave,
    onDeleteMemory,
    onNotify: (message, type) => toast[type](message),
  });

  const onAddLine = () => {
    const id = handleAddMemory();
    if (id !== null) {
      setFocusMemoryId(id);
    }
  };

  return (
    <Modal open onOpenChange={(open) => !open && close?.()}>
      <Modal.Content width="sm" height="lg">
        <Modal.Header
          icon={SvgAddLines}
          title={t("modalTitle")}
          description={t("modalDescription")}
          onClose={close}
        >
          <Section flexDirection="row" gap={0.5}>
            <InputTypeIn
              placeholder={t("searchPlaceholder")}
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              leftSearchIcon
              showClearButton={false}
              className="w-full !bg-transparent !border-transparent [&:is(:hover,:active,:focus,:focus-within)]:!bg-background-neutral-00 [&:is(:hover)]:!border-border-01 [&:is(:focus,:focus-within)]:!shadow-none"
            />
            <Button
              onClick={onAddLine}
              tertiary
              rightIcon={SvgPlusCircle}
              disabled={!canAddMemory}
              title={
                !canAddMemory
                  ? t("maxMemoriesReached", { count: MAX_MEMORY_COUNT })
                  : undefined
              }
            >
              {t("addLine")}
            </Button>
          </Section>
        </Modal.Header>

        <Modal.Body padding={0.5}>
          {filteredMemories.length === 0 ? (
            <Section alignItems="center" padding={2}>
              <Text secondaryBody text03>
                {searchQuery.trim() ? t("noResults") : t("noMemoriesYet")}
              </Text>
            </Section>
          ) : (
            <Section gap={0.5}>
              {filteredMemories.map(({ memory, originalIndex }) => (
                <Fragment key={memory.id}>
                  <MemoryItem
                    memory={memory}
                    originalIndex={originalIndex}
                    onUpdate={handleUpdateMemory}
                    onBlur={handleBlurMemory}
                    onRemove={handleRemoveMemory}
                    shouldFocus={memory.id === focusMemoryId}
                    onFocused={() => setFocusMemoryId(null)}
                    shouldHighlight={memory.dbId === highlightMemoryId}
                    onHighlighted={() => {
                      setHighlightMemoryId(null);
                    }}
                  />
                  {memory.isNew && <Separator noPadding />}
                </Fragment>
              ))}
            </Section>
          )}
          <TextSeparator
            count={totalLineCount}
            text={t("line", { count: totalLineCount })}
          />
        </Modal.Body>
      </Modal.Content>
    </Modal>
  );
}

