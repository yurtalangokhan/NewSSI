import React from "react";
import { render, screen, fireEvent, act } from "@tests/setup/test-utils";
import PasswordInputTypeIn, {
  computeMaskedInputChange,
} from "./PasswordInputTypeIn";

describe("computeMaskedInputChange", () => {
  const MASK = "∗"; // ASTERISK OPERATOR (U+2217)

  test("handles typing at any position", () => {
    // Typing "x" in middle of "abcd" -> "abxcd"
    const result = computeMaskedInputChange(
      MASK.repeat(2) + "x" + MASK.repeat(2),
      "abcd",
      3,
      { start: 2, end: 2 }
    );
    expect(result).toEqual({ newValue: "abxcd", cursorPosition: 3 });
  });

  test("handles deletion", () => {
    // Delete at position 1 of "abcd" -> "acd"
    const result = computeMaskedInputChange(MASK.repeat(3), "abcd", 1, {
      start: 1,
      end: 1,
    });
    expect(result).toEqual({ newValue: "acd", cursorPosition: 1 });
  });

  test("handles selection replacement", () => {
    // Select "bc" in "abcd", type "xyz" -> "axyzd"
    const result = computeMaskedInputChange(MASK + "xyz" + MASK, "abcd", 4, {
      start: 1,
      end: 3,
    });
    expect(result).toEqual({ newValue: "axyzd", cursorPosition: 4 });
  });

  test("handles clearing the field", () => {
    const result = computeMaskedInputChange("", "password", 0, {
      start: 0,
      end: 8,
    });
    expect(result).toEqual({ newValue: "", cursorPosition: 0 });
  });

  test("preserves mask character in user input", () => {
    // Pasting "∗∗" to replace "bc" in "abcd" -> "a∗∗d"
    const result = computeMaskedInputChange(
      MASK.repeat(4), // display shows 4 masks
      "abcd",
      3,
      { start: 1, end: 3 }
    );
    expect(result).toEqual({ newValue: "a∗∗d", cursorPosition: 3 });
  });

  test("handles browser autofill when cursorPosition is 0 and no mask characters exist", () => {
    const result = computeMaskedInputChange("MyAutofilledPass123!", "", 0, {
      start: 0,
      end: 0,
    });
    expect(result).toEqual({
      newValue: "MyAutofilledPass123!",
      cursorPosition: 20,
    });
  });

  test("handles pasting a full password without mask characters", () => {
    const result = computeMaskedInputChange("PastedSecret999", "oldpass", 15, {
      start: 0,
      end: 7,
    });
    expect(result).toEqual({
      newValue: "PastedSecret999",
      cursorPosition: 15,
    });
  });
});

describe("PasswordInputTypeIn CapsLock behavior", () => {
  it("detects Caps Lock and displays indicator in rightSection while focused", () => {
    const onCapsLockChange = jest.fn();
    render(
      <PasswordInputTypeIn
        placeholder="Enter password"
        capsLockLabel="Caps Lock is active"
        onCapsLockChange={onCapsLockChange}
      />
    );

    const input = screen.getByPlaceholderText("Enter password");

    // Initially, no indicator
    expect(screen.queryByTestId("caps-lock-indicator")).not.toBeInTheDocument();

    // Focus and press key with Caps Lock on
    act(() => {
      fireEvent.focus(input);
      fireEvent.keyDown(input, { key: "A", modifierCapsLock: true });
    });

    expect(onCapsLockChange).toHaveBeenCalledWith(true);
    expect(screen.getByTestId("caps-lock-indicator")).toBeInTheDocument();
    expect(screen.getByTestId("caps-lock-indicator")).toHaveAttribute(
      "aria-label",
      "Caps Lock is active"
    );

    // Caps Lock turned off
    act(() => {
      fireEvent.keyUp(input, { key: "a", modifierCapsLock: false });
    });

    expect(onCapsLockChange).toHaveBeenCalledWith(false);
    expect(screen.queryByTestId("caps-lock-indicator")).not.toBeInTheDocument();

    // Re-enable and blur
    act(() => {
      fireEvent.keyDown(input, { key: "A", modifierCapsLock: true });
    });
    expect(screen.getByTestId("caps-lock-indicator")).toBeInTheDocument();

    act(() => {
      fireEvent.blur(input);
    });
    expect(onCapsLockChange).toHaveBeenCalledWith(false);
    expect(screen.queryByTestId("caps-lock-indicator")).not.toBeInTheDocument();
  });
});
