import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { ImportFlowModal } from "../ImportFlowModal";
import { SAMPLE_FLOW_JSON } from "../../utils/importFlow";

// Mock i18n
jest.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, defaultVal?: any, params?: any) => {
      if (typeof defaultVal === "string") {
        if (params) {
          let str = defaultVal;
          Object.keys(params).forEach((k) => {
            str = str.replace(`{{${k}}}`, params[k]);
          });
          return str;
        }
        return defaultVal;
      }
      return key;
    },
  }),
}));

describe("ImportFlowModal", () => {
  const mockOnClose = jest.fn();
  const mockOnImport = jest.fn();

  beforeEach(() => {
    jest.clearAllMocks();
  });

  it("renders the modal with drag & drop upload tab by default", () => {
    render(
      <ImportFlowModal
        open={true}
        onClose={mockOnClose}
        onImport={mockOnImport}
      />
    );

    expect(screen.getByText("Akış İçe Aktar (JSON)")).toBeInTheDocument();
    expect(screen.getByTestId("import-modal-tab-upload")).toBeInTheDocument();
    expect(screen.getByTestId("import-modal-tab-paste")).toBeInTheDocument();
    expect(screen.getByTestId("import-dropzone")).toBeInTheDocument();
    expect(screen.getByTestId("import-modal-submit")).toBeDisabled();
  });

  it("switches to paste JSON tab and allows typing JSON", async () => {
    render(
      <ImportFlowModal
        open={true}
        onClose={mockOnClose}
        onImport={mockOnImport}
      />
    );

    fireEvent.click(screen.getByTestId("import-modal-tab-paste"));
    expect(screen.getByTestId("json-code-editor-textarea")).toBeInTheDocument();

    // Type invalid JSON
    fireEvent.change(screen.getByTestId("json-code-editor-textarea"), {
      target: { value: '{"broken": ' },
    });

    expect(screen.getByTestId("json-editor-error-banner")).toBeInTheDocument();
    expect(screen.getByTestId("import-modal-submit")).toBeDisabled();
  });

  it("loads sample flow JSON when 'Örnek Şablon' is clicked and enables submit", () => {
    render(
      <ImportFlowModal
        open={true}
        onClose={mockOnClose}
        onImport={mockOnImport}
      />
    );

    fireEvent.click(screen.getByTestId("import-modal-tab-paste"));
    const sampleBtn = screen.getByText("Örnek Şablon");
    fireEvent.click(sampleBtn);

    const textarea = screen.getByTestId(
      "json-code-editor-textarea"
    ) as HTMLTextAreaElement;
    expect(textarea.value).toContain("chat_input_1");
    expect(
      screen.queryByTestId("json-editor-error-banner")
    ).not.toBeInTheDocument();

    const submitBtn = screen.getByTestId("import-modal-submit");
    expect(submitBtn).toBeEnabled();

    fireEvent.click(submitBtn);
    expect(mockOnImport).toHaveBeenCalledTimes(1);
    expect(mockOnImport).toHaveBeenCalledWith(
      expect.objectContaining({
        nodes: expect.any(Array),
        edges: expect.any(Array),
      }),
      3, // 3 nodes in sample
      2 // 2 edges in sample
    );
  });

  it("formats unformatted JSON when 'Biçimlendir' is clicked", () => {
    render(
      <ImportFlowModal
        open={true}
        onClose={mockOnClose}
        onImport={mockOnImport}
      />
    );

    fireEvent.click(screen.getByTestId("import-modal-tab-paste"));
    const unformatted = JSON.stringify(JSON.parse(SAMPLE_FLOW_JSON));
    fireEvent.change(screen.getByTestId("json-code-editor-textarea"), {
      target: { value: unformatted },
    });

    const formatBtn = screen.getByText("Biçimlendir");
    fireEvent.click(formatBtn);

    const textarea = screen.getByTestId(
      "json-code-editor-textarea"
    ) as HTMLTextAreaElement;
    expect(textarea.value).toContain("\n");
  });

  it("handles valid JSON file drop and shows summary card", async () => {
    render(
      <ImportFlowModal
        open={true}
        onClose={mockOnClose}
        onImport={mockOnImport}
      />
    );

    const file = new File([SAMPLE_FLOW_JSON], "my-flow.json", {
      type: "application/json",
    });

    const dropzoneInput = screen.getByTestId("import-dropzone-input");
    fireEvent.change(dropzoneInput, {
      target: { files: [file] },
    });

    await waitFor(() => {
      expect(screen.getByTestId("import-file-card")).toBeInTheDocument();
      expect(screen.getByText("my-flow.json")).toBeInTheDocument();
    });

    const submitBtn = screen.getByTestId("import-modal-submit");
    expect(submitBtn).toBeEnabled();

    // Clicking edit in code editor switches tab
    const editBtn = screen.getByText("Editörde Düzenle");
    fireEvent.click(editBtn);

    expect(screen.getByTestId("json-code-editor-textarea")).toBeInTheDocument();
    const textarea = screen.getByTestId(
      "json-code-editor-textarea"
    ) as HTMLTextAreaElement;
    expect(textarea.value).toContain("chat_input_1");
  });
});
