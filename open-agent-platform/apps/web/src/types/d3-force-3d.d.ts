/**
 * Minimal type declarations for d3-force-3d.
 * Only the APIs used in graph-explorer are declared here.
 * d3-force-3d is a superset of d3-force with 1D/2D/3D support.
 */
declare module "d3-force-3d" {
  export interface SimulationNodeDatum {
    index?: number;
    x?: number;
    y?: number;
    z?: number;
    vx?: number;
    vy?: number;
    vz?: number;
    fx?: number | null;
    fy?: number | null;
    fz?: number | null;
    [key: string]: any;
  }

  // ── forceCollide ──
  export interface ForceCollide {
    (alpha: number): void;
    initialize(nodes: SimulationNodeDatum[], random: () => number, numDimensions: number): void;
    radius(): (node: SimulationNodeDatum, i: number, nodes: SimulationNodeDatum[]) => number;
    radius(radius: number | ((node: SimulationNodeDatum, i: number, nodes: SimulationNodeDatum[]) => number)): ForceCollide;
    strength(): number;
    strength(strength: number): ForceCollide;
    iterations(): number;
    iterations(iterations: number): ForceCollide;
  }
  export function forceCollide(radius?: number | ((node: SimulationNodeDatum, i: number, nodes: SimulationNodeDatum[]) => number)): ForceCollide;

  // ── forceRadial ──
  export interface ForceRadial {
    (alpha: number): void;
    initialize(nodes: SimulationNodeDatum[], random: () => number, numDimensions: number): void;
    radius(): (node: SimulationNodeDatum, i: number, nodes: SimulationNodeDatum[]) => number;
    radius(radius: number | ((node: SimulationNodeDatum, i: number, nodes: SimulationNodeDatum[]) => number)): ForceRadial;
    strength(): (node: SimulationNodeDatum, i: number, nodes: SimulationNodeDatum[]) => number;
    strength(strength: number | ((node: SimulationNodeDatum, i: number, nodes: SimulationNodeDatum[]) => number)): ForceRadial;
    x(): number;
    x(x: number): ForceRadial;
    y(): number;
    y(y: number): ForceRadial;
    z(): number;
    z(z: number): ForceRadial;
  }
  export function forceRadial(radius?: number | ((node: SimulationNodeDatum, i: number, nodes: SimulationNodeDatum[]) => number), x?: number, y?: number, z?: number): ForceRadial;
}
