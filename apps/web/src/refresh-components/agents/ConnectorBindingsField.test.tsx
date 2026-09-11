import React from "react";
import { Formik } from "formik";
import { fireEvent, render, screen } from "@tests/setup/test-utils";

import ConnectorBindingsField from "./ConnectorBindingsField";

const options = [
  {
    id: "github-1",
    name: "Engineering GitHub",
    connector_type: "github",
    operations: ["list_resources", "read"],
    unavailable_reason: null,
  },
  {
    id: "drive-1",
    name: "Finance Drive",
    connector_type: "google_drive",
    operations: ["list_resources"],
    unavailable_reason: null,
  },
  {
    id: "broken-1",
    name: "Broken Drive",
    connector_type: "google_drive",
    operations: ["list_resources"],
    unavailable_reason: "Connection needs attention",
  },
];

function renderField(
  initialBindings: Array<{ datasource_id: string; operations: string[] }> = []
) {
  return render(
    <Formik
      initialValues={{ connector_bindings: initialBindings }}
      onSubmit={() => undefined}
    >
      <ConnectorBindingsField
        options={options}
        isLoading={false}
        error={undefined}
      />
    </Formik>
  );
}

describe("ConnectorBindingsField", () => {
  it("selects multiple configured connectors and their allowed operations", () => {
    renderField();

    fireEvent.click(
      screen.getByRole("checkbox", { name: "Engineering GitHub" })
    );
    fireEvent.click(screen.getByRole("checkbox", { name: "Finance Drive" }));

    expect(
      screen.getByRole("checkbox", { name: "Engineering GitHub" })
    ).toHaveAttribute("aria-checked", "true");
    expect(
      screen.getByRole("checkbox", { name: "Finance Drive" })
    ).toHaveAttribute("aria-checked", "true");
    expect(
      screen.getByRole("checkbox", { name: "Broken Drive" })
    ).toHaveAttribute("tabindex", "-1");
    expect(
      screen.getByRole("checkbox", { name: "Engineering GitHub: Read" })
    ).toHaveAttribute("aria-checked", "true");
    expect(
      screen.getByRole("checkbox", { name: "Finance Drive: Read" })
    ).toHaveAttribute("tabindex", "-1");
  });

  it("keeps a deleted saved binding visible and removable", () => {
    renderField([{ datasource_id: "deleted-1", operations: ["read"] }]);

    expect(
      screen.getByText("Deleted connector (deleted-1)")
    ).toBeInTheDocument();
    fireEvent.click(
      screen.getByRole("button", {
        name: "Remove Deleted connector (deleted-1)",
      })
    );
    expect(
      screen.queryByText("Deleted connector (deleted-1)")
    ).not.toBeInTheDocument();
  });

  it("does not hide saved bindings when loading options fails", () => {
    render(
      <Formik
        initialValues={{
          connector_bindings: [
            { datasource_id: "github-1", operations: ["read"] },
          ],
        }}
        onSubmit={() => undefined}
      >
        <ConnectorBindingsField
          options={undefined}
          isLoading={false}
          error={new Error("offline")}
        />
      </Formik>
    );

    expect(screen.getByText("Saved connector (github-1)")).toBeInTheDocument();
    expect(
      screen.getByText(
        "Connector options could not be loaded. Saved selections are preserved."
      )
    ).toBeInTheDocument();
  });
});
