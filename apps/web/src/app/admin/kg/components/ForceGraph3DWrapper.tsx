/**
 * SSR-safe wrapper for react-force-graph-3d.
 * Three.js accesses WebGL constants at import time which crashes in Node.
 * This component is always loaded via next/dynamic with ssr: false.
 */
"use client";

import { forwardRef, useImperativeHandle, useRef } from "react";
import ForceGraph3DComponent from "react-force-graph-3d";

const ForceGraph3DWrapper = forwardRef<any, any>((props, ref) => {
  const innerRef = useRef<any>(null);

  // Proxy that safely returns undefined for any property access when the
  // inner ref is null (e.g. during unmount). Prevents "Cannot read properties
  // of undefined (reading 'tick')" crashes.
  useImperativeHandle(ref, () =>
    new Proxy({} as any, {
      get(_target, prop) {
        const current = innerRef.current;
        if (!current) return undefined;
        const val = current[prop];
        return typeof val === "function" ? val.bind(current) : val;
      },
    })
  );

  return <ForceGraph3DComponent ref={innerRef} {...props} />;
});

ForceGraph3DWrapper.displayName = "ForceGraph3DWrapper";
export default ForceGraph3DWrapper;
