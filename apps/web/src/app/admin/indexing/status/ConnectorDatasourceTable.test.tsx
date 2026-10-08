import React from "react";
import { render, screen, setupUser, waitFor } from "@tests/setup/test-utils";

import {
  ManageDialog,
  destinationModeOptions,
  syncModeOptions,
} from "./ConnectorDatasourceTable";
import {
  fetchConnectorSpec,
  fetchSourcePreview,
  getDatasourceDetails,
  syncDatasource,
  updateDatasource,
} from "@/lib/api/domains/datasources/api";

jest.mock("react-i18next", () => {
  // Stable like the real hook's `t`: effects that depend on it must not re-run per render.
  const t = (key: string) => key;
  return {
    useTranslation: () => ({ t }),
    initReactI18next: { type: "3rdParty", init: () => {} },
  };
});

jest.mock("@/hooks/useToast", () => ({
  toast: { success: jest.fn(), error: jest.fn(), info: jest.fn() },
}));

jest.mock("@/lib/api/domains/datasources/hooks", () => ({
  useDatasourceStatus: () => ({ status: undefined }),
  useDatasourceSchedule: () => ({ schedule: null }),
  useDatasourceSyncHistory: () => ({ attempts: [], isLoading: false }),
}));

jest.mock("@/lib/api/domains/datasources/api", () => ({
  fetchConnectorSpec: jest.fn(),
  fetchSourcePreview: jest.fn(),
  getDatasourceDetails: jest.fn(),
  syncDatasource: jest.fn(),
  updateDatasource: jest.fn(),
  deleteDatasource: jest.fn(),
  createSchedule: jest.fn(),
  updateSchedule: jest.fn(),
  deleteSchedule: jest.fn(),
}));

const datasource = {
  id: "ds-1",
  name: "Orders",
  connector_type: "postgres",
  connector_display_name: "Postgres",
  streams: ["orders"],
};

const spec = {
  name: "postgres",
  display_name: "Postgres",
  connection_specification: {
    type: "object",
    properties: {
      host: { type: "string", title: "Host" },
      port: { type: "integer", title: "Port", default: 5432 },
    },
    required: ["host"],
  },
  supported_sync_modes: ["full_refresh", "incremental"],
};

function renderDialog() {
  return render(
    <ManageDialog
      datasource={datasource}
      open
      onOpenChange={jest.fn()}
      onSaved={jest.fn()}
    />
  );
}

describe("ManageDialog connection and sync controls", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    jest.mocked(fetchConnectorSpec).mockResolvedValue(spec);
    jest.mocked(getDatasourceDetails).mockResolvedValue({
      ...datasource,
      config: { host: "db.internal" },
      sync_mode: "full_refresh",
      destination_sync_mode: "overwrite",
    });
    jest.mocked(updateDatasource).mockResolvedValue({ ...datasource });
    jest.mocked(syncDatasource).mockResolvedValue({});
    jest.mocked(fetchSourcePreview).mockResolvedValue({
      datasource_id: "ds-1",
      connector_type: "postgres",
      streams: [{ name: "orders" }, { name: "customers" }],
    });
  });

  it("prefills the connection form with the stored configuration and saves connector_config", async () => {
    const user = setupUser();
    renderDialog();

    await user.click(
      screen.getByText("admin.indexingStatus.manage.tabs.connection")
    );
    const host = await screen.findByDisplayValue("db.internal");
    expect(getDatasourceDetails).toHaveBeenCalledWith("ds-1", 1, 1);
    expect(fetchConnectorSpec).toHaveBeenCalledWith("postgres");
    expect(
      screen.queryByText("admin.indexingStatus.manage.connection.missingConfig")
    ).not.toBeInTheDocument();

    await user.clear(host);
    await user.type(host, "db2.internal");
    await user.click(
      screen.getByText("admin.indexingStatus.manage.connection.save")
    );

    await waitFor(() => {
      expect(updateDatasource).toHaveBeenCalledWith("ds-1", {
        connector_config: expect.objectContaining({ host: "db2.internal" }),
      });
    });
  });

  it("tells the user when no configuration is stored", async () => {
    jest.mocked(getDatasourceDetails).mockResolvedValue({
      ...datasource,
      config: {},
    });
    const user = setupUser();
    renderDialog();

    await user.click(
      screen.getByText("admin.indexingStatus.manage.tabs.connection")
    );

    expect(
      await screen.findByText(
        "admin.indexingStatus.manage.connection.missingConfig"
      )
    ).toBeInTheDocument();
  });

  it("discovers streams through the service's source preview of the stored configuration", async () => {
    const user = setupUser();
    renderDialog();

    await user.click(
      screen.getByText("admin.indexingStatus.manage.discoverStreams")
    );

    expect(await screen.findByText("customers")).toBeInTheDocument();
    expect(fetchSourcePreview).toHaveBeenCalledWith("ds-1");
  });

  it("starts a full refresh through the sync endpoint", async () => {
    const user = setupUser();
    renderDialog();

    await user.click(
      screen.getByText("admin.indexingStatus.manage.fullRefresh")
    );

    await waitFor(() => {
      expect(syncDatasource).toHaveBeenCalledWith("ds-1", {
        fullRefresh: true,
      });
    });
  });
});

describe("sync mode options", () => {
  it("offers only the modes the connector supports, full refresh by default", () => {
    expect(syncModeOptions(null)).toEqual(["full_refresh"]);
    expect(
      syncModeOptions({ ...spec, supported_sync_modes: ["full_refresh"] })
    ).toEqual(["full_refresh"]);
    expect(syncModeOptions(spec)).toEqual(["full_refresh", "incremental"]);
  });

  it("lets an incremental read only append", () => {
    expect(destinationModeOptions("full_refresh")).toEqual([
      "overwrite",
      "append",
    ]);
    expect(destinationModeOptions("incremental")).toEqual(["append"]);
  });
});
