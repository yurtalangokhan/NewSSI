import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import FilterButton from "./FilterButton";
import { SvgUser } from "@opal/icons";

describe("FilterButton", () => {
  it("renders correctly in inactive state without nested buttons", () => {
    const { container } = render(
      <FilterButton leftIcon={SvgUser} active={false}>
        Filter
      </FilterButton>
    );

    expect(screen.getByText("Filter")).toBeInTheDocument();
    const buttons = container.querySelectorAll("button");
    expect(buttons.length).toBe(1);
    expect(container.querySelector("button button")).toBeNull();
  });

  it("renders correctly in active state without nested buttons", () => {
    const onClear = jest.fn();
    const onClick = jest.fn();
    const { container } = render(
      <FilterButton
        leftIcon={SvgUser}
        active={true}
        onClick={onClick}
        onClear={onClear}
      >
        Active Filter
      </FilterButton>
    );

    expect(screen.getByText("Active Filter")).toBeInTheDocument();
    const buttons = container.querySelectorAll("button");
    expect(buttons.length).toBe(1);
    expect(container.querySelector("button button")).toBeNull();

    const clearBtn = screen.getByRole("button", { name: "Clear filter" });
    expect(clearBtn.tagName.toLowerCase()).toBe("span");

    fireEvent.click(clearBtn);
    expect(onClear).toHaveBeenCalledTimes(1);
    expect(onClick).not.toHaveBeenCalled();
  });
});
