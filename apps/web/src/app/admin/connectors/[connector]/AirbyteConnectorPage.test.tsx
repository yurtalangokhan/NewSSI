import React from "react";
import { render, screen, setupUser, waitFor } from "@tests/setup/test-utils";

import AirbyteConnectorPage from "./AirbyteConnectorPage";
import { fetchConnectorSpec, validateConnectorConfig } from "@/lib/airbyte";

jest.mock("next/navigation", () => ({
  useRouter: () => ({ push: jest.fn() }),
}));

jest.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

jest.mock("@/lib/airbyte", () => ({
  fetchConnectorSpec: jest.fn(),
  validateConnectorConfig: jest.fn(),
  fetchConnectorStreams: jest.fn(),
  createDatasource: jest.fn(),
  DatasourceConflictError: class DatasourceConflictError extends Error {},
}));

jest.mock("@/sections/sidebar/StepSidebarWrapper", () => ({
  __esModule: true,
  default: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

describe("AirbyteConnectorPage defaults", () => {
  it("submits untouched schema defaults including the displayed replication branch", async () => {
    jest.mocked(fetchConnectorSpec).mockResolvedValue({
      connector_type: "source-postgres",
      display_name: "Postgres",
      connection_specification: {
        type: "object",
        properties: {
          host: { type: "string" },
          port: { type: "integer", default: 5432 },
          replication_method: {
            default: "CDC",
            oneOf: [
              {
                type: "object",
                properties: {
                  method: { type: "string", const: "CDC" },
                  queue_size: { type: "integer", default: 1000 },
                },
              },
              {
                type: "object",
                properties: {
                  method: { type: "string", const: "Standard" },
                  initial_waiting_seconds: { type: "integer", default: 0 },
                },
              },
            ],
          },
          ssl: {
            type: "object",
            properties: {
              mode: { type: "string", default: "prefer" },
              verify: { type: "boolean", default: false },
            },
          },
        },
      },
    } as never);
    jest.mocked(validateConnectorConfig).mockResolvedValue({
      valid: false,
      message: "stop after validation",
    });

    render(<AirbyteConnectorPage connectorName="source-postgres" />);
    const user = setupUser();
    const submit = await screen.findByRole("button", {
      name: "admin.airbyteConnector.testAndContinue",
    });
    await waitFor(() => expect(submit).toBeEnabled());
    await user.click(submit);

    await waitFor(() => {
      expect(validateConnectorConfig).toHaveBeenCalledWith("source-postgres", {
        port: 5432,
        replication_method: { method: "CDC", queue_size: 1000 },
        ssl: { mode: "prefer", verify: false },
      });
    });
  });
});
