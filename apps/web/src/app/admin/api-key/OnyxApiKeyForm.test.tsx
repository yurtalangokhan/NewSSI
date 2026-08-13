import React from "react";
import { render, screen } from "@tests/setup/test-utils";
import OnyxApiKeyForm from "@/app/admin/api-key/OnyxApiKeyForm";

jest.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

jest.mock("@/app/admin/api-key/lib", () => ({
  createApiKey: jest.fn(),
  updateApiKey: jest.fn(),
}));

describe("OnyxApiKeyForm", () => {
  test("does not expose legacy API key role selection", () => {
    render(<OnyxApiKeyForm onClose={jest.fn()} onCreateApiKey={jest.fn()} />);

    expect(screen.queryByText("admin.apiKey.roleLabel")).not.toBeInTheDocument();
    expect(screen.queryByText("admin.apiKey.roleDescription")).not.toBeInTheDocument();
  });
});
