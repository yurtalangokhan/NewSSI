import { fireEvent, render } from "@testing-library/react";
import { OrganizationMiniMapNode } from "@/components/organization/OrganizationMiniMapNode";

it("keeps minimap markers visible at overview scale and forwards focus clicks", () => {
  const onClick = jest.fn();
  const { container } = render(
    <svg>
      <OrganizationMiniMapNode
        id="root"
        x={1000000}
        y={0}
        width={300}
        height={150}
        selected
        borderRadius={5}
        className=""
        shapeRendering="auto"
        onClick={onClick}
      />
    </svg>
  );
  const marker = container.querySelector("rect")!;
  expect(marker).toHaveAttribute("vector-effect", "non-scaling-stroke");
  expect(marker).toHaveAttribute("stroke-width", "4");
  fireEvent.click(marker);
  expect(onClick).toHaveBeenCalledWith(expect.anything(), "root");
});
