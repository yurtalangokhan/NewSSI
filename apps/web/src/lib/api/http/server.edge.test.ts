jest.mock("@/i18n/config", () => {
  throw new Error("browser-only i18n loaded by the edge transport");
});

describe("server transport edge boundary", () => {
  it("does not load browser-only error presentation dependencies", () => {
    expect(() => {
      jest.isolateModules(() => {
        require("@/lib/api/http/server");
      });
    }).not.toThrow();
  });
});
