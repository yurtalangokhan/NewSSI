"use client";

import React, { useEffect, useRef, useState } from "react";
import { FileDescriptor } from "@/app/app/interfaces";
import "katex/dist/katex.min.css";
import MessageSwitcher from "@/app/app/message/MessageSwitcher";
import Text from "@/refresh-components/texts/Text";
import { cn } from "@/lib/utils";
import CopyIconButton from "@/refresh-components/buttons/CopyIconButton";
import { Button } from "@opal/components";
import { SvgEdit } from "@opal/icons";
import { useTranslation } from "react-i18next";
import FileDisplay from "./FileDisplay";
import { useAppBackground } from "@/providers/AppBackgroundProvider";

interface MessageEditingProps {
  content: string;
  onSubmitEdit: (editedContent: string) => void;
  onCancelEdit: () => void;
}

function MessageEditing({
  content,
  onSubmitEdit,
  onCancelEdit,
}: MessageEditingProps) {
  const { t } = useTranslation();
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const [editedContent, setEditedContent] = useState(content);

  useEffect(() => {
    if (!textareaRef.current) return;

    // Focus the textarea
    textareaRef.current.focus();
    textareaRef.current.select();
  }, []);

  function handleSubmit() {
    onSubmitEdit(editedContent);
  }

  function handleCancel() {
    setEditedContent(content);
    onCancelEdit();
  }

  return (
    <div className="w-full">
      <div
        className={cn(
          "w-full h-full border border-border-01 rounded-16 overflow-hidden bg-background-neutral-00 p-3 flex flex-col gap-2 shadow-01"
        )}
      >
        <textarea
          ref={textareaRef}
          className={cn(
            "w-full min-h-[8rem] resize-none outline-none bg-transparent overflow-y-auto whitespace-normal break-word text-text-01"
          )}
          aria-multiline
          role="textarea"
          value={editedContent}
          style={{ scrollbarWidth: "thin" }}
          onChange={(e) => {
            setEditedContent(e.target.value);
            textareaRef.current!.style.height = "auto";
            e.target.style.height = `${e.target.scrollHeight}px`;
          }}
          onKeyDown={(e) => {
            if (e.key === "Escape") {
              e.preventDefault();
              handleCancel();
            }
            // Submit edit if "Command Enter" is pressed, like in ChatGPT
            if (e.key === "Enter" && e.metaKey) handleSubmit();
          }}
        />
        <div className="flex justify-end gap-1">
          <Button onClick={handleSubmit}>{t("common.submit")}</Button>
          <Button prominence="secondary" onClick={handleCancel}>
            {t("common.cancel")}
          </Button>
        </div>
      </div>
    </div>
  );
}

interface HumanMessageProps {
  // Content and display
  content: string;
  files?: FileDescriptor[];

  // Message navigation - nodeId for tree position, messageId for editing
  nodeId: number;
  messageId?: number | null;
  otherMessagesCanSwitchTo?: number[];
  onMessageSelection?: (nodeId: number) => void;

  // Editing functionality - takes (editedContent, messageId) to allow stable callback reference
  onEdit?: (editedContent: string, messageId: number) => void;

  // Streaming and generation
  stopGenerating?: () => void;
  disableSwitchingForStreaming?: boolean;
}

// Memoization comparison - compare by value for primitives, by reference for objects/arrays
function arePropsEqual(
  prev: HumanMessageProps,
  next: HumanMessageProps
): boolean {
  return (
    prev.content === next.content &&
    prev.nodeId === next.nodeId &&
    prev.messageId === next.messageId &&
    prev.files === next.files &&
    prev.disableSwitchingForStreaming === next.disableSwitchingForStreaming &&
    prev.otherMessagesCanSwitchTo === next.otherMessagesCanSwitchTo &&
    prev.onEdit === next.onEdit
    // Skip: stopGenerating, onMessageSelection (inline function props)
  );
}

const HumanMessage = React.memo(function HumanMessage({
  content: initialContent,
  files,
  nodeId,
  messageId,
  otherMessagesCanSwitchTo,
  onEdit,
  onMessageSelection,
  stopGenerating = () => null,
  disableSwitchingForStreaming = false,
}: HumanMessageProps) {
  // TODO (@raunakab):
  //
  // This is some duplicated state that is patching a memoization issue with `HumanMessage`.
  // Fix this later.
  const [content, setContent] = useState(initialContent);

  const [isEditing, setIsEditing] = useState(false);
  const { t } = useTranslation();
  const { foregroundTextClass, foregroundTextStyle } = useAppBackground();

  // Use nodeId for switching (finding position in siblings)
  const indexInSiblings = otherMessagesCanSwitchTo?.indexOf(nodeId);
  // indexOf returns -1 if not found, treat that as undefined
  const currentMessageInd =
    indexInSiblings !== undefined && indexInSiblings !== -1
      ? indexInSiblings
      : undefined;

  const getPreviousMessage = () => {
    if (
      currentMessageInd !== undefined &&
      currentMessageInd > 0 &&
      otherMessagesCanSwitchTo
    ) {
      return otherMessagesCanSwitchTo[currentMessageInd - 1];
    }
    return undefined;
  };

  const getNextMessage = () => {
    if (
      currentMessageInd !== undefined &&
      currentMessageInd < (otherMessagesCanSwitchTo?.length || 0) - 1 &&
      otherMessagesCanSwitchTo
    ) {
      return otherMessagesCanSwitchTo[currentMessageInd + 1];
    }
    return undefined;
  };

  return (
    <div
      id="onyx-human-message"
      className="group flex flex-col justify-end w-full relative"
    >
      <FileDisplay alignBubble files={files || []} />
      <div className="md:flex md:flex-wrap relative justify-end break-words">
        {isEditing ? (
          <MessageEditing
            content={content}
            onSubmitEdit={(editedContent) => {
              // Don't update UI for edits that can't be persisted
              if (messageId === undefined || messageId === null) {
                setIsEditing(false);
                return;
              }
              onEdit?.(editedContent, messageId);
              setContent(editedContent);
              setIsEditing(false);
            }}
            onCancelEdit={() => setIsEditing(false)}
          />
        ) : typeof content === "string" ? (
          <>
            <div className="flex basis-[100%] justify-end md:order-1 md:basis-auto md:max-w-[37.5rem]">
              <div
                className={
                  "max-w-[min(34rem,calc(100vw-3rem))] md:max-w-[37.5rem] whitespace-break-spaces break-anywhere rounded-t-16 rounded-bl-16 border border-border-01 bg-background-neutral-00 px-3.5 py-2.5 shadow-01"
                }
                onCopy={(e) => {
                  const selection = window.getSelection();
                  if (selection) {
                    e.preventDefault();
                    const text = selection
                      .toString()
                      .replace(/\n{2,}/g, "\n")
                      .trim();
                    e.clipboardData.setData("text/plain", text);
                  }
                }}
              >
                <Text
                  as="p"
                  className={`inline-block align-middle ${foregroundTextClass}`}
                  style={foregroundTextStyle}
                  mainContentBody
                >
                  {content}
                </Text>
              </div>
            </div>
            {onEdit && !isEditing && (
              <div className="absolute right-0 z-content flex flex-row rounded-08 bg-background-neutral-00 p-1 opacity-0 shadow-01 transition-opacity group-hover:opacity-100 md:relative md:bg-transparent md:shadow-none">
                <CopyIconButton
                  getCopyText={() => content}
                  prominence="tertiary"
                  data-testid="HumanMessage/copy-button"
                />
                <Button
                  icon={SvgEdit}
                  prominence="tertiary"
                  tooltip={t("humanMessage.editTooltip")}
                  onClick={() => setIsEditing(true)}
                  data-testid="HumanMessage/edit-button"
                />
              </div>
            )}
          </>
        ) : (
          <>
            <div
              className={cn(
                "my-auto",
                onEdit && !isEditing
                  ? "opacity-0 group-hover:opacity-100 transition-opacity"
                  : "invisible"
              )}
            >
              <Button
                icon={SvgEdit}
                onClick={() => setIsEditing(true)}
                prominence="tertiary"
                tooltip={t("humanMessage.editTooltip")}
              />
            </div>
            <div className="ml-auto rounded-lg p-1" style={foregroundTextStyle}>
              {content}
            </div>
          </>
        )}
        <div className="md:min-w-[100%] flex justify-end order-1 mt-1">
          {currentMessageInd !== undefined &&
            onMessageSelection &&
            otherMessagesCanSwitchTo &&
            otherMessagesCanSwitchTo.length > 1 && (
              <MessageSwitcher
                disableForStreaming={disableSwitchingForStreaming}
                currentPage={currentMessageInd + 1}
                totalPages={otherMessagesCanSwitchTo.length}
                handlePrevious={() => {
                  stopGenerating();
                  const prevMessage = getPreviousMessage();
                  if (prevMessage !== undefined) {
                    onMessageSelection(prevMessage);
                  }
                }}
                handleNext={() => {
                  stopGenerating();
                  const nextMessage = getNextMessage();
                  if (nextMessage !== undefined) {
                    onMessageSelection(nextMessage);
                  }
                }}
              />
            )}
        </div>
      </div>
    </div>
  );
}, arePropsEqual);

export default HumanMessage;
