import "@/i18n/config";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { uploadAgentIcon } from "@/lib/api/domains/agents/api";

jest.mock("@/lib/api/domains/agents/api", () => ({
  uploadAgentIcon: jest.fn(),
}));
import userEvent from "@testing-library/user-event";
import AgentIconPicker from "@/refresh-components/agents/AgentIconPicker";
import StarterMessagesField from "@/refresh-components/agents/StarterMessagesField";
import AgentVisibilityFields from "@/refresh-components/agents/AgentVisibilityFields";

describe("extracted editor fields", () => {
  it("reports the picked icon through onChange", async () => {
    const onChange = jest.fn();
    render(
      <AgentIconPicker
        value={{ uploadedImageId: null, iconName: null }}
        onChange={onChange}
      />
    );

    // The icon grid lives in a Popover.Content that only mounts once the
    // trigger opens it — Radix activates on real pointer sequencing, so
    // userEvent (not a bare fireEvent.click) is required here too.
    await userEvent.click(
      screen.getByRole("button", { name: "Edit" }).parentElement!
    );
    fireEvent.click(screen.getAllByTestId("agent-icon-option")[0]!);
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ uploadedImageId: null })
    );
  });

  it("does not trigger file input when clicking avatar, only when clicking upload image line item", async () => {
    const fileClickSpy = jest.spyOn(HTMLInputElement.prototype, "click");
    render(
      <AgentIconPicker
        value={{ uploadedImageId: null, iconName: null }}
        onChange={jest.fn()}
      />
    );

    // Clicking avatar/edit trigger opens popover
    await userEvent.click(
      screen.getByRole("button", { name: "Edit" }).parentElement!
    );
    expect(fileClickSpy).not.toHaveBeenCalled();

    // Now click upload image inside the open popover
    const uploadButton = screen.getAllByText(/uploadImage|Upload image/i)[0]!;
    fireEvent.click(uploadButton);
    expect(fileClickSpy).toHaveBeenCalledTimes(1);

    fileClickSpy.mockRestore();
  });

  it("applies large dimensions when size is set to large", () => {
    render(
      <AgentIconPicker
        value={{ uploadedImageId: null, iconName: null }}
        onChange={jest.fn()}
        size="large"
      />
    );

    const trigger = screen.getByRole("button", { name: "Edit" }).parentElement!;
    expect(trigger.className).toContain("h-[10rem]");
    expect(trigger.className).toContain("w-[10rem]");
  });

  it("reports edited starter messages through onChange", () => {
    const onChange = jest.fn();
    render(
      <StarterMessagesField value={["", "", "", ""]} onChange={onChange} />
    );

    fireEvent.change(screen.getAllByTestId("starter-message-input")[0]!, {
      target: { value: "Merhaba" },
    });
    expect(onChange).toHaveBeenCalledWith(["Merhaba", "", "", ""]);
  });

  it("reports visibility switches through onChange", () => {
    const onChange = jest.fn();
    render(
      <AgentVisibilityFields
        isPublic={false}
        featured={false}
        canFeature
        onChange={onChange}
      />
    );

    fireEvent.click(screen.getByTestId("agent-visibility-public"));
    expect(onChange).toHaveBeenCalledWith({ isPublic: true, featured: false });
  });
  it("applies rounded square boundaries when variant is flow", () => {
    render(
      <AgentIconPicker
        value={{ uploadedImageId: null, iconName: null }}
        onChange={jest.fn()}
        variant="flow"
      />
    );

    const trigger = screen.getByRole("button", { name: "Edit" }).parentElement!;
    expect(trigger).toHaveAttribute("data-variant", "flow");
    expect(trigger.className).toContain("rounded-[28%]");
    expect(trigger.className).not.toContain("rounded-full");
  });

  it("applies circular boundaries when variant is agent", () => {
    render(
      <AgentIconPicker
        value={{ uploadedImageId: null, iconName: null }}
        onChange={jest.fn()}
        variant="agent"
      />
    );

    const trigger = screen.getByRole("button", { name: "Edit" }).parentElement!;
    expect(trigger).toHaveAttribute("data-variant", "agent");
    expect(trigger.className).toContain("rounded-full");
    expect(trigger.className).not.toContain("rounded-[28%]");
  });
  it("uploads an image and updates uploadedImageId on file change", async () => {
    jest
      .mocked(uploadAgentIcon)
      .mockResolvedValue(
        new Response(JSON.stringify({ file_id: "file-456" }), { status: 200 })
      );
    const onChange = jest.fn();
    render(
      <AgentIconPicker
        value={{ uploadedImageId: null, iconName: null }}
        onChange={onChange}
      />
    );

    const fileInput = document.querySelector(
      "input[type='file']"
    ) as HTMLInputElement;
    expect(fileInput).toBeInTheDocument();

    const file = new File(["dummy content"], "avatar.png", {
      type: "image/png",
    });
    fireEvent.change(fileInput, { target: { files: [file] } });

    expect(uploadAgentIcon).toHaveBeenCalledWith(expect.any(FormData));
    await waitFor(() => {
      expect(onChange).toHaveBeenCalledWith({
        uploadedImageId: "file-456",
        iconName: null,
      });
    });
  });
});
