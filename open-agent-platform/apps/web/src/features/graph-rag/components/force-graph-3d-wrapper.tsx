/**
 * Thin wrapper around react-force-graph-3d that is loaded via next/dynamic
 * with ssr: false. This prevents Three.js from being evaluated during SSR
 * where WebGL constants (like VERTEX) are unavailable.
 */

"use client";

import { forwardRef, useImperativeHandle, useRef } from "react";
import ForceGraph3DComponent from "react-force-graph-3d";

const ForceGraph3DWrapper = forwardRef<any, any>((props, ref) => {
  const innerRef = useRef<any>(null);

  // Expose the inner ref's methods to the parent via a proxy that
  // safely returns undefined for any property access when the inner
  // ref is null (e.g. during unmount). This prevents "Cannot read
  // properties of undefined (reading 'tick')" crashes.
  useImperativeHandle(ref, () =>
    new Proxy({} as any, {
      get(_target, prop) {
        const current = innerRef.current;
        if (!current) return undefined;
        const val = current[prop];
        return typeof val === "function" ? val.bind(current) : val;
      },
    }),
  );

  return <ForceGraph3DComponent ref={innerRef} {...props} />;
});

ForceGraph3DWrapper.displayName = "ForceGraph3DWrapper";

export default ForceGraph3DWrapper;
