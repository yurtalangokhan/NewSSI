import React from "react";
import { render, screen, fireEvent, waitFor } from "@tests/setup/test-utils";
import CreateProjectModal from "@/components/modals/CreateProjectModal";
import { toast } from "@/hooks/useToast";

const mockCreateProject = jest.fn();
const mockRoute = jest.fn();
const mockToggle = jest.fn();

jest.mock("@/providers/ProjectsContext", () => ({
  useProjectsContext: () => ({
    createProject: mockCreateProject,
  }),
}));

jest.mock("@/hooks/appNavigation", () => ({
  useAppRouter: () => mockRoute,
}));

jest.mock("@/refresh-components/contexts/ModalContext", () => ({
  useModal: () => ({
    isOpen: true,
    toggle: mockToggle,
  }),
}));

jest.mock("@/hooks/useToast", () => ({
  toast: {
    error: jest.fn(),
    success: jest.fn(),
  },
}));

jest.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, options?: { defaultValue?: string }) => {
      if (key === "modals.createProject.createButton") return "Create Project";
      if (key === "modals.createProject.creatingButton") return "Creating...";
      if (key === "modals.cancel") return "Cancel";
      if (options?.defaultValue) return options.defaultValue;
      return key;
    },
  }),
}));

describe("CreateProjectModal", () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it("disables the create button when project name is empty or only whitespace", () => {
    render(<CreateProjectModal />);

    const createButton = screen.getByRole("button", {
      name: /create project/i,
    });
    expect(createButton).toBeDisabled();

    const input = screen.getByPlaceholderText(
      "modals.createProject.namePlaceholder"
    );
    fireEvent.change(input, { target: { value: "   " } });
    expect(createButton).toBeDisabled();

    fireEvent.change(input, { target: { value: "My New Project" } });
    expect(createButton).not.toBeDisabled();
  });

  it("shows loading state and disables buttons while creating project", async () => {
    let resolvePromise: (value: any) => void;
    const promise = new Promise((resolve) => {
      resolvePromise = resolve;
    });
    mockCreateProject.mockReturnValue(promise);

    render(<CreateProjectModal initialProjectName="Test Project" />);

    const createButton = screen.getByRole("button", {
      name: /create project/i,
    });
    expect(createButton).not.toBeDisabled();

    fireEvent.click(createButton);

    // During submission
    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /creating\.\.\./i })
      ).toBeDisabled();
    });
    expect(screen.getByRole("button", { name: /cancel/i })).toBeDisabled();

    // Resolve the creation
    resolvePromise!({ id: 123, name: "Test Project" });

    await waitFor(() => {
      expect(mockCreateProject).toHaveBeenCalledWith("Test Project");
      expect(mockRoute).toHaveBeenCalledWith({ projectId: 123 });
      expect(mockToggle).toHaveBeenCalledWith(false);
    });
  });

  it("prevents multiple submissions when Enter is pressed repeatedly", async () => {
    let resolvePromise: (value: any) => void;
    const promise = new Promise((resolve) => {
      resolvePromise = resolve;
    });
    mockCreateProject.mockReturnValue(promise);

    render(<CreateProjectModal initialProjectName="Duplicate Test" />);

    // Press Enter multiple times in rapid succession
    fireEvent.keyDown(document, { key: "Enter" });
    fireEvent.keyDown(document, { key: "Enter" });
    fireEvent.keyDown(document, { key: "Enter" });

    expect(mockCreateProject).toHaveBeenCalledTimes(1);

    resolvePromise!({ id: 456, name: "Duplicate Test" });

    await waitFor(() => {
      expect(mockRoute).toHaveBeenCalledWith({ projectId: 456 });
    });
  });

  it("handles error during creation, shows toast, and re-enables button", async () => {
    mockCreateProject.mockRejectedValue(new Error("Network error"));

    render(<CreateProjectModal initialProjectName="Error Project" />);

    const createButton = screen.getByRole("button", {
      name: /create project/i,
    });
    fireEvent.click(createButton);

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith(
        "Failed to create the project Error Project"
      );
    });

    // After failure, button should be re-enabled
    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /create project/i })
      ).not.toBeDisabled();
    });
  });
});
