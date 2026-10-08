import React from "react";
import { render, screen } from "@tests/setup/test-utils";
import AtlasApiKeyForm from "@/app/admin/api-key/AtlasApiKeyForm";

jest.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

jest.mock("@/lib/api/domains/access/api", () => ({
  createApiKey: jest.fn(),
  updateApiKey: jest.fn(),
}));

describe("AtlasApiKeyForm", () => {
  test("does not expose legacy API key role selection", () => {
    render(<AtlasApiKeyForm onClose={jest.fn()} onCreateApiKey={jest.fn()} />);

    expect(
      screen.queryByText("admin.apiKey.roleLabel")
    ).not.toBeInTheDocument();
    expect(
      screen.queryByText("admin.apiKey.roleDescription")
    ).not.toBeInTheDocument();
  });
});
