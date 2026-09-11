/**
 * The studio's leave-the-draft dialog. Built as its own component (like its
 * sibling PublishFlowModal) rather than via ConfirmationModalLayout, which
 * left an empty tinted Modal.Body strip below the header — the layout puts
 * its text in the header's `description` and renders the body from
 * `children`, which this dialog never had — and mixed two different Button
 * implementations in one footer, so the three actions did not match.
 */

import { fireEvent, render, screen } from "@testing-library/react";
import { FlowExitModal } from "../components/FlowExitModal";

describe("FlowExitModal", () => {
  it("explains in the body what stays published", () => {
    render(
      <FlowExitModal
        publishedVersionNo={5}
        isDiscarding={false}
        onKeep={jest.fn()}
        onDiscard={jest.fn()}
        onCancel={jest.fn()}
      />
    );

    const explanation = screen.getByTestId("flow-exit-explanation");
    expect(explanation).toHaveTextContent("5");
    // The prose belongs to the body, not the header's subtitle — putting it
    // in the subtitle is what left the body an empty tinted strip.
    expect(screen.getByTestId("flow-exit-body")).toContainElement(explanation);
  });

  it("warns when discarding would leave the flow with nothing", () => {
    render(
      <FlowExitModal
        publishedVersionNo={null}
        isDiscarding={false}
        onKeep={jest.fn()}
        onDiscard={jest.fn()}
        onCancel={jest.fn()}
      />
    );

    // i18n is not initialised here, so `t()` yields the inline default —
    // asserting on that keeps the test independent of the locale files.
    expect(screen.getByTestId("flow-exit-explanation")).toHaveTextContent(
      "no content at all"
    );
  });

  it("wires each action to its handler", () => {
    const onKeep = jest.fn();
    const onDiscard = jest.fn();
    const onCancel = jest.fn();
    render(
      <FlowExitModal
        publishedVersionNo={5}
        isDiscarding={false}
        onKeep={onKeep}
        onDiscard={onDiscard}
        onCancel={onCancel}
      />
    );

    fireEvent.click(screen.getByTestId("flow-exit-keep"));
    fireEvent.click(screen.getByTestId("flow-exit-discard"));
    fireEvent.click(screen.getByTestId("flow-exit-cancel"));

    expect(onKeep).toHaveBeenCalledTimes(1);
    expect(onDiscard).toHaveBeenCalledTimes(1);
    expect(onCancel).toHaveBeenCalledTimes(1);
  });

  it("gives all three actions the same button chrome, with discard as the destructive one", () => {
    render(
      <FlowExitModal
        publishedVersionNo={5}
        isDiscarding={false}
        onKeep={jest.fn()}
        onDiscard={jest.fn()}
        onCancel={jest.fn()}
      />
    );

    for (const testId of [
      "flow-exit-cancel",
      "flow-exit-discard",
      "flow-exit-keep",
    ]) {
      const action = screen.getByTestId(testId);
      expect(action.querySelector(".opal-button")).not.toBeNull();
    }

    expect(screen.getByTestId("flow-exit-discard")).toHaveAttribute(
      "data-interactive-base-variant",
      "danger"
    );
  });

  it("disables discard while the discard request is in flight", () => {
    render(
      <FlowExitModal
        publishedVersionNo={5}
        isDiscarding
        onKeep={jest.fn()}
        onDiscard={jest.fn()}
        onCancel={jest.fn()}
      />
    );

    expect(screen.getByTestId("flow-exit-discard")).toBeDisabled();
  });
});
