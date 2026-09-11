import { fireEvent, render, screen } from "@testing-library/react";
import { PublishFlowModal } from "../components/PublishFlowModal";

describe("PublishFlowModal", () => {
  it("announces the version about to be created", () => {
    render(
      <PublishFlowModal
        nextVersionNo={4}
        currentVersionNo={3}
        isPublishing={false}
        onConfirm={jest.fn()}
        onClose={jest.fn()}
      />
    );

    expect(screen.getByTestId("publish-modal-target")).toHaveTextContent("4");
  });

  it("passes the notes to onConfirm", () => {
    const onConfirm = jest.fn();
    render(
      <PublishFlowModal
        nextVersionNo={1}
        currentVersionNo={null}
        isPublishing={false}
        onConfirm={onConfirm}
        onClose={jest.fn()}
      />
    );

    fireEvent.change(screen.getByTestId("publish-modal-notes"), {
      target: { value: "İlk sürüm" },
    });
    fireEvent.click(screen.getByTestId("publish-modal-confirm"));

    expect(onConfirm).toHaveBeenCalledWith("İlk sürüm");
  });

  it("disables confirm while publishing", () => {
    render(
      <PublishFlowModal
        nextVersionNo={2}
        currentVersionNo={1}
        isPublishing
        onConfirm={jest.fn()}
        onClose={jest.fn()}
      />
    );

    expect(screen.getByTestId("publish-modal-confirm")).toBeDisabled();
  });
});
