declare module "d3-force-3d" {
  /** A force the simulation applies to its nodes on every tick. */
  export interface Force {
    (alpha: number): void;
  }

  type Accessor<NodeDatum, Value> =
    | Value
    | ((node: NodeDatum, i: number, nodes: NodeDatum[]) => Value);

  export interface ForceCollide<NodeDatum = unknown> extends Force {
    radius(): (node: NodeDatum, i: number, nodes: NodeDatum[]) => number;
    radius(radius: Accessor<NodeDatum, number>): this;
    strength(): number;
    strength(strength: number): this;
    iterations(): number;
    iterations(iterations: number): this;
  }

  export interface ForceLink<NodeDatum = unknown, LinkDatum = unknown>
    extends Force {
    links(): LinkDatum[];
    links(links: LinkDatum[]): this;
    id(id: (node: NodeDatum, i: number, nodes: NodeDatum[]) => string): this;
    distance(distance: number | ((link: LinkDatum, i: number) => number)): this;
    strength(strength: number | ((link: LinkDatum, i: number) => number)): this;
  }

  export interface ForceManyBody<NodeDatum = unknown> extends Force {
    strength(strength: Accessor<NodeDatum, number>): this;
    distanceMin(distance: number): this;
    distanceMax(distance: number): this;
  }

  export interface ForceCenter extends Force {
    x(x: number): this;
    y(y: number): this;
    z(z: number): this;
  }

  /** Pulls nodes toward one coordinate; ``forceX`` and ``forceY`` share it. */
  export interface ForcePosition<NodeDatum = unknown> extends Force {
    strength(strength: Accessor<NodeDatum, number>): this;
  }

  export interface Simulation<NodeDatum = unknown> {
    numDimensions(dimensions: 1 | 2 | 3): this;
    force(name: string, force: Force | null): this;
    stop(): this;
    tick(iterations?: number): this;
    nodes(): NodeDatum[];
  }

  export function forceCollide<NodeDatum = unknown>(
    radius?: Accessor<NodeDatum, number>
  ): ForceCollide<NodeDatum>;
  export function forceLink<NodeDatum = unknown, LinkDatum = unknown>(
    links?: LinkDatum[]
  ): ForceLink<NodeDatum, LinkDatum>;
  export function forceManyBody<
    NodeDatum = unknown,
  >(): ForceManyBody<NodeDatum>;
  export function forceCenter(x?: number, y?: number, z?: number): ForceCenter;
  export function forceSimulation<NodeDatum = unknown>(
    nodes?: NodeDatum[]
  ): Simulation<NodeDatum>;
  export function forceX<NodeDatum = unknown>(
    x?: number
  ): ForcePosition<NodeDatum>;
  export function forceY<NodeDatum = unknown>(
    y?: number
  ): ForcePosition<NodeDatum>;
}
