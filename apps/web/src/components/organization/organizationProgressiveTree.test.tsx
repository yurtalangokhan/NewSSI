import { getProgressiveCollapsedIds } from "@/components/organization/organizationProgressiveTree";
import {
  organizationTreeToFlowGraph,
  type OrganizationTreeNode,
} from "@/components/organization/organizationGraph";

it.each(["vertical", "horizontal"] as const)(
  "compacts 10,000 units and expands one level in %s mode",
  (orientation) => {
    const root: OrganizationTreeNode = {
      id: "0",
      name: "Root",
      path: "/0",
      parent_id: null,
      children: [],
    };
    const all = [root];
    for (let i = 1; i < 10000; i++) {
      const parent = all[Math.floor((i - 1) / 5)]!;
      const node = {
        id: String(i),
        name: String(i),
        path: `${parent.path}/${i}`,
        parent_id: parent.id,
        children: [],
      };
      parent.children!.push(node);
      all.push(node);
    }
    const expanded = new Set<string>();
    const graph = () =>
      organizationTreeToFlowGraph(
        [root],
        {},
        new Set(),
        undefined,
        orientation,
        expanded,
        getProgressiveCollapsedIds([root], expanded, new Set())
      );
    expect(graph().nodes).toHaveLength(6);
    expanded.add("1");
    const next = graph();
    expect(next.nodes).toHaveLength(11);
    expect(next.nodes.find((node) => node.id === "6")).toBeDefined();
    expect(next.nodes.find((node) => node.id === "31")).toBeUndefined();
    const axis = orientation === "vertical" ? "x" : "y";
    const coords = next.nodes.map((node) => node.position[axis]);
    expect(Math.max(...coords) - Math.min(...coords)).toBeLessThan(15000);
  }
);
