import { getSelectedRoleName } from "./roleSelection";

describe("getSelectedRoleName", () => {
  it("selects the first backend role when nothing is selected", () => {
    expect(
      getSelectedRoleName(
        [{ name: "enduser" }, { name: "enterprise-admin" }],
        ""
      )
    ).toBe("enduser");
  });

  it("keeps an existing selected role when it is still present", () => {
    expect(
      getSelectedRoleName(
        [{ name: "enduser" }, { name: "enterprise-admin" }],
        "enterprise-admin"
      )
    ).toBe("enterprise-admin");
  });

  it("falls back to the first role when the selected role disappears", () => {
    expect(getSelectedRoleName([{ name: "enduser" }], "custom-role")).toBe(
      "enduser"
    );
  });
});
