/**
 * AttachmentButton - A button component for displaying file attachments or similar items
 *
 * Displays an attachment item with an icon, title, description, metadata text,
 * and optional action buttons. Commonly used for file lists, attachment pickers,
 * and similar UI patterns where items can be viewed or acted upon.
 *
 * Features:
 * - Three visual states: default, selected (shows checkbox), processing
 * - Left icon that changes to checkbox when selected
 * - Truncated title and description text
 * - Right-aligned metadata text (e.g., file size, date)
 * - Optional view button (external link icon) that appears on hover
 * - Optional action button (custom icon) that appears on hover
 * - Full-width button with hover states
 * - Prevents event bubbling for nested action buttons
 *
 * @example
 * ```tsx
 * import AttachmentButton from "@/refresh-components/buttons/AttachmentButton";
 * import { SvgFileText, SvgTrash } from "@opal/icons";
 *
 * // Basic attachment
 * <AttachmentButton
 *   icon={SvgFileText}
 *   description="document.pdf"
 *   rightText="2.4 MB"
 * >
 *   Project Proposal
 * </AttachmentButton>
 *
 * // Selected state with view button
 * <AttachmentButton
 *   icon={SvgFileText}
 *   selected
 *   description="document.pdf"
 *   rightText="2.4 MB"
 *   onView={() => window.open('/view/doc')}
 * >
 *   Project Proposal
 * </AttachmentButton>
 *
 * // With action button (delete)
 * <AttachmentButton
 *   icon={SvgFileText}
 *   description="document.pdf"
 *   rightText="2.4 MB"
 *   actionIcon={SvgTrash}
 *   onAction={() => handleDelete()}
 * >
 *   Project Proposal
 * </AttachmentButton>
 *
 * // Processing state
 * <AttachmentButton
 *   icon={SvgFileText}
 *   processing
 *   description="Uploading..."
 *   rightText="45%"
 * >
 *   Project Proposal
 * </AttachmentButton>
 * ```
 */

import React from "react";
import { noProp } from "@/lib/utils";
import Truncated from "@/refresh-components/texts/Truncated";
import IconButton from "@/refresh-components/buttons/IconButton";
import { Button } from "@opal/components";
import Text from "@/refresh-components/texts/Text";
import type { IconProps } from "@opal/types";
import Checkbox from "@/refresh-components/inputs/Checkbox";
import { SvgExternalLink } from "@opal/icons";
import { WithoutStyles } from "@/types";

export interface AttachmentProps
  extends Omit<
    WithoutStyles<React.HTMLAttributes<HTMLDivElement>>,
    "children"
  > {
  selected?: boolean;
  processing?: boolean;

  icon: React.FunctionComponent<IconProps>;
  children: React.ReactNode;
  description?: string;
  rightText?: string;
  onView?: () => void;

  // Action button: An optional secondary action button that appears on hover.
  // Commonly used for actions like delete, download, or remove.
  // Both `actionIcon` and `onAction` must be provided for the button to appear.
  actionIcon?: React.FunctionComponent<IconProps>;
  onAction?: () => void;
  disabled?: boolean;
}

export default function AttachmentButton({
  selected,
  processing,
  icon: Icon,
  children,
  description,
  rightText,
  onView,
  actionIcon,
  onAction,
  onClick,
  onKeyDown,
  onKeyUp,
  disabled,
  tabIndex = 0,
  ...props
}: AttachmentProps) {
  const state = selected ? "selected" : processing ? "processing" : "default";

  const handleKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
    if (disabled) return;
    if (e.target !== e.currentTarget) {
      onKeyDown?.(e);
      return;
    }
    if (e.key === "Enter") {
      e.preventDefault();
      onClick?.(e as unknown as React.MouseEvent<HTMLDivElement>);
    } else if (e.key === " ") {
      e.preventDefault();
    }
    onKeyDown?.(e);
  };

  const handleKeyUp = (e: React.KeyboardEvent<HTMLDivElement>) => {
    if (disabled) return;
    if (e.target !== e.currentTarget) {
      onKeyUp?.(e);
      return;
    }
    if (e.key === " ") {
      e.preventDefault();
      onClick?.(e as unknown as React.MouseEvent<HTMLDivElement>);
    }
    onKeyUp?.(e);
  };

  return (
    <div
      role="button"
      tabIndex={disabled ? -1 : tabIndex}
      className="attachment-button"
      data-state={state}
      onClick={disabled ? undefined : onClick}
      onKeyDown={handleKeyDown}
      onKeyUp={handleKeyUp}
      {...props}
    >
      <div className="attachment-button__content">
        <div className="attachment-button__icon-wrapper">
          {selected ? (
            <Checkbox checked />
          ) : (
            <Icon className="attachment-button__icon" />
          )}
        </div>
        <div className="attachment-button__text-container">
          <div className="attachment-button__title-row">
            <div className="attachment-button__title-wrapper">
              <Truncated mainUiMuted text04 nowrap>
                {children}
              </Truncated>
            </div>
            {onView && (
              <IconButton
                icon={SvgExternalLink}
                onClick={noProp(onView)}
                internal
                className="attachment-button__view-button"
              />
            )}
          </div>
          {description && (
            <Truncated secondaryBody text03 className="w-full">
              {description}
            </Truncated>
          )}
        </div>
      </div>

      <div className="attachment-button__actions">
        {rightText && (
          <Text as="p" secondaryBody text03>
            {rightText}
          </Text>
        )}
        {actionIcon && onAction && (
          <div className="attachment-button__action-button">
            <Button
              icon={actionIcon}
              onClick={noProp(onAction)}
              prominence="tertiary"
              size="sm"
            />
          </div>
        )}
      </div>
    </div>
  );
}
