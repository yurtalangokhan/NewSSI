declare module "d3-force-3d" {
  export function forceCollide<NodeDatum = any>(
    radius?:
      | number
      | ((node: NodeDatum, i: number, nodes: NodeDatum[]) => number)
  ): {
    (alpha?: number): void;
    radius(): (node: NodeDatum, i: number, nodes: NodeDatum[]) => number;
    radius(
      radius:
        | number
        | ((node: NodeDatum, i: number, nodes: NodeDatum[]) => number)
    ): this;
    strength(): number;
    strength(strength: number): this;
    iterations(): number;
    iterations(iterations: number): this;
  };

  export function forceLink<NodeDatum = any, LinkDatum = any>(
    links?: LinkDatum[]
  ): any;
  export function forceManyBody<NodeDatum = any>(): any;
  export function forceCenter<NodeDatum = any>(
    x?: number,
    y?: number,
    z?: number
  ): any;
  export function forceSimulation<NodeDatum = any>(nodes?: NodeDatum[]): any;
}
