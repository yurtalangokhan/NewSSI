"use client";

import * as React from "react";
import InputTypeIn, {
  InputTypeInProps,
} from "@/refresh-components/inputs/InputTypeIn";
import { Button } from "@opal/components";
import { noProp } from "@/lib/utils";
import { SvgEye, SvgEyeClosed, SvgAlertTriangle } from "@opal/icons";
import { useTranslation } from "react-i18next";

/**
 * Custom mask character for password display.
 *
 * We use ASTERISK OPERATOR (U+2217) instead of the browser's native password
 * masking (typically bullet •) to follow our design guidelines. This requires
 * custom change handling logic to track the real value while displaying masks.
 */
const MASK_CHARACTER = "∗";

// Backend placeholder pattern - indicates a stored value that can't be revealed
const BACKEND_PLACEHOLDER_PATTERN = /^•+$/; // All bullet characters (U+2022)

/**
 * Check if a value is a backend placeholder (all bullet characters).
 * The backend sends this to indicate a stored secret exists without revealing it.
 */
function isBackendPlaceholder(value: string): boolean {
  return !!value && BACKEND_PLACEHOLDER_PATTERN.test(value);
}

export interface SelectionRange {
  start: number;
  end: number;
}

export interface MaskedInputChangeResult {
  newValue: string;
  cursorPosition: number;
}

/**
 * Computes the real value from a masked input change event.
 *
 * Since we display mask characters (∗) instead of the actual password,
 * we need to reverse-engineer what the user typed/deleted by comparing
 * the new display value with the previous real value and selection state.
 *
 * @param newDisplayValue - The new value from the input (mix of masks and typed chars)
 * @param previousValue - The actual password value before the change
 * @param cursorPosition - Current cursor position after the change
 * @param previousSelection - Selection range before the change occurred
 * @returns The computed real value and where to place the cursor
 */
export function computeMaskedInputChange(
  newDisplayValue: string,
  previousValue: string,
  cursorPosition: number,
  previousSelection: SelectionRange
): MaskedInputChangeResult {
  const oldLength = previousValue.length;
  const newLength = newDisplayValue.length;
  const hadSelection = previousSelection.end > previousSelection.start;

  // Field was cleared
  if (newLength === 0) {
    return { newValue: "", cursorPosition: 0 };
  }

  // When autofilled by the browser or pasted as plain text, no mask characters are present.
  // In that case, the entire display value is the new raw password.
  if (!newDisplayValue.includes(MASK_CHARACTER)) {
    return { newValue: newDisplayValue, cursorPosition: newLength };
  }

  // Text was selected and replaced/deleted
  if (hadSelection) {
    const selectionLength = previousSelection.end - previousSelection.start;
    const insertedLength = newLength - oldLength + selectionLength;

    // Extract inserted characters from their position in the display value
    const insertedChars = newDisplayValue.slice(
      previousSelection.start,
      previousSelection.start + insertedLength
    );

    const newValue =
      previousValue.slice(0, previousSelection.start) +
      insertedChars +
      previousValue.slice(previousSelection.end);

    return {
      newValue,
      cursorPosition: previousSelection.start + insertedChars.length,
    };
  }

  // Characters were added (typed or pasted) without selection
  if (newLength > oldLength) {
    const charsAdded = newLength - oldLength;
    const insertPos = Math.max(0, cursorPosition - charsAdded);
    const addedChars = newDisplayValue.slice(insertPos, cursorPosition);

    return {
      newValue:
        previousValue.slice(0, insertPos) +
        addedChars +
        previousValue.slice(insertPos),
      cursorPosition,
    };
  }

  // Characters were deleted without selection
  if (newLength < oldLength) {
    const charsDeleted = oldLength - newLength;
    const deleteEnd = cursorPosition + charsDeleted;

    return {
      newValue:
        previousValue.slice(0, cursorPosition) + previousValue.slice(deleteEnd),
      cursorPosition,
    };
  }

  // Same length without selection - no change
  return { newValue: previousValue, cursorPosition };
}

export interface PasswordInputTypeInProps
  extends Omit<
    InputTypeInProps,
    "type" | "rightSection" | "leftSearchIcon" | "variant"
  > {
  /**
   * Ref to the input element.
   */
  ref?: React.Ref<HTMLInputElement>;
  /**
   * Whether the input is disabled.
   */
  disabled?: boolean;
  /**
   * Whether the input has an error.
   */
  error?: boolean;
  /**
   * When true, the reveal toggle is disabled.
   * Use this when displaying a stored/masked value from the backend
   * that cannot actually be revealed.
   * The input remains editable so users can type a new value.
   */
  isNonRevealable?: boolean;
  /**
   * When true, the reveal toggle is always shown, even when the field is
   * empty and unfocused. Defaults to false (toggle only shows once the
   * field has a value or is focused).
   */
  alwaysShowToggle?: boolean;
  /**
   * Tooltip/aria-label shown when the password is hidden (toggle reveals it).
   * Defaults to the `common.showPassword` locale copy.
   */
  showPasswordLabel?: string;
  /**
   * Tooltip/aria-label shown when the password is revealed (toggle hides it).
   * Defaults to the `common.hidePassword` locale copy.
   */
  hidePasswordLabel?: string;
  /**
   * Tooltip/aria-label shown for the Caps Lock indicator.
   * Defaults to the `common.capsLockOn` locale copy.
   */
  capsLockLabel?: string;
  /**
   * Whether to show a Caps Lock icon indicator in rightSection when Caps Lock is active.
   * Defaults to true.
   */
  showCapsLockIndicator?: boolean;
  /**
   * Callback fired when Caps Lock modifier state changes.
   */
  onCapsLockChange?: (isCapsLockOn: boolean) => void;
}

/**
 * PasswordInputTypeIn Component
 *
 * A password input with custom mask character (∗) and reveal/hide toggle.
 * Built on top of InputTypeIn for consistency.
 *
 * Features:
 * - Custom mask character (∗) instead of browser default
 * - Show/hide toggle button only visible when input has value or is focused
 * - When revealed, the toggle icon uses action style (more prominent)
 * - When hidden, the toggle icon uses internal style (muted)
 * - Optional `isNonRevealable` prop to disable reveal (for stored backend values)
 */
export default function PasswordInputTypeIn({
  ref,
  isNonRevealable = false,
  alwaysShowToggle = false,
  showPasswordLabel,
  hidePasswordLabel,
  capsLockLabel,
  showCapsLockIndicator = true,
  onCapsLockChange,
  value,
  onChange,
  onFocus,
  onBlur,
  onKeyDown,
  onKeyUp,
  onClick,
  disabled,
  error,
  showClearButton = false,
  ...props
}: PasswordInputTypeInProps) {
  const { t } = useTranslation("common", { keyPrefix: "common" });
  const [isPasswordVisible, setIsPasswordVisible] = React.useState(false);
  const [isFocused, setIsFocused] = React.useState(false);
  const [isCapsLockOn, setIsCapsLockOn] = React.useState(false);

  // Track selection range before changes occur
  const selectionRef = React.useRef<{ start: number; end: number }>({
    start: 0,
    end: 0,
  });

  const checkCapsLock = React.useCallback(
    (
      e:
        | React.KeyboardEvent<HTMLInputElement>
        | React.MouseEvent<HTMLInputElement>
    ) => {
      if (typeof e.getModifierState === "function") {
        const active = e.getModifierState("CapsLock");
        setIsCapsLockOn(active);
        onCapsLockChange?.(active);
      }
    },
    [onCapsLockChange]
  );

  const realValue = String(value || "");
  const hasValue = realValue.length > 0;
  const effectiveNonRevealable =
    isNonRevealable || isBackendPlaceholder(realValue);
  const isHidden = !isPasswordVisible || effectiveNonRevealable;

  const getDisplayValue = (): string => {
    if (isHidden) {
      return MASK_CHARACTER.repeat(realValue.length);
    }
    return realValue;
  };

  const handleFocus = React.useCallback(
    (e: React.FocusEvent<HTMLInputElement>) => {
      setIsFocused(true);
      onFocus?.(e);
    },
    [onFocus]
  );

  const handleBlur = React.useCallback(
    (e: React.FocusEvent<HTMLInputElement>) => {
      setIsFocused(false);
      setIsCapsLockOn(false);
      onCapsLockChange?.(false);
      onBlur?.(e);
    },
    [onBlur, onCapsLockChange]
  );

  // Track selection before any change occurs (used by both onSelect and onKeyDown)
  const captureSelection = React.useCallback(
    (e: React.SyntheticEvent<HTMLInputElement>) => {
      const target = e.target as HTMLInputElement;
      selectionRef.current = {
        start: target.selectionStart ?? 0,
        end: target.selectionEnd ?? 0,
      };
    },
    []
  );

  const handleKeyDown = React.useCallback(
    (e: React.KeyboardEvent<HTMLInputElement>) => {
      captureSelection(e);
      checkCapsLock(e);
      onKeyDown?.(e);
    },
    [captureSelection, checkCapsLock, onKeyDown]
  );

  const handleKeyUp = React.useCallback(
    (e: React.KeyboardEvent<HTMLInputElement>) => {
      checkCapsLock(e);
      onKeyUp?.(e);
    },
    [checkCapsLock, onKeyUp]
  );

  const handleClick = React.useCallback(
    (e: React.MouseEvent<HTMLInputElement>) => {
      checkCapsLock(e);
      onClick?.(e);
    },
    [checkCapsLock, onClick]
  );

  const handleChange = React.useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      // When visible, pass through directly - no masking needed
      if (!isHidden) {
        onChange?.(e);
        return;
      }

      const input = e.target;
      const cursorPos = input.selectionStart ?? input.value.length;

      // Compute the real value from the masked input change
      const result = computeMaskedInputChange(
        input.value,
        realValue,
        cursorPos,
        selectionRef.current
      );

      // Restore cursor position after React re-renders with new masked value
      requestAnimationFrame(() => {
        if (input && document.activeElement === input) {
          input.setSelectionRange(result.cursorPosition, result.cursorPosition);
        }
      });

      // Create synthetic event for Formik compatibility
      const syntheticEvent = {
        target: { name: input.name, value: result.newValue, type: "text" },
        currentTarget: {
          name: input.name,
          value: result.newValue,
          type: "text",
        },
        type: "change",
        persist: () => {},
      } as unknown as React.ChangeEvent<HTMLInputElement>;

      onChange?.(syntheticEvent);
    },
    [isHidden, realValue, onChange]
  );

  const showToggleButton = alwaysShowToggle || hasValue || isFocused;
  const isRevealed = isPasswordVisible && !effectiveNonRevealable;
  // A caller-supplied label wins; otherwise the shared `common.*` copy keeps
  // the tooltips in the active locale instead of a baked-in English string
  // (the flow canvas' SecretField relies on those defaults).
  const toggleLabel = effectiveNonRevealable
    ? t("valueCannotBeRevealed")
    : isPasswordVisible
      ? hidePasswordLabel ?? t("hidePassword")
      : showPasswordLabel ?? t("showPassword");
  const capsLockText = capsLockLabel ?? t("capsLockOn");

  const showCapsLock = showCapsLockIndicator && isCapsLockOn && isFocused;
  const showRightSection = showToggleButton || showCapsLock;

  const rightSectionContent = showRightSection ? (
    <div className="flex items-center gap-0.5">
      {showCapsLock && (
        <span
          data-testid="caps-lock-indicator"
          className="flex items-center justify-center p-1 text-amber-500 shrink-0"
          title={capsLockText}
          aria-label={capsLockText}
        >
          <SvgAlertTriangle className="size-4 stroke-amber-500" />
        </span>
      )}
      {showToggleButton && (
        <Button
          icon={isRevealed ? SvgEye : SvgEyeClosed}
          disabled={disabled || effectiveNonRevealable}
          onClick={noProp(() => setIsPasswordVisible((v) => !v))}
          type="button"
          variant={isRevealed ? "action" : undefined}
          prominence="tertiary"
          size="sm"
          tooltipSide="left"
          tooltip={toggleLabel}
          aria-label={toggleLabel}
        />
      )}
    </div>
  ) : undefined;

  return (
    <InputTypeIn
      ref={ref}
      value={getDisplayValue()}
      onChange={handleChange}
      onFocus={handleFocus}
      onBlur={handleBlur}
      onSelect={captureSelection}
      onKeyDown={handleKeyDown}
      onKeyUp={handleKeyUp}
      onClick={handleClick}
      variant={disabled ? "disabled" : error ? "error" : undefined}
      showClearButton={showClearButton}
      autoComplete="off"
      data-ph-no-capture
      rightSection={rightSectionContent}
      {...props}
    />
  );
}
