import { act, screen } from "@testing-library/react";
import { render } from "@tests/setup/test-utils";
import AdminOverviewPanel from "@/components/admin/AdminOverviewPanel";
import { SvgWallet } from "@opal/icons";

describe("AdminOverviewPanel", () => {
  it("renders metrics without any navigation button row", () => {
    render(
      <AdminOverviewPanel
        icon={SvgWallet}
        title="Test workspace"
        description="Test description"
        metrics={[
          { label: "Toplam ajan", value: "42" },
          { label: "Araç bağlı", value: "20" },
        ]}
      />
    );

    expect(screen.getByText("Test workspace")).toBeInTheDocument();
    expect(screen.getByText("Toplam ajan")).toBeInTheDocument();
    expect(screen.getByText("42")).toBeInTheDocument();
    expect(screen.queryAllByRole("link")).toHaveLength(0);
    expect(screen.queryAllByRole("button")).toHaveLength(0);
  });

  it("renders the skeleton without a button placeholder while loading", () => {
    render(
      <AdminOverviewPanel
        icon={SvgWallet}
        title="Test workspace"
        description="Test description"
        isLoading
      />
    );

    expect(screen.getByRole("status")).toBeInTheDocument();
    expect(screen.queryAllByRole("button")).toHaveLength(0);
  });

  it("auto-rotates a metric's values when more than one is provided", () => {
    jest.useFakeTimers();
    render(
      <AdminOverviewPanel
        icon={SvgWallet}
        title="Test workspace"
        description="Test description"
        metrics={[
          {
            label: "En yaygın rol",
            value: "Enduser · 128",
            values: [
              { value: "Enduser · 128" },
              { value: "Admin · 5" },
              { value: "Curator · 2" },
            ],
          },
        ]}
      />
    );

    expect(screen.getByText("Enduser · 128")).toBeInTheDocument();

    act(() => {
      jest.advanceTimersByTime(3000);
    });
    expect(screen.getByText("Admin · 5")).toBeInTheDocument();

    act(() => {
      jest.advanceTimersByTime(3000);
    });
    expect(screen.getByText("Curator · 2")).toBeInTheDocument();

    act(() => {
      jest.advanceTimersByTime(3000);
    });
    expect(screen.getByText("Enduser · 128")).toBeInTheDocument();

    jest.useRealTimers();
  });

  it("falls back to a single static value when only one value is provided", () => {
    render(
      <AdminOverviewPanel
        icon={SvgWallet}
        title="Test workspace"
        description="Test description"
        metrics={[
          {
            label: "En yaygın rol",
            value: "Enduser · 128",
            values: [{ value: "Enduser · 128" }],
          },
        ]}
      />
    );

    expect(screen.getByText("Enduser · 128")).toBeInTheDocument();
  });

  it("fills the full row width regardless of how many metrics are passed", () => {
    render(
      <AdminOverviewPanel
        icon={SvgWallet}
        title="Test workspace"
        description="Test description"
        metrics={[{ label: "Yerleşik Sağlayıcılar", value: "1" }]}
      />
    );

    const tile = screen.getByText("Yerleşik Sağlayıcılar").closest("div");
    expect(tile).toHaveClass("flex-1");
  });
});
